"""PDF text extraction, cleaning, and chunking for legal documents."""

import gc
import os
import re
import logging
from typing import Optional

import pdfplumber

logger = logging.getLogger(__name__)


class PasswordProtectedError(Exception):
    """Raised when a PDF is password-protected."""


class PdfProcessor:
    """Extracts, cleans, and chunks text from legal PDF files.

    Primary extractor: pdfplumber
    Fallback extractor: pypdf

    Usage::

        processor = PdfProcessor()
        result = processor.process("path/to/document.pdf")
    """

    MAX_CHUNK_SIZE: int = 80_000
    CHUNK_OVERLAP: int = 500
    SCANNED_MIN_CHARS_PER_PAGE: int = 50
    SCANNED_PAGE_RATIO: float = 0.80
    MAX_PAGES: int = 500
    BATCH_SIZE: int = 50

    # Text cleaning patterns applied in order: (compiled_regex, replacement)
    CLEANING_PATTERNS: list[tuple[re.Pattern, str]] = [
        # 1. Bates stamps: PREFIX-###### (2-10 letter prefix, 6-10 digits)
        (re.compile(r'\b[A-Z]{2,10}[-\s]\d{6,10}\b'), ''),

        # 2. Page numbers: standalone lines like "42", "Page 5", "- 12 -"
        (re.compile(
            r'^\s*[-\u2013\u2014]?\s*'
            r'(?:[Pp]age\s+)?'
            r'\d{1,5}'
            r'(?:\s+(?:of|de|sur)\s+\d{1,5})?'
            r'\s*[-\u2013\u2014]?\s*$',
            re.MULTILINE,
        ), ''),

        # 3. Confidentiality footers (English)
        (re.compile(
            r'^\s*(?:PRIVILEGED\s+AND\s+)?CONFIDENTIAL(?:\s*[-\u2013\u2014]\s*.*)?$'
            r'|^\s*ATTORNEY[\s-]CLIENT\s+PRIVILEGE[D]?\s*$'
            r'|^\s*ATTORNEY\s+WORK\s+PRODUCT\s*$'
            r'|^\s*DO\s+NOT\s+DISTRIBUTE\s*$'
            r'|^\s*FOR\s+SETTLEMENT\s+PURPOSES\s+ONLY\s*$',
            re.MULTILINE | re.IGNORECASE,
        ), ''),

        # 4. Confidentiality footers (French)
        (re.compile(
            r'^\s*CONFIDENTIEL(?:LE)?\s*$'
            r'|^\s*PROT[E\u00c9]G[E\u00c9]?\s+PAR\s+LE\s+SECRET\s+PROFESSIONNEL\s*$'
            r'|^\s*NE\s+PAS\s+DISTRIBUER\s*$',
            re.MULTILINE | re.IGNORECASE,
        ), ''),

        # 5. Separator lines (===, ---, ___)
        (re.compile(r'^\s*[=_\-]{3,}\s*$', re.MULTILINE), ''),

        # 6. Form feed characters
        (re.compile(r'\f'), ''),

        # 7. Collapse 3+ newlines into 2
        (re.compile(r'\n{3,}'), '\n\n'),

        # 8. Strip trailing whitespace per line
        (re.compile(r'[ \t]+$', re.MULTILINE), ''),
    ]

    def process(self, filepath: str) -> dict:
        """Extract, clean, and chunk text from a PDF file.

        Args:
            filepath: Path to the PDF file.

        Returns:
            On success::

                {
                    "pages": [{"page_number": int, "text": str}, ...],
                    "chunks": [{"chunk_index": int, "text": str,
                                "char_count": int, "source_pages": [int, int]}, ...],
                    "metadata": {"total_pages": int, "filename": str, "is_chunked": bool}
                }

            On error::

                {"error": str, "message": str}
        """
        # Validate
        error = self._validate_file(filepath)
        if error:
            return error

        # Quick page-count check before full extraction
        validation = self.validate_pdf(filepath)
        if "error" in validation:
            # Block on encryption; other validation errors → try extraction anyway
            if validation["error"] == "protected_pdf":
                return validation
        elif validation["page_count"] > self.MAX_PAGES:
            return {
                "error": "document_too_large",
                "message": (
                    f"Document has {validation['page_count']} pages. "
                    f"Maximum {self.MAX_PAGES} pages allowed."
                ),
            }

        # Extract
        pages = None
        try:
            pages = self._extract_with_pdfplumber(filepath)
        except Exception as pdfplumber_err:
            # Check for password-protected before falling back
            if _is_encryption_error(pdfplumber_err):
                return {
                    "error": "protected_pdf",
                    "message": "PDF is password-protected and cannot be processed.",
                }
            # Fallback to pypdf
            try:
                pages = self._extract_with_pypdf(filepath)
            except PasswordProtectedError:
                return {
                    "error": "protected_pdf",
                    "message": "PDF is password-protected and cannot be processed.",
                }
            except Exception as fallback_err:
                return {
                    "error": "extraction_failed",
                    "message": f"Failed to extract text: {fallback_err}",
                }

        logger.info("Extracted %d pages from %s", len(pages), os.path.basename(filepath))

        # Detect scanned/image PDF — attempt OCR on sparse pages
        ocr_info: dict = {"ocr_applied": False, "ocr_pages": []}
        if self._detect_scanned(pages):
            ocr_info = self._attempt_ocr(filepath, pages)
            if "error" in ocr_info:
                return ocr_info

        # Clean
        for page in pages:
            page["cleaned_text"] = self._clean_text(page["raw_text"])

        # Chunk
        chunks = self._chunk_pages(pages)

        return self._build_result(pages, chunks, filepath, ocr_info)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_file(self, filepath: str) -> Optional[dict]:
        """Return an error dict if the file is invalid, else None."""
        if not os.path.exists(filepath):
            return {"error": "file_not_found", "message": f"File not found: {filepath}"}
        if not filepath.lower().endswith(".pdf"):
            return {"error": "invalid_format", "message": "File is not a PDF."}
        return None

    def validate_pdf(self, filepath: str) -> dict:
        """Open PDF, read page count and file size, close immediately.

        Returns:
            On success: ``{"page_count": int, "file_size_mb": float}``
            On error: ``{"error": str, "message": str}``
        """
        try:
            file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
            with pdfplumber.open(filepath) as pdf:
                page_count = len(pdf.pages)
            return {"page_count": page_count, "file_size_mb": round(file_size_mb, 2)}
        except Exception as e:
            if _is_encryption_error(e):
                return {
                    "error": "protected_pdf",
                    "message": "PDF is password-protected and cannot be processed.",
                }
            return {
                "error": "validation_failed",
                "message": f"Failed to validate PDF: {e}",
            }

    def _extract_with_pdfplumber(self, filepath: str) -> list[dict]:
        """Primary extraction using pdfplumber, processing in batches.

        Opens and closes the reader per batch to limit memory usage.
        Calls gc.collect() between batches for large files (100+ pages).
        """
        # First pass: get total page count
        with pdfplumber.open(filepath) as pdf:
            total_pages = len(pdf.pages)

        pages: list[dict] = []
        use_gc = total_pages > 100

        for batch_start in range(0, total_pages, self.BATCH_SIZE):
            batch_end = min(batch_start + self.BATCH_SIZE, total_pages)
            with pdfplumber.open(filepath) as pdf:
                for i in range(batch_start, batch_end):
                    page = pdf.pages[i]
                    text = page.extract_text() or ""
                    has_images = len(page.images) > 0
                    pages.append({
                        "page_number": page.page_number,
                        "raw_text": text,
                        "has_images": has_images,
                    })

            if use_gc:
                gc.collect()

        return pages

    def _extract_with_pypdf(self, filepath: str) -> list[dict]:
        """Fallback extraction using pypdf."""
        from pypdf import PdfReader  # lazy import — fallback only

        reader = PdfReader(filepath)
        if reader.is_encrypted:
            raise PasswordProtectedError("PDF is encrypted.")

        pages: list[dict] = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append({
                "page_number": i + 1,
                "raw_text": text,
                "has_images": False,
            })
        return pages

    def _detect_scanned(self, pages: list[dict]) -> bool:
        """Heuristic: most pages yield very little text."""
        if not pages:
            return False
        sparse = sum(
            1 for p in pages
            if len(p["raw_text"].strip()) < self.SCANNED_MIN_CHARS_PER_PAGE
        )
        return (sparse / len(pages)) >= self.SCANNED_PAGE_RATIO

    def _attempt_ocr(self, filepath: str, pages: list[dict]) -> dict:
        """Try OCR on sparse pages. Mutates *pages* in-place on success.

        Returns:
            On success: ``{"ocr_applied": True, "ocr_pages": [1, 3, 5]}``
            On failure: error dict ``{"error": str, "message": str, ...}``
        """
        from caselens import ocr

        engine = ocr.OcrEngine()
        available, reason = engine.check_availability()

        if not available:
            return {
                "error": "ocr_unavailable",
                "message": (
                    "PDF appears to be scanned/image-based and requires OCR, "
                    f"but OCR is not available: {reason}"
                ),
                "metadata": {
                    "total_pages": len(pages),
                    "filename": os.path.basename(filepath),
                },
            }

        # Identify sparse pages that need OCR
        sparse_page_nums = [
            p["page_number"]
            for p in pages
            if len(p["raw_text"].strip()) < self.SCANNED_MIN_CHARS_PER_PAGE
        ]

        if not sparse_page_nums:
            return {"ocr_applied": False, "ocr_pages": []}

        try:
            ocr_texts, skipped_pages = engine.ocr_pages(filepath, sparse_page_nums)
        except Exception as e:
            logger.warning("OCR failed: %s", e)
            return {
                "error": "ocr_failed",
                "message": f"OCR processing failed: {e}",
                "metadata": {
                    "total_pages": len(pages),
                    "filename": os.path.basename(filepath),
                },
            }

        # Replace raw_text for OCR'd pages
        page_map = {p["page_number"]: p for p in pages}
        for page_num, text in ocr_texts.items():
            if page_num in page_map:
                page_map[page_num]["raw_text"] = text

        ocr_page_nums = list(ocr_texts.keys())
        logger.info("OCR applied to %d pages: %s", len(ocr_page_nums), ocr_page_nums)

        result: dict = {"ocr_applied": True, "ocr_pages": ocr_page_nums}
        if skipped_pages:
            result["ocr_warning"] = (
                f"Only first {engine.MAX_OCR_PAGES} pages OCR'd. "
                f"Remaining {len(skipped_pages)} pages skipped."
            )
        return result

    def _clean_text(self, text: str) -> str:
        """Apply the cleaning pipeline to a single page's text."""
        if not text:
            return ""
        for pattern, replacement in self.CLEANING_PATTERNS:
            text = pattern.sub(replacement, text)
        return text.strip()

    def _chunk_pages(self, pages: list[dict]) -> list[dict]:
        """Split cleaned page texts into overlapping chunks."""
        # Build full text and track page boundary offsets
        full_text = ""
        page_boundaries: list[tuple[int, int]] = []  # (char_offset, page_number)

        for page in pages:
            page_boundaries.append((len(full_text), page["page_number"]))
            full_text += page["cleaned_text"] + "\n\n"

        full_text = full_text.rstrip()
        if not full_text:
            return []

        # Single chunk — fits within limit
        if len(full_text) <= self.MAX_CHUNK_SIZE:
            return [{
                "chunk_index": 0,
                "text": full_text,
                "char_count": len(full_text),
                "source_pages": [pages[0]["page_number"], pages[-1]["page_number"]],
            }]

        # Multi-chunk splitting
        chunks: list[dict] = []
        pos = 0
        chunk_index = 0

        while pos < len(full_text):
            end = pos + self.MAX_CHUNK_SIZE

            if end >= len(full_text):
                chunk_text = full_text[pos:].strip()
                if chunk_text:
                    chunks.append({
                        "chunk_index": chunk_index,
                        "text": chunk_text,
                        "char_count": len(chunk_text),
                        "source_pages": self._find_source_pages(pos, len(full_text), page_boundaries),
                    })
                break

            break_point = self._find_break_point(full_text, pos, end)
            chunk_text = full_text[pos:break_point].strip()

            if chunk_text:
                chunks.append({
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                    "char_count": len(chunk_text),
                    "source_pages": self._find_source_pages(pos, break_point, page_boundaries),
                })
                chunk_index += 1

            # Advance with overlap, ensuring forward progress
            new_pos = break_point - self.CHUNK_OVERLAP
            if new_pos <= pos:
                new_pos = break_point
            pos = new_pos

        return chunks

    def _find_break_point(self, text: str, start: int, end: int) -> int:
        """Find the best break point near *end*, preferring natural boundaries."""
        search_start = max(start, end - 2000)
        region = text[search_start:end]

        # Prefer paragraph break
        para_idx = region.rfind('\n\n')
        if para_idx != -1:
            return search_start + para_idx + 2

        # Prefer sentence break (period + space + uppercase, including accented)
        sentence_re = re.compile(r'\.\s+(?=[A-Z\u00C0-\u00DC])')
        matches = list(sentence_re.finditer(region))
        if matches:
            return search_start + matches[-1].end()

        # Hard break
        return end

    @staticmethod
    def _find_source_pages(
        start: int, end: int, page_boundaries: list[tuple[int, int]]
    ) -> list[int]:
        """Map a character range to [first_page, last_page]."""
        first_page = page_boundaries[0][1]
        last_page = page_boundaries[-1][1]

        for offset, page_num in page_boundaries:
            if offset <= start:
                first_page = page_num
            if offset < end:
                last_page = page_num

        return [first_page, last_page]

    @staticmethod
    def _build_result(
        pages: list[dict],
        chunks: list[dict],
        filepath: str,
        ocr_info: Optional[dict] = None,
    ) -> dict:
        """Assemble the final output dictionary."""
        metadata: dict = {
            "total_pages": len(pages),
            "filename": os.path.basename(filepath),
            "is_chunked": len(chunks) > 1,
        }
        if ocr_info and ocr_info.get("ocr_applied"):
            metadata["ocr_applied"] = True
            metadata["ocr_pages"] = ocr_info.get("ocr_pages", [])
            if ocr_info.get("ocr_warning"):
                metadata["ocr_warning"] = ocr_info["ocr_warning"]

        return {
            "pages": [
                {"page_number": p["page_number"], "text": p["cleaned_text"]}
                for p in pages
            ],
            "chunks": chunks,
            "metadata": metadata,
        }


def _is_encryption_error(exc: Exception) -> bool:
    """Check if an exception is a PDF encryption error (pdfminer)."""
    try:
        from pdfminer.pdfdocument import PDFEncryptionError
        return isinstance(exc, PDFEncryptionError)
    except ImportError:
        return "encrypt" in str(exc).lower()
