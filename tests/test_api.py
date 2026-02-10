"""Unit tests for the FastAPI server."""

import io
import json
import os

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from caselens.api import app, MAX_UPLOAD_BYTES


client = TestClient(app)

# -- Shared test data ------------------------------------------------------ #

TEST_API_KEY = "test-key-12345"

VALID_EXTRACTION = {
    "pages": [{"page_number": 1, "text": "Extracted content."}],
    "chunks": [{"chunk_index": 0, "text": "Chunk.", "char_count": 6, "source_pages": [1, 1]}],
    "metadata": {"total_pages": 1, "filename": "tmp12345.pdf", "is_chunked": False},
}

VALID_SUMMARY = {
    "parties": [
        {"name": "Marie Tremblay", "role": "petitioner", "aliases": []},
    ],
    "key_facts": ["The parties separated in June 2024."],
    "timeline": [{"date": "2024-06-15", "event": "Parties separated."}],
    "case_type": "custody",
    "summary": "A custody dispute.",
    "metadata": {
        "model": "claude-sonnet-4-5-20250929",
        "chunks_processed": 1,
        "filename": "tmp12345.pdf",
    },
}


def _pdf_bytes() -> bytes:
    """Minimal bytes to simulate a PDF upload."""
    return b"%PDF-1.4 fake content for testing purposes"


def _auth_headers(key: str = TEST_API_KEY) -> dict:
    """Build headers with X-API-Key."""
    return {"X-API-Key": key}


# -- Existing tests (auth disabled via CASELENS_API_KEY=None) -------------- #

