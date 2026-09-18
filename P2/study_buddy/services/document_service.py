"""
DocumentService — file upload, text extraction, and topic chunking.

Persistence: data/documents.json
"""
from __future__ import annotations

import io
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_TYPES = {"application/pdf", "text/plain"}
DATA_DIR = Path(__file__).parent.parent / "data"
DOCUMENTS_FILE = DATA_DIR / "documents.json"


class DocumentValidationError(ValueError):
    """Raised for invalid uploads."""


class DocumentService:
    """Handles document upload, text extraction, and topic chunking."""

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_upload(self, file_bytes: bytes, filename: str, mime_type: str) -> dict[str, Any]:
        """Validate, extract text, chunk into topics, and persist.

        Parameters
        ----------
        file_bytes:
            Raw bytes of the uploaded file.
        filename:
            Original filename (used for display and MIME fallback).
        mime_type:
            MIME type reported by the uploader.

        Returns
        -------
        dict
            Document record with ``id``, ``filename``, ``topics``, etc.

        Raises
        ------
        DocumentValidationError
            On size, type, or empty-content violations.
        """
        self._validate(file_bytes, filename, mime_type)
        text = self._extract_text(file_bytes, filename, mime_type)
        if not text.strip():
            raise DocumentValidationError("Extracted text is empty. Please upload a non-empty document.")
        topics = self._chunk_topics(text)
        record = {
            "id": str(uuid.uuid4()),
            "filename": filename,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "full_text": text,
            "topics": topics,
        }
        self._save(record)
        return record

    def list_documents(self) -> list[dict[str, Any]]:
        """Return all persisted document records."""
        return self._load_all()

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """Return a single document by id, or None."""
        for doc in self._load_all():
            if doc["id"] == doc_id:
                return doc
        return None

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def _validate(self, file_bytes: bytes, filename: str, mime_type: str) -> None:
        if len(file_bytes) > MAX_FILE_SIZE:
            raise DocumentValidationError(
                f"File is too large ({len(file_bytes) / 1024 / 1024:.1f} MB). Maximum allowed size is 5 MB."
            )
        # Accept by MIME or extension fallback
        ext = Path(filename).suffix.lower()
        if mime_type not in ALLOWED_TYPES and ext not in {".pdf", ".txt"}:
            raise DocumentValidationError(
                f"Unsupported file type '{mime_type}'. Only PDF and TXT files are accepted."
            )

    def _extract_text(self, file_bytes: bytes, filename: str, mime_type: str) -> str:
        ext = Path(filename).suffix.lower()
        if mime_type == "application/pdf" or ext == ".pdf":
            return self._extract_pdf(file_bytes)
        return self._extract_txt(file_bytes)

    def _extract_pdf(self, file_bytes: bytes) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages)
        except Exception as exc:
            raise DocumentValidationError(f"Could not read PDF: {exc}") from exc

    def _extract_txt(self, file_bytes: bytes) -> str:
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise DocumentValidationError("Could not decode text file. Please ensure it is UTF-8 encoded.")

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def _chunk_topics(self, text: str) -> list[dict[str, str]]:
        """Split text into named topic chunks.

        Strategy:
        1. Try heading-based splitting (Markdown / ALL-CAPS / numbered).
        2. Fall back to fixed-size paragraph windows with auto-generated names.
        """
        topics = self._split_by_headings(text)
        if len(topics) >= 2:
            return topics
        return self._split_by_paragraphs(text)

    def _split_by_headings(self, text: str) -> list[dict[str, str]]:
        """Detect headings and split accordingly."""
        # Match: Markdown (#), numbered (1. / 1.1), or short ALL-CAPS lines
        heading_re = re.compile(
            r"^(?:#{1,4}\s+.+|[A-Z][A-Z0-9 \-:,]{3,60}$|\d+[\.\)]\s+.{3,80})",
            re.MULTILINE,
        )
        matches = list(heading_re.finditer(text))
        if len(matches) < 2:
            return []

        topics: list[dict[str, str]] = []
        for i, match in enumerate(matches):
            title = match.group(0).strip().lstrip("#").strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                topics.append({"name": title[:120], "content": body})
        return topics

    def _split_by_paragraphs(self, text: str) -> list[dict[str, str]]:
        """Group paragraphs into ~500-word chunks."""
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        if not paragraphs:
            return [{"name": "Full Document", "content": text.strip()}]

        chunk_size = 500  # words per chunk
        chunks: list[dict[str, str]] = []
        current_words: list[str] = []
        chunk_index = 1

        for para in paragraphs:
            words = para.split()
            if current_words and len(current_words) + len(words) > chunk_size:
                body = " ".join(current_words)
                # Use first sentence as title
                first_sentence = re.split(r"[.!?]", body)[0].strip()
                name = (first_sentence[:80] + "…") if len(first_sentence) > 80 else first_sentence
                chunks.append({"name": name or f"Topic {chunk_index}", "content": body})
                chunk_index += 1
                current_words = words
            else:
                current_words.extend(words)

        if current_words:
            body = " ".join(current_words)
            first_sentence = re.split(r"[.!?]", body)[0].strip()
            name = (first_sentence[:80] + "…") if len(first_sentence) > 80 else first_sentence
            chunks.append({"name": name or f"Topic {chunk_index}", "content": body})

        return chunks if chunks else [{"name": "Full Document", "content": text.strip()}]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_all(self) -> list[dict[str, Any]]:
        if not DOCUMENTS_FILE.exists():
            return []
        try:
            with DOCUMENTS_FILE.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, record: dict[str, Any]) -> None:
        records = self._load_all()
        records.append(record)
        with DOCUMENTS_FILE.open("w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2, ensure_ascii=False)
