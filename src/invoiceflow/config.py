"""Safe environment settings. No payments or accounting write connector exists."""
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    operator_key: str = ""
    db_path: Path = Path("./data/invoiceflow.sqlite")
    max_upload_bytes: int = 2 * 1024 * 1024
    max_pdf_pages: int = 8
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    @classmethod
    def from_env(cls):
        get = os.environ.get
        return cls(
            operator_key=get("IF_OPERATOR_KEY", ""),
            db_path=Path(get("IF_DB_PATH", "./data/invoiceflow.sqlite")),
            max_upload_bytes=int(get("IF_MAX_UPLOAD_BYTES", "2097152")),
            max_pdf_pages=int(get("IF_MAX_PDF_PAGES", "8")),
            openai_api_key=get("IF_OPENAI_API_KEY", ""),
            openai_model=get("IF_OPENAI_MODEL", "gpt-4.1-mini"),
        )

    def validate(self):
        if not 1000 <= self.max_upload_bytes <= 10_000_000:
            raise ValueError("Upload limit must be between 1000 bytes and 10 MB")
        if not 1 <= self.max_pdf_pages <= 20:
            raise ValueError("PDF page limit must be 1–20")

    @property
    def operator_ready(self):
        return len(self.operator_key) >= 24 and not self.operator_key.startswith("REPLACE_")
