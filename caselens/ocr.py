"""OCR engine for extracting text from scanned/image-based PDF pages."""

import io
import logging
import shutil

logger = logging.getLogger(__name__)

# Guarded imports — OCR dependencies are optional.
try:
    import fitz  # pymupdf
except ImportError:
    fitz = None  # type: ignore[assignment]

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore[assignment]

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment]


class OcrEngine:
    """Extracts text from scanned PDF pages using Tesseract OCR via PyMuPDF.

    Renders each requested page to a PNG at the configured DPI, then
    passes the image to Tesseract for text recognition.

    Usage::

        engine = OcrEngine()
        ok, msg = engine.check_availability()
        if ok:
            texts = engine.ocr_pages("doc.pdf", [1, 3, 5])
    """

    DEFAULT_DPI: int = 300
    DEFAULT_LANGUAGE: str = "eng"

    def __init__(self, *, dpi: int = DEFAULT_DPI, language: str = DEFAULT_LANGUAGE):
        self.dpi = dpi
        self.language = language

    def check_availability(self) -> tuple[bool, str]:
        """Check whether OCR dependencies are installed and functional.

        Returns:
            ``(True, "")`` on success, ``(False, reason)`` on failure.
        """
        if fitz is None:
            return False, (
                "pymupdf is not installed. "
                "Install it with: python -m pip install pymupdf"
            )
        if pytesseract is None:
            return False, (
                "pytesseract is not installed. "
                "Install it with: python -m pip install pytesseract"
            )
        if Image is None:
            return False, (
                "Pillow is not installed. "
                "Install it with: python -m pip install Pillow"
            )
        # Check tesseract binary reachability
        if not shutil.which("tesseract"):
            try:
                pytesseract.get_tesseract_version()
            except Exception:
                return False, (
                    "Tesseract OCR is not installed or not on PATH. "
                    "Install via: conda install -c conda-forge tesseract "
                    "or download from https://github.com/tesseract-ocr/tesseract"
                )
        return True, ""

    def ocr_pages(self, filepath: str, page_numbers: list[int]) -> dict[int, str]:
        """OCR specified pages and return extracted text.

        Args:
            filepath: Path to the PDF file.
            page_numbers: 1-based page numbers to OCR.

        Returns:
            Mapping of page_number to extracted text string.
        """
        results: dict[int, str] = {}
        doc = fitz.open(filepath)
        try:
            for page_num in page_numbers:
                page = doc[page_num - 1]  # fitz is 0-based
                zoom = self.dpi / 72  # PDF default is 72 DPI
                matrix = fitz.Matrix(zoom, zoom)
                pixmap = page.get_pixmap(matrix=matrix)
                img_bytes = pixmap.tobytes("png")
                image = Image.open(io.BytesIO(img_bytes))
                text = pytesseract.image_to_string(image, lang=self.language)
                results[page_num] = text.strip()
                logger.debug(
                    "OCR page %d: %d chars extracted",
                    page_num,
                    len(results[page_num]),
                )
        finally:
            doc.close()
        return results
