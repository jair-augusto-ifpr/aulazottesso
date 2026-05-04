"""Extração básica de texto de arquivos enviados no Material."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from pypdf import PdfReader


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def extract_text_from_upload(uploaded_file) -> str:
    """Extrai texto de PDF/DOCX/TXT/MD sem interromper o fluxo de upload."""
    name = getattr(uploaded_file, "name", "") or ""
    suffix = Path(name).suffix.lower()

    try:
        uploaded_file.seek(0)
        if suffix == ".pdf":
            reader = PdfReader(uploaded_file)
            return "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
        if suffix == ".docx":
            doc = Document(uploaded_file)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()
        if suffix in {".txt", ".md"}:
            return _decode_bytes(uploaded_file.read()).strip()
        return ""
    except Exception:
        return ""
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
