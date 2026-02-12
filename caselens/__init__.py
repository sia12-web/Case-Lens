"""Case Lens — Legal PDF processing and analysis."""

from caselens.pdf_processor import PdfProcessor
from caselens.summarizer import Summarizer
from caselens.ocr import OcrEngine
from caselens.embeddings import EmbeddingEngine
from caselens.database import CaseDatabase
from caselens.canlii import CanLIIClient
from caselens.ingest import CaseIngester

__all__ = [
    "PdfProcessor", "Summarizer", "OcrEngine",
    "EmbeddingEngine", "CaseDatabase",
    "CanLIIClient", "CaseIngester",
]
__version__ = "0.11.0"