def test_api_health():
    """GET /api/health returns 200."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@patch("caselens.api.CASELENS_API_KEY", None)
@patch("caselens.api.Summarizer")
@patch("caselens.api.PdfProcessor")
def test_api_summarize_valid_pdf(mock_processor_cls, mock_summarizer_cls):
    """Upload mock PDF, verify response structure."""
    mock_processor = MagicMock()
    mock_processor.process.return_value = VALID_EXTRACTION
    mock_processor_cls.return_value = mock_processor

    mock_summarizer = MagicMock()
    mock_summarizer.summarize.return_value = VALID_SUMMARY.copy()
    mock_summarizer_cls.return_value = mock_summarizer

    response = client.post(
        "/api/summarize",
        files={"file": ("case.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()
    assert "parties" in data
    assert "key_facts" in data
    assert "timeline" in data
    assert "case_type" in data
    assert "summary" in data
    assert "metadata" in data
    # Filename should be the original upload name, not the temp path
    assert data["metadata"]["filename"] == "case.pdf"


@patch("caselens.api.CASELENS_API_KEY", None)
def test_api_summarize_non_pdf():
    """Upload .txt file, verify 400 error."""
    response = client.post(
        "/api/summarize",
        files={"file": ("notes.txt", io.BytesIO(b"just text"), "text/plain")},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "invalid_format"


@patch("caselens.api.CASELENS_API_KEY", None)
def test_api_summarize_too_large():
    """Verify 413 error for oversized files."""
    # Create content just over the limit
    oversized = b"x" * (MAX_UPLOAD_BYTES + 1)

    response = client.post(
        "/api/summarize",
        files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
    )

    assert response.status_code == 413
    data = response.json()
    assert data["detail"]["error"] == "file_too_large"


@patch("caselens.api.CASELENS_API_KEY", None)
@patch("caselens.api.Summarizer")
@patch("caselens.api.PdfProcessor")
def test_api_temp_file_cleanup(mock_processor_cls, mock_summarizer_cls):
    """Verify temp files are deleted after processing."""
    captured_paths = []

    original_process = MagicMock(return_value=VALID_EXTRACTION)

    def tracking_process(filepath):
        captured_paths.append(filepath)
        return VALID_EXTRACTION

    mock_processor = MagicMock()
    mock_processor.process.side_effect = tracking_process
    mock_processor_cls.return_value = mock_processor

    mock_summarizer = MagicMock()
    mock_summarizer.summarize.return_value = VALID_SUMMARY.copy()
    mock_summarizer_cls.return_value = mock_summarizer

    response = client.post(
        "/api/summarize",
        files={"file": ("case.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
    )

    assert response.status_code == 200
    # The temp file path was captured — verify it no longer exists
    assert len(captured_paths) == 1
    assert not os.path.exists(captured_paths[0])


@patch("caselens.api.CASELENS_API_KEY", None)
@patch("caselens.api.Summarizer")
@patch("caselens.api.PdfProcessor")
def test_api_extraction_error(mock_processor_cls, mock_summarizer_cls):
    """Verify extraction error returns 422."""
    mock_processor = MagicMock()
    mock_processor.process.return_value = {
        "error": "scanned_pdf",
        "message": "PDF appears to be scanned.",
    }
    mock_processor_cls.return_value = mock_processor

    response = client.post(
        "/api/summarize",
        files={"file": ("scan.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
    )

    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "scanned_pdf"


@patch("caselens.api.CASELENS_API_KEY", None)
@patch("caselens.api.Summarizer")
@patch("caselens.api.PdfProcessor")
def test_api_summarizer_error(mock_processor_cls, mock_summarizer_cls):
    """Verify summarizer error returns 502."""
    mock_processor = MagicMock()
    mock_processor.process.return_value = VALID_EXTRACTION
    mock_processor_cls.return_value = mock_processor

    mock_summarizer = MagicMock()
    mock_summarizer.summarize.return_value = {
        "error": "missing_api_key",
        "message": "ANTHROPIC_API_KEY is not set.",
    }
    mock_summarizer_cls.return_value = mock_summarizer

    response = client.post(
        "/api/summarize",
        files={"file": ("case.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
    )

    assert response.status_code == 502
    data = response.json()
    assert data["error"] == "missing_api_key"


@patch("caselens.api.CASELENS_API_KEY", None)
@patch("caselens.api.Summarizer")
@patch("caselens.api.PdfProcessor")
def test_api_temp_cleanup_on_error(mock_processor_cls, mock_summarizer_cls):
    """Verify temp file cleaned up even when processing raises."""
    captured_paths = []

    def exploding_process(filepath):
        captured_paths.append(filepath)
        raise RuntimeError("Unexpected failure")

    mock_processor = MagicMock()
    mock_processor.process.side_effect = exploding_process
    mock_processor_cls.return_value = mock_processor

    response = client.post(
        "/api/summarize",
        files={"file": ("case.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
    )

    assert response.status_code == 500
    data = response.json()
    assert data["error"] == "internal_error"
    # The temp file is still cleaned up
    assert len(captured_paths) == 1
    assert not os.path.exists(captured_paths[0])


@patch("caselens.api.CASELENS_API_KEY", None)
def test_api_no_file():
    """Verify 422 when no file is provided."""
    response = client.post("/api/summarize")
    assert response.status_code == 422


# -- Auth tests ------------------------------------------------------------ #

@patch("caselens.api.CASELENS_API_KEY", TEST_API_KEY)
def test_api_summarize_missing_auth():
    """POST /api/summarize without X-API-Key header returns 401."""
    response = client.post(
        "/api/summarize",
        files={"file": ("case.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "missing_api_key"


@patch("caselens.api.CASELENS_API_KEY", TEST_API_KEY)
def test_api_summarize_invalid_auth():
    """POST /api/summarize with wrong API key returns 401."""
    response = client.post(
        "/api/summarize",
        files={"file": ("case.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "invalid_api_key"


@patch("caselens.api.CASELENS_API_KEY", TEST_API_KEY)
@patch("caselens.api.Summarizer")
@patch("caselens.api.PdfProcessor")
def test_api_summarize_valid_auth(mock_processor_cls, mock_summarizer_cls):
    """POST /api/summarize with valid API key returns 200."""
    mock_processor = MagicMock()
    mock_processor.process.return_value = VALID_EXTRACTION
    mock_processor_cls.return_value = mock_processor

    mock_summarizer = MagicMock()
    mock_summarizer.summarize.return_value = VALID_SUMMARY.copy()
    mock_summarizer_cls.return_value = mock_summarizer

    response = client.post(
        "/api/summarize",
        files={"file": ("case.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert "parties" in response.json()


@patch("caselens.api.CASELENS_API_KEY", TEST_API_KEY)
@patch("caselens.api.rate_limiter")
def test_api_summarize_rate_limited(mock_limiter):
    """POST /api/summarize returns 429 when rate limit exceeded."""
    mock_limiter.is_allowed.return_value = False
    mock_limiter.retry_after.return_value = 3600

    response = client.post(
        "/api/summarize",
        files={"file": ("case.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=_auth_headers(),
    )

    assert response.status_code == 429
    data = response.json()
    assert data["detail"]["error"] == "rate_limit_exceeded"


@patch("caselens.api.CASELENS_API_KEY", TEST_API_KEY)
def test_api_health_no_auth():
    """GET /api/health returns 200 even when auth is required."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
