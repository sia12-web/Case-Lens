"""Unit tests for PdfProcessor."""

import pytest
from unittest.mock import patch, MagicMock

from caselens.pdf_processor import PdfProcessor


@pytest.fixture
def processor():
    return PdfProcessor()


def _mock_pdfplumber_pdf(pages_data: list[tuple[int, str, list]]):
    """Build a mock pdfplumber PDF context manager.

    Args:
        pages_data: List of (page_number, text, images) tuples.
    """
    mock_pages = []
    for page_num, text, images in pages_data:
        page = MagicMock()
        page.page_number = page_num
        page.extract_text.return_value = text
        page.images = images
        mock_pages.append(page)

    mock_pdf = MagicMock()
    mock_pdf.pages = mock_pages
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    return mock_pdf


# ------------------------------------------------------------------ #
# Required tests
# ------------------------------------------------------------------ #

@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_extract_text_pdf(mock_exists, mock_pdfplumber, processor):
    """Verify text extraction returns correct structure with pages and metadata."""
    mock_pdfplumber.open.return_value = _mock_pdfplumber_pdf([
        (1, "First page content about the case. This paragraph contains enough text to exceed the scanned-PDF detection threshold used by the processor.", []),
        (2, "Second page with more legal details. The respondent filed a motion to dismiss on the grounds of insufficient evidence presented by the plaintiff.", []),
    ])

    result = processor.process("document.pdf")

    assert "pages" in result
    assert "chunks" in result
    assert "metadata" in result

    assert result["metadata"]["total_pages"] == 2
    assert result["metadata"]["filename"] == "document.pdf"
    assert isinstance(result["metadata"]["is_chunked"], bool)
    assert result["metadata"]["is_chunked"] is False

    assert len(result["pages"]) == 2
    assert result["pages"][0]["page_number"] == 1
    assert "First page content" in result["pages"][0]["text"]
    assert result["pages"][1]["page_number"] == 2

    assert len(result["chunks"]) == 1
    assert result["chunks"][0]["chunk_index"] == 0
    assert "char_count" in result["chunks"][0]
    assert "source_pages" in result["chunks"][0]


@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_chunking_splits_large_doc(mock_exists, mock_pdfplumber, processor):
    """Verify a long text gets split into chunks with overlap."""
    # 3 pages x 45k chars = 135k total -> must produce >= 2 chunks
    large_text = "Word " * 9000  # ~45,000 chars per page
    mock_pdfplumber.open.return_value = _mock_pdfplumber_pdf([
        (1, large_text, []),
        (2, large_text, []),
        (3, large_text, []),
    ])

    result = processor.process("large.pdf")

    assert "chunks" in result
    assert len(result["chunks"]) >= 2
    assert result["metadata"]["is_chunked"] is True

    # Each chunk should be within the size limit
    for chunk in result["chunks"]:
        assert chunk["char_count"] <= processor.MAX_CHUNK_SIZE
        assert "source_pages" in chunk
        assert len(chunk["source_pages"]) == 2

    # Verify overlap: a substring from the end of chunk 0 appears near the start of chunk 1
    overlap_sample = result["chunks"][0]["text"][-200:]
    assert overlap_sample in result["chunks"][1]["text"]


@patch("caselens.ocr.OcrEngine")
@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_handles_scanned_pdf(mock_exists, mock_pdfplumber, mock_engine_cls, processor):
    """Scanned PDF with OCR unavailable returns error dict."""
    mock_pdfplumber.open.return_value = _mock_pdfplumber_pdf([
        (1, "", [{"x0": 0}]),
        (2, "", [{"x0": 0}]),
        (3, "  ", [{"x0": 0}]),
        (4, "", [{"x0": 0}]),
        (5, "", [{"x0": 0}]),
    ])

    mock_engine = MagicMock()
    mock_engine.check_availability.return_value = (False, "Tesseract not installed")
    mock_engine_cls.return_value = mock_engine

    result = processor.process("scanned.pdf")

    assert "error" in result
    assert result["error"] == "ocr_unavailable"
    assert "message" in result


def test_handles_missing_file(processor):
    """Verify missing file path raises clean error."""
    result = processor.process("/nonexistent/path/to/file.pdf")

    assert "error" in result
    assert result["error"] == "file_not_found"
    assert "message" in result


