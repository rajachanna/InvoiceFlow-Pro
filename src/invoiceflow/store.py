"""Atomic SQLite intake and human review workflow. No payment functions."""
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4
import json
import sqlite3

from .config import Settings
from .extract import invoice_key, validate_invoice


class InvoiceConflict(ValueError):
    pass


class WorkflowError(ValueError):
    pass


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS invoices (
                    id TEXT PRIMARY KEY,
                    source_hash TEXT NOT NULL UNIQUE,
                    invoice_key TEXT UNIQUE,
                    filename TEXT NOT NULL,
                    extraction_mode TEXT NOT NULL,
                    invoice_json TEXT NOT NULL,
                    errors_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('needs_review','approved','rejected')),
                    reviewer_note TEXT NOT NULL DEFAULT '',
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT ''
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(str(self.settings.db_path), timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=20000")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
        finally:
            db.close()

    def _record(self, r):
        record = dict(r)
        record["data"] = json.loads(record.pop("invoice_json"))
        record["errors"] = json.loads(record.pop("errors_json"))
        return record

    def add(self, *, doc, source_hash, filename, mode="rules"):
        errors = validate_invoice(doc)
        key = invoice_key(doc)
        iid = uuid4().hex
        now = utcnow()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # Enforce both duplicate strategies even under concurrent uploads.
            if db.execute("SELECT 1 FROM invoices WHERE source_hash=?", (source_hash,)).fetchone():
                db.execute("ROLLBACK")
                raise InvoiceConflict("This exact document was already uploaded")
            if key and db.execute("SELECT 1 FROM invoices WHERE invoice_key=?", (key,)).fetchone():
                db.execute("ROLLBACK")
                raise InvoiceConflict("An invoice from this vendor with this invoice number already exists")
            try:
                db.execute("""INSERT INTO invoices(
                    id,source_hash,invoice_key,filename,extraction_mode,invoice_json,errors_json,
                    status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,'needs_review',?,?)""",
                    (iid,source_hash,key,filename[:160],mode,json.dumps(doc),json.dumps(errors),now,now),
                )
            except sqlite3.IntegrityError as exc:
                db.execute("ROLLBACK")
                raise InvoiceConflict("Duplicate invoice conflict") from exc
            db.execute(
                "INSERT INTO audit(invoice_id,occurred_at,action,details) VALUES(?,?,?,?)",
                (iid,now,"uploaded",f"{mode} extraction; {len(errors)} review flags"),
            )
            db.execute("COMMIT")
        return self.get(iid)

    def get(self, iid):
        with self.connection() as db:
            r = db.execute("SELECT * FROM invoices WHERE id=?", (iid,)).fetchone()
        return self._record(r) if r else None

    def list(self):
        with self.connection() as db:
            return [self._record(r) for r in db.execute(
                "SELECT * FROM invoices ORDER BY created_at DESC LIMIT 300"
            )]

    def revise(self, iid, patch: dict, *, version: int):
        if not patch:
            raise WorkflowError("Supply at least one field to revise")
        allowed = {"vendor","invoice_number","invoice_date","due_date","currency","subtotal","tax","total","items"}
        if not set(patch).issubset(allowed):
            raise WorkflowError("Unrecognized correction field")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM invoices WHERE id=?", (iid,)).fetchone()
            if row is None:
                raise WorkflowError("Invoice does not exist")
            if row["version"] != version:
                raise InvoiceConflict("Invoice was changed by another reviewer; refresh")
            if row["status"] == "approved":
                raise WorkflowError("Approved records are locked; start a correction workflow")
            updated = json.loads(row["invoice_json"])
            updated.update(patch)
            new_key = invoice_key(updated)
            errors = validate_invoice(updated)
            now = utcnow()
            try:
                db.execute(
                    """UPDATE invoices SET invoice_json=?,invoice_key=?,errors_json=?,
                    status='needs_review',reviewer_note='',version=version+1,updated_at=? WHERE id=?""",
                    (json.dumps(updated),new_key,json.dumps(errors),now,iid),
                )
            except sqlite3.IntegrityError as exc:
                raise InvoiceConflict("Corrected vendor/invoice number conflicts with another invoice") from exc
            db.execute(
                "INSERT INTO audit(invoice_id,occurred_at,action,details) VALUES(?,?,?,?)",
                (iid,now,"corrected", "Updated: " + ", ".join(sorted(patch))),
            )
            db.execute("COMMIT")
        return self.get(iid)

    def review(self, iid, *, action: str, note: str, version: int):
        if action not in ("approve", "reject"):
            raise WorkflowError("Action must be approve or reject")
        if len(note) > 300:
            raise WorkflowError("Review note is too long")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM invoices WHERE id=?", (iid,)).fetchone()
            if row is None:
                raise WorkflowError("Invoice does not exist")
            if row["version"] != version:
                raise InvoiceConflict("Invoice was changed; refresh before review")
            if row["status"] != "needs_review":
                raise WorkflowError("Only pending review invoices can be actioned")
            errors = json.loads(row["errors_json"])
            if action == "approve" and errors:
                raise WorkflowError("Resolve all validation flags before approving")
            now = utcnow()
            new_status = "approved" if action == "approve" else "rejected"
            db.execute("""UPDATE invoices SET status=?,reviewer_note=?,version=version+1,
                       updated_at=? WHERE id=?""", (new_status,note,now,iid))
            db.execute("INSERT INTO audit(invoice_id,occurred_at,action,details) VALUES(?,?,?,?)",
                       (iid,now,new_status, "Manual operator decision"))
            db.execute("COMMIT")
        return self.get(iid)

    def events(self, iid=None):
        with self.connection() as db:
            if iid:
                rows = db.execute("SELECT * FROM audit WHERE invoice_id=? ORDER BY id DESC LIMIT 100", (iid,))
            else:
                rows = db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100")
            return [dict(r) for r in rows]

    def metrics(self):
        with self.connection() as db:
            groups = {r["status"]: r["n"] for r in db.execute(
                "SELECT status,count(*) n FROM invoices GROUP BY status"
            )}
            flags = db.execute("SELECT errors_json FROM invoices WHERE status='needs_review'").fetchall()
        return {
            "total": sum(groups.values()),
            "needs_review": groups.get("needs_review",0),
            "approved": groups.get("approved",0),
            "rejected": groups.get("rejected",0),
            "flagged": sum(bool(json.loads(r["errors_json"])) for r in flags),
        }
