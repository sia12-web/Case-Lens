"""Tests for caselens.ocr — OcrEngine."""

from unittest.mock import MagicMock, patch, call

import pytest

from caselens.ocr import OcrEngine


# ------------------------------------------------------------------
# check_availability tests
# ------------------------------------------------------------------


@patch("caselens.ocr.pytesseract")
@patch("caselens.ocr.fitz", new_callable=lambda: MagicMock)
@patch("caselens.ocr.Image", new_callable=lambda: MagicMock)
@patch("shutil.which", return_value="/usr/bin/tesseract")
def test_ocr_check_availability_all_present(mock_which, _img, _fitz, _tess):
    """All deps installed and tesseract binary on PATH."""
    engine = OcrEngine()
    ok, msg = engine.check_availability()
    assert ok is True
    assert msg == ""


@patch("caselens.ocr.fitz", None)
def test_ocr_check_availability_no_pymupdf():
    """pymupdf not installed."""
    engine = OcrEngine()
    ok, msg = engine.check_availability()
    assert ok is False
    assert "pymupdf" in msg


@patch("caselens.ocr.Image", new_callable=lambda: MagicMock)
@patch("caselens.ocr.fitz", new_callable=lambda: MagicMock)
@patch("caselens.ocr.pytesseract", None)
def test_ocr_check_availability_no_pytesseract(_fitz, _img):
    """pytesseract not installed."""
    engine = OcrEngine()
    ok, msg = engine.check_availability()
    assert ok is False
    assert "pytesseract" in msg


@patch("caselens.ocr.pytesseract")
@patch("caselens.ocr.fitz", new_callable=lambda: MagicMock)
@patch("caselens.ocr.Image", None)
def test_ocr_check_availability_no_pillow(_fitz, _tess):
    """Pillow not installed."""
    engine = OcrEngine()
    ok, msg = engine.check_availability()
    assert ok is False
    assert "Pillow" in msg


@patch("caselens.ocr.Image", new_callable=lambda: MagicMock)
@patch("caselens.ocr.pytesseract")
@patch("caselens.ocr.fitz", new_callable=lambda: MagicMock)
@patch("shutil.which", return_value=None)
def test_ocr_check_availability_no_tesseract_binary(mock_which, _fitz, mock_tess, _img):
    """Tesseract binary not on PATH and version check fails."""
    mock_tess.get_tesseract_version.side_effect = RuntimeError("not found")
    engine = OcrEngine()
    ok, msg = engine.check_availability()
    assert ok is False
    assert "not installed or not on PATH" in msg


# ------------------------------------------------------------------
# ocr_pages tests
# ------------------------------------------------------------------


@patch("caselens.ocr.pytesseract")
@patch("caselens.ocr.Image")
@patch("caselens.ocr.fitz")
def test_ocr_pages_extracts_text(mock_fitz, mock_image, mock_tess):
    """Single page OCR returns extracted text."""
    # Mock fitz doc/page/pixmap chain
    mock_pixmap = MagicMock()
    mock_pixmap.tobytes.return_value = b"fake-png-bytes"

    mock_page = MagicMock()
    mock_page.get_pixmap.return_value = mock_pixmap

    mock_doc = MagicMock()
    mock_doc.__getitem__ = MagicMock(return_value=mock_page)
    mock_fitz.open.return_value = mock_doc

    # Mock PIL Image.open
    mock_pil_img = MagicMock()
    mock_image.open.return_value = mock_pil_img

    # Mock tesseract
    mock_tess.image_to_string.return_value = "  OCR extracted legal text from the scanned document  "

    engine = OcrEngine()
    result = engine.ocr_pages("test.pdf", [1])

    assert result == {1: "OCR extracted legal text from the scanned document"}
    mock_fitz.open.assert_called_once_with("test.pdf")
    mock_doc.__getitem__.assert_called_once_with(0)  # 1-based → 0-based
    mock_doc.close.assert_called_once()


@patch("caselens.ocr.pytesseract")
@patch("caselens.ocr.Image")
@patch("caselens.ocr.fitz")
def test_ocr_pages_multiple_pages(mock_fitz, mock_image, mock_tess):
    """OCR multiple pages returns text for each."""
    mock_pixmap = MagicMock()
    mock_pixmap.tobytes.return_value = b"fake-png"

    mock_page = MagicMock()
    mock_page.get_pixmap.return_value = mock_pixmap

    mock_doc = MagicMock()
    mock_doc.__getitem__ = MagicMock(return_value=mock_page)
    mock_fitz.open.return_value = mock_doc

    mock_image.open.return_value = MagicMock()

    call_count = 0
    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return f"Text from page {call_count}"

    mock_tess.image_to_string.side_effect = side_effect

    engine = OcrEngine()
    result = engine.ocr_pages("multi.pdf", [1, 3, 5])

    assert len(result) == 3
    assert 1 in result and 3 in result and 5 in result
    # Verify 0-based page indices: pages 1,3,5 → indices 0,2,4
    calls = mock_doc.__getitem__.call_args_list
    assert calls == [call(0), call(2), call(4)]


@patch("caselens.ocr.pytesseract")
@patch("caselens.ocr.Image")
@patch("caselens.ocr.fitz")
def test_ocr_pages_closes_doc_on_error(mock_fitz, mock_image, mock_tess):
    """Document is closed even when OCR raises an exception."""
    mock_page = MagicMock()
    mock_page.get_pixmap.side_effect = RuntimeError("render failed")

    mock_doc = MagicMock()
    mock_doc.__getitem__ = MagicMock(return_value=mock_page)
    mock_fitz.open.return_value = mock_doc

    engine = OcrEngine()
    with pytest.raises(RuntimeError, match="render failed"):
        engine.ocr_pages("bad.pdf", [1])

    mock_doc.close.assert_called_once()


@patch("caselens.ocr.pytesseract")
@patch("caselens.ocr.Image")
@patch("caselens.ocr.fitz")
def test_ocr_engine_custom_dpi_and_language(mock_fitz, mock_image, mock_tess):
    """Custom DPI and language are passed through correctly."""
    mock_pixmap = MagicMock()
    mock_pixmap.tobytes.return_value = b"png"

    mock_page = MagicMock()
    mock_page.get_pixmap.return_value = mock_pixmap

    mock_doc = MagicMock()
    mock_doc.__getitem__ = MagicMock(return_value=mock_page)
    mock_fitz.open.return_value = mock_doc

    mock_image.open.return_value = MagicMock()
    mock_tess.image_to_string.return_value = "texte en francais"

    engine = OcrEngine(dpi=600, language="fra")
    engine.ocr_pages("french.pdf", [1])

    # Verify DPI: zoom = 600/72 ≈ 8.333
    mock_fitz.Matrix.assert_called_once_with(600 / 72, 600 / 72)
    # Verify language
    mock_tess.image_to_string.assert_called_once()
    _, kwargs = mock_tess.image_to_string.call_args
    assert kwargs["lang"] == "fra"