@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_french_characters(mock_exists, mock_pdfplumber, processor):
    """Verify accented characters (é, è, ç, à, ï) are preserved correctly."""
    french_text = (
        "Le juge a rendu sa décision concernant l\u2019affaire.\n"
        "Les témoins ont été entendus à l\u2019audience.\n"
        "Résumé des conclusions: café, naïve, protégé.\n"
        "Arrêté de la Cour d\u2019appel du Québec.\n"
        "Conformément à l\u2019article 2858 du Code civil."
    )
    mock_pdfplumber.open.return_value = _mock_pdfplumber_pdf([
        (1, french_text, []),
    ])

    result = processor.process("french_doc.pdf")

    text = result["pages"][0]["text"]
    assert "décision" in text
    assert "témoins" in text
    assert "été" in text
    assert "à" in text
    assert "naïve" in text
    assert "café" in text
    assert "Québec" in text
    assert "Conformément" in text


# ------------------------------------------------------------------ #
# Additional edge-case tests
# ------------------------------------------------------------------ #

@patch("os.path.exists", return_value=True)
def test_handles_non_pdf_extension(mock_exists, processor):
    """Verify error on non-PDF file."""
    result = processor.process("document.docx")
    assert result["error"] == "invalid_format"


@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_password_protected_pdf(mock_exists, mock_pdfplumber, processor):
    """Verify password-protected PDF returns error dict."""
    # Simulate pdfminer encryption error
    try:
        from pdfminer.pdfdocument import PDFEncryptionError
        mock_pdfplumber.open.side_effect = PDFEncryptionError("File is encrypted")
    except ImportError:
        # If pdfminer not installed, use a generic exception with 'encrypt' in message
        exc = Exception("encrypt")
        exc.__class__.__name__ = "PDFEncryptionError"
        mock_pdfplumber.open.side_effect = exc
        pytest.skip("pdfminer not installed")

    result = processor.process("protected.pdf")
    assert result["error"] == "protected_pdf"
    assert "message" in result


def test_clean_text_removes_bates_stamps(processor):
    """Verify Bates stamps are removed."""
    text = "Some content\nABC-001234\nMore content"
    cleaned = processor._clean_text(text)
    assert "ABC-001234" not in cleaned
    assert "Some content" in cleaned
    assert "More content" in cleaned


def test_clean_text_removes_confidentiality_footer(processor):
    """Verify confidentiality footers are removed."""
    text = "Legal content here.\nPRIVILEGED AND CONFIDENTIAL"
    cleaned = processor._clean_text(text)
    assert "PRIVILEGED AND CONFIDENTIAL" not in cleaned
    assert "Legal content" in cleaned


def test_clean_text_removes_page_numbers(processor):
    """Verify standalone page numbers are removed."""
    text = "Content of the page.\n  42  \nMore content."
    cleaned = processor._clean_text(text)
    # The standalone "42" line should be removed
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    assert "42" not in lines


def test_clean_text_preserves_inline_numbers(processor):
    """Verify numbers within sentences are NOT removed."""
    text = "Article 42 of the Civil Code requires compliance."
    cleaned = processor._clean_text(text)
    assert "42" in cleaned


def test_clean_text_removes_french_confidentiality(processor):
    """Verify French confidentiality footers are removed."""
    text = "Contenu juridique.\nCONFIDENTIEL"
    cleaned = processor._clean_text(text)
    assert "CONFIDENTIEL" not in cleaned
    assert "Contenu juridique" in cleaned


@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_fallback_to_pypdf(mock_exists, mock_pdfplumber, processor):
    """Verify pypdf fallback when pdfplumber fails."""
    mock_pdfplumber.open.side_effect = Exception("pdfplumber failed")

    fallback_text = (
        "Fallback content extracted by pypdf. This text is long enough "
        "to pass the scanned-PDF detection threshold in the processor."
    )

    mock_reader = MagicMock()
    mock_reader.is_encrypted = False
    mock_page = MagicMock()
    mock_page.extract_text.return_value = fallback_text
    mock_reader.pages = [mock_page]

    with patch("pypdf.PdfReader", return_value=mock_reader):
        result = processor.process("fallback.pdf")

    assert "pages" in result
    assert "Fallback content" in result["pages"][0]["text"]


