"""
Tests for DocumentService — extraction, validation, and chunking.
"""
from __future__ import annotations

import io
import json
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Patch DATA_DIR before importing the service so tests use a temp directory
@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    import services.document_service as ds_mod
    monkeypatch.setattr(ds_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ds_mod, "DOCUMENTS_FILE", tmp_path / "documents.json")
    yield tmp_path


from services.document_service import DocumentService, DocumentValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_txt_bytes(text: str = "Hello world") -> bytes:
    return text.encode("utf-8")


def _make_minimal_pdf_bytes() -> bytes:
    """Return a tiny but structurally valid PDF with one text page."""
    content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>
stream
BT /F1 12 Tf 100 700 Td (Hello PDF) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000360 00000 n 
trailer<</Size 6/Root 1 0 R>>
startxref
441
%%EOF"""
    return content


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestValidation:
    def test_file_too_large_raises(self):
        svc = DocumentService()
        big = b"x" * (5 * 1024 * 1024 + 1)
        with pytest.raises(DocumentValidationError, match="too large"):
            svc.process_upload(big, "big.txt", "text/plain")

    def test_unsupported_mime_raises(self):
        svc = DocumentService()
        with pytest.raises(DocumentValidationError, match="Unsupported file type"):
            svc.process_upload(b"data", "file.docx", "application/msword")

    def test_empty_text_raises(self):
        svc = DocumentService()
        # A text file with only whitespace should fail
        with pytest.raises(DocumentValidationError, match="empty"):
            svc.process_upload(b"   \n  ", "empty.txt", "text/plain")

    def test_pdf_extension_accepted_without_mime(self):
        """Extension .pdf should be accepted even if MIME is octet-stream."""
        svc = DocumentService()
        # Use a real tiny PDF so pypdf doesn't crash
        pdf_bytes = _make_minimal_pdf_bytes()
        try:
            record = svc.process_upload(pdf_bytes, "notes.pdf", "application/octet-stream")
            assert record["filename"] == "notes.pdf"
        except DocumentValidationError as e:
            # Acceptable if pypdf can't parse the minimal PDF in this env
            assert "Could not read PDF" in str(e) or "empty" in str(e)


# ---------------------------------------------------------------------------
# TXT extraction tests
# ---------------------------------------------------------------------------

class TestTxtExtraction:
    def test_basic_txt_extraction(self):
        svc = DocumentService()
        text = "Introduction\n\nThis is the first topic.\n\nConclusion\n\nFinal thoughts."
        record = svc.process_upload(_make_txt_bytes(text), "notes.txt", "text/plain")
        assert record["full_text"] == text
        assert len(record["topics"]) >= 1

    def test_record_has_required_keys(self):
        svc = DocumentService()
        record = svc.process_upload(
            _make_txt_bytes("Some content here."), "doc.txt", "text/plain"
        )
        for key in ("id", "filename", "uploaded_at", "full_text", "topics"):
            assert key in record

    def test_latin1_encoding(self):
        svc = DocumentService()
        text = "Héllo wörld"
        record = svc.process_upload(text.encode("latin-1"), "doc.txt", "text/plain")
        assert "Héllo" in record["full_text"]


# ---------------------------------------------------------------------------
# Chunking tests
# ---------------------------------------------------------------------------

class TestChunking:
    def test_heading_based_chunking(self):
        svc = DocumentService()
        text = (
            "# Introduction\n\nThis covers the basics.\n\n"
            "# Advanced Topics\n\nThis covers advanced material.\n\n"
            "# Conclusion\n\nSummary of everything."
        )
        record = svc.process_upload(_make_txt_bytes(text), "notes.txt", "text/plain")
        names = [t["name"] for t in record["topics"]]
        assert any("Introduction" in n for n in names)
        assert any("Advanced" in n for n in names)

    def test_fallback_paragraph_chunking(self):
        svc = DocumentService()
        # Plain paragraphs, no headings
        paras = ["Word " * 100, "Word " * 100, "Word " * 100]
        text = "\n\n".join(paras)
        record = svc.process_upload(_make_txt_bytes(text), "notes.txt", "text/plain")
        assert len(record["topics"]) >= 1

    def test_single_paragraph_gives_one_topic(self):
        svc = DocumentService()
        text = "This is a single paragraph with enough content to be a topic."
        record = svc.process_upload(_make_txt_bytes(text), "notes.txt", "text/plain")
        assert len(record["topics"]) == 1


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_document_is_saved(self, tmp_data_dir):
        svc = DocumentService()
        svc.process_upload(_make_txt_bytes("Topic A\n\nContent A."), "a.txt", "text/plain")
        docs = svc.list_documents()
        assert len(docs) == 1
        assert docs[0]["filename"] == "a.txt"

    def test_multiple_documents_accumulate(self, tmp_data_dir):
        svc = DocumentService()
        svc.process_upload(_make_txt_bytes("Topic A content here."), "a.txt", "text/plain")
        svc.process_upload(_make_txt_bytes("Topic B content here."), "b.txt", "text/plain")
        docs = svc.list_documents()
        assert len(docs) == 2

    def test_get_document_by_id(self, tmp_data_dir):
        svc = DocumentService()
        record = svc.process_upload(_make_txt_bytes("Content for retrieval."), "r.txt", "text/plain")
        found = svc.get_document(record["id"])
        assert found is not None
        assert found["id"] == record["id"]

    def test_get_missing_document_returns_none(self, tmp_data_dir):
        svc = DocumentService()
        assert svc.get_document("nonexistent-id") is None
