"""InvoiceFlow Pro — local accounts-payable review workflow, no payment execution."""
from datetime import date
from hmac import compare_digest
from pathlib import Path
import re
from hashlib import sha256

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .ai import extract_with_ai
from .config import Settings
from .extract import DocumentError, fingerprint, parse_invoice, text_from_file
from .store import InvoiceConflict, Store, WorkflowError


class Corrections(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    fields: dict = Field(min_length=1, max_length=9)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    action: str = Field(pattern="^(approve|reject)$")
    note: str = Field(default="", max_length=300)


def create_app(config: Settings | None = None):
    settings = config or Settings.from_env()
    settings.validate()
    app = FastAPI(
        title="InvoiceFlow Pro — Accounts Payable Approval Lab",
        version=__version__,
        description="PDF/text invoice intake, validation, manual correction and operator approval. "
                    "No financial transfer or accounting-platform write actions.",
    )
    store: Store | None = None

    def get_store():
        nonlocal store
        if store is None:
            store = Store(settings)
        return store

    def auth(x_operator_key: str | None = Header(default=None)):
        if not settings.operator_ready or x_operator_key is None or not compare_digest(settings.operator_key, x_operator_key):
            raise HTTPException(status_code=401, detail="Valid operator key required")

    def safe_id(iid: str):
        if not re.fullmatch(r"[a-f0-9]{32}", iid):
            raise HTTPException(status_code=404, detail="Invoice not found")
        return iid

    def get_existing(iid):
        invoice = get_store().get(safe_id(iid))
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return invoice

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/health")
    def health():
        return {"ok": True, "mode": "LOCAL_REVIEW_ONLY", "version": __version__,
                "payments_enabled": False, "accounting_sync_enabled": False,
                "ai_provider_configured": bool(settings.openai_api_key)}

    @app.post("/api/invoices/upload", dependencies=[Depends(auth)])
    async def upload(file: UploadFile = File(...), use_ai: bool = Form(False), ai_authorized: bool = Form(False)):
        # Bounded read; processed bytes are never stored to disk by this application.
        payload = await file.read(settings.max_upload_bytes + 1)
        await file.close()
        if not payload or len(payload) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="Document is empty or exceeds the configured upload limit")
        filename = (file.filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if not (filename.lower().endswith(".pdf") or filename.lower().endswith(".txt")):
            raise HTTPException(status_code=422, detail="Only .pdf or .txt invoices are supported")
        try:
            text = text_from_file(payload, filename, max_pages=settings.max_pdf_pages)
            if use_ai:
                if not ai_authorized:
                    raise DocumentError("Explicit external AI data-processing authorization is required")
                invoice = extract_with_ai(text, api_key=settings.openai_api_key, model=settings.openai_model)
                mode = "opt_in_ai_unverified"
            else:
                invoice = parse_invoice(text)
                mode = "deterministic_template"
            return get_store().add(doc=invoice, source_hash=fingerprint(payload), filename=filename, mode=mode)
        except InvoiceConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DocumentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/invoices", dependencies=[Depends(auth)])
    def invoices():
        return {"items": get_store().list()}

    @app.get("/api/invoices/{iid}", dependencies=[Depends(auth)])
    def invoice(iid: str):
        return get_existing(iid)

    @app.patch("/api/invoices/{iid}", dependencies=[Depends(auth)])
    def correct(iid: str, req: Corrections):
        get_existing(iid)
        try:
            return get_store().revise(iid, req.fields, version=req.version)
        except InvoiceConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except WorkflowError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/invoices/{iid}/review", dependencies=[Depends(auth)])
    def review(iid: str, req: Decision):
        get_existing(iid)
        try:
            return get_store().review(iid, action=req.action, note=req.note, version=req.version)
        except InvoiceConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except WorkflowError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/audit", dependencies=[Depends(auth)])
    def audit():
        return {"events": get_store().events()}

    @app.get("/api/metrics", dependencies=[Depends(auth)])
    def metrics():
        return {**get_store().metrics(), "mode": "LOCAL_REVIEW_ONLY"}

    @app.get("/api/export.csv", dependencies=[Depends(auth)])
    def csv_export():
        import csv
        from io import StringIO
        stream = StringIO()
        writer = csv.writer(stream)
        writer.writerow(["invoice_id", "vendor", "invoice_number", "invoice_date", "currency", "total", "status", "errors"])
        for r in get_store().list():
            d = r["data"]
            writer.writerow([r["id"], d.get("vendor"), d.get("invoice_number"), d.get("invoice_date"),
                             d.get("currency"), d.get("total"), r["status"], ";".join(r["errors"])])
        return Response(
            content=stream.getvalue(), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="invoiceflow-local.csv"'},
        )

    return app


app = create_app()