@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_single_page_not_chunked(mock_exists, mock_pdfplumber, processor):
    """Verify a short document is not chunked."""
    mock_pdfplumber.open.return_value = _mock_pdfplumber_pdf([
        (1, "Short content that is long enough to pass the scanned detection threshold in the processor heuristic.", []),
    ])

    result = processor.process("short.pdf")

    assert result["metadata"]["is_chunked"] is False
    assert len(result["chunks"]) == 1
    assert result["chunks"][0]["source_pages"] == [1, 1]


# ------------------------------------------------------------------ #
# OCR integration tests
# ------------------------------------------------------------------ #

# Text long enough to exceed 50-char scanned threshold after OCR
_OCR_TEXT = (
    "The Court hereby orders that custody of the minor child be awarded "
    "to the petitioner in accordance with the best interests of the child."
)


@patch("caselens.ocr.OcrEngine")
@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_scanned_pdf_with_ocr_available(mock_exists, mock_pdfplumber, mock_engine_cls, processor):
    """Scanned PDF + OCR available → success with ocr_applied metadata."""
    mock_pdfplumber.open.return_value = _mock_pdfplumber_pdf([
        (1, "", [{"x0": 0}]),
        (2, "", [{"x0": 0}]),
        (3, "", [{"x0": 0}]),
        (4, "", [{"x0": 0}]),
        (5, "", [{"x0": 0}]),
    ])

    mock_engine = MagicMock()
    mock_engine.check_availability.return_value = (True, "")
    mock_engine.ocr_pages.return_value = (
        {1: _OCR_TEXT, 2: _OCR_TEXT, 3: _OCR_TEXT, 4: _OCR_TEXT, 5: _OCR_TEXT},
        [],
    )
    mock_engine_cls.return_value = mock_engine

    result = processor.process("scanned.pdf")

    assert "error" not in result
    assert "pages" in result
    assert "chunks" in result
    assert result["metadata"]["ocr_applied"] is True
    assert result["metadata"]["ocr_pages"] == [1, 2, 3, 4, 5]
    assert _OCR_TEXT[:30] in result["pages"][0]["text"]


@patch("caselens.ocr.OcrEngine")
@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_scanned_pdf_ocr_unavailable(mock_exists, mock_pdfplumber, mock_engine_cls, processor):
    """Scanned PDF + OCR deps missing → ocr_unavailable error."""
    mock_pdfplumber.open.return_value = _mock_pdfplumber_pdf([
        (1, "", [{"x0": 0}]),
        (2, "", [{"x0": 0}]),
        (3, "", [{"x0": 0}]),
        (4, "", [{"x0": 0}]),
        (5, "", [{"x0": 0}]),
    ])

    mock_engine = MagicMock()
    mock_engine.check_availability.return_value = (False, "pymupdf is not installed")
    mock_engine_cls.return_value = mock_engine

    result = processor.process("scanned.pdf")

    assert result["error"] == "ocr_unavailable"
    assert "pymupdf" in result["message"]


@patch("caselens.ocr.OcrEngine")
@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_scanned_pdf_ocr_fails(mock_exists, mock_pdfplumber, mock_engine_cls, processor):
    """Scanned PDF + OCR crashes → ocr_failed error."""
    mock_pdfplumber.open.return_value = _mock_pdfplumber_pdf([
        (1, "", [{"x0": 0}]),
        (2, "", [{"x0": 0}]),
        (3, "", [{"x0": 0}]),
        (4, "", [{"x0": 0}]),
        (5, "", [{"x0": 0}]),
    ])

    mock_engine = MagicMock()
    mock_engine.check_availability.return_value = (True, "")
    mock_engine.ocr_pages.side_effect = RuntimeError("Tesseract crashed")
    mock_engine_cls.return_value = mock_engine

    result = processor.process("scanned.pdf")

    assert result["error"] == "ocr_failed"
    assert "Tesseract crashed" in result["message"]


@patch("caselens.ocr.OcrEngine")
@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_mixed_pdf_ocr_only_sparse_pages(mock_exists, mock_pdfplumber, mock_engine_cls, processor):
    """Mixed PDF: 4 scanned + 1 text (80% sparse triggers OCR), only sparse pages OCR'd."""
    text_content = (
        "This page has plenty of extracted text from the PDF. "
        "The court finds that the evidence supports the plaintiff's claim."
    )
    mock_pdfplumber.open.return_value = _mock_pdfplumber_pdf([
        (1, text_content, []),            # text page — >50 chars
        (2, "", [{"x0": 0}]),            # scanned page
        (3, "", [{"x0": 0}]),            # scanned page
        (4, "", [{"x0": 0}]),            # scanned page
        (5, "", [{"x0": 0}]),            # scanned page
    ])

    mock_engine = MagicMock()
    mock_engine.check_availability.return_value = (True, "")
    mock_engine.ocr_pages.return_value = (
        {2: _OCR_TEXT, 3: _OCR_TEXT, 4: _OCR_TEXT, 5: _OCR_TEXT},
        [],
    )
    mock_engine_cls.return_value = mock_engine

    result = processor.process("mixed.pdf")

    assert "error" not in result
    assert result["metadata"]["ocr_applied"] is True
    assert result["metadata"]["ocr_pages"] == [2, 3, 4, 5]
    # OCR should only have been called for pages 2-5 (the sparse ones)
    mock_engine.ocr_pages.assert_called_once_with("mixed.pdf", [2, 3, 4, 5])
    # Page 1 (text) should preserve original content
    assert "evidence supports" in result["pages"][0]["text"]


@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_text_pdf_no_ocr_metadata(mock_exists, mock_pdfplumber, processor):
    """Normal text PDF has no ocr_applied in metadata."""
    mock_pdfplumber.open.return_value = _mock_pdfplumber_pdf([
        (1, "First page content about the case that easily exceeds the scanned threshold.", []),
        (2, "Second page with more legal details and sufficient text length for detection.", []),
    ])

    result = processor.process("text.pdf")

    assert "error" not in result
    assert "ocr_applied" not in result["metadata"]


# ------------------------------------------------------------------ #
# Phase 9: Memory management + large PDF tests
# ------------------------------------------------------------------ #


@patch("os.path.getsize", return_value=1024)
@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_pdf_processor_rejects_over_max_pages(mock_exists, mock_pdfplumber, mock_getsize, processor):
    """PDFs over MAX_PAGES (500) are rejected with document_too_large error."""
    # Create a mock with 501 pages
    pages_data = [
        (i + 1, f"Page {i + 1} content that is long enough to pass the scanned threshold check.", [])
        for i in range(501)
    ]
    mock_pdfplumber.open.return_value = _mock_pdfplumber_pdf(pages_data)

    result = processor.process("huge.pdf")

    assert result["error"] == "document_too_large"
    assert "501" in result["message"]
    assert "500" in result["message"]


@patch("os.path.getsize", return_value=1024)
@patch("caselens.pdf_processor.gc")
@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_pdf_processor_batch_processing(mock_exists, mock_pdfplumber, mock_gc, mock_getsize, processor):
    """Large docs (>50 pages) are processed in batches with pdfplumber opened/closed per batch."""
    # Create 120 pages -> 3 batches: 50 + 50 + 20
    page_text = "Legal content for batch processing test that is definitely long enough to exceed the threshold."
    pages_data = [
        (i + 1, page_text, [])
        for i in range(120)
    ]
    mock_pdfplumber.open.return_value = _mock_pdfplumber_pdf(pages_data)

    result = processor.process("batched.pdf")

    assert "error" not in result
    assert result["metadata"]["total_pages"] == 120

    # pdfplumber.open called: 1x validate_pdf + 1x page count + 3x batches = 5
    assert mock_pdfplumber.open.call_count == 5

    # gc.collect() called between batches for >100 page files
    assert mock_gc.collect.call_count >= 2


@patch("os.path.getsize", return_value=1024)
@patch("caselens.pdf_processor.pdfplumber")
@patch("os.path.exists", return_value=True)
def test_memory_cleanup_reader_closed(mock_exists, mock_pdfplumber, mock_getsize, processor):
    """pdfplumber reader is explicitly closed (via context manager) after processing."""
    mock_pdf = _mock_pdfplumber_pdf([
        (1, "Content for testing memory cleanup that exceeds the scanned PDF detection threshold.", []),
    ])
    mock_pdfplumber.open.return_value = mock_pdf

    result = processor.process("cleanup.pdf")

    assert "error" not in result
    # Context manager __exit__ called for each open (validate_pdf + page count + 1 batch = 3)
    assert mock_pdf.__exit__.call_count == 3
