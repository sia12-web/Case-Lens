"""Embedding generation for legal document similarity search."""

import logging
import os
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Voyage-3 produces 1024-dimensional vectors
EMBEDDING_DIM = 1024
VOYAGE_MODEL = "voyage-3"
OPENAI_MODEL = "text-embedding-3-small"
OPENAI_DIM = 1024  # request 1024 dims from OpenAI for consistency

# Guarded imports — engine selection at init time
try:
    import voyageai
except ImportError:
    voyageai = None

try:
    import openai
except ImportError:
    openai = None


def _load_env() -> None:
    """Load .env file if present."""
    load_dotenv()


class EmbeddingEngine:
    """Generate text embeddings using Voyage AI (primary) or OpenAI (fallback).

    Both engines produce 1024-dimensional vectors for storage in pgvector.
    """

    def __init__(self, voyage_api_key: Optional[str] = None,
                 openai_api_key: Optional[str] = None) -> None:
        _load_env()
        self.voyage_api_key = voyage_api_key or os.getenv("VOYAGE_API_KEY")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.engine: Optional[str] = None
        self._voyage_client = None
        self._openai_client = None

        # Try Voyage first, then OpenAI
        if voyageai and self.voyage_api_key:
            self.engine = "voyage"
            self._voyage_client = voyageai.Client(api_key=self.voyage_api_key)
        elif openai and self.openai_api_key:
            self.engine = "openai"
            self._openai_client = openai.OpenAI(api_key=self.openai_api_key)

    def generate(self, text: str) -> dict | list[float]:
        """Generate a single embedding vector.

        Args:
            text: The text to embed.

        Returns:
            A list of floats (1024 dimensions) on success,
            or ``{"error": str, "message": str}`` on failure.
        """
        if not self.engine:
            return {
                "error": "missing_api_key",
                "message": (
                    "No embedding API key found. "
                    "Set VOYAGE_API_KEY or OPENAI_API_KEY in your .env file."
                ),
            }

        try:
            if self.engine == "voyage":
                result = self._voyage_client.embed(
                    [text], model=VOYAGE_MODEL, input_type="document"
                )
                return result.embeddings[0]
            else:
                result = self._openai_client.embeddings.create(
                    input=[text],
                    model=OPENAI_MODEL,
                    dimensions=OPENAI_DIM,
                )
                return result.data[0].embedding
        except Exception as exc:
            logger.error("Embedding generation failed: %s", exc)
            return {
                "error": "embedding_failed",
                "message": f"Embedding generation failed: {exc}",
            }

    def generate_batch(self, texts: list[str]) -> dict | list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            A list of embedding vectors on success,
            or ``{"error": str, "message": str}`` on failure.
        """
        if not texts:
            return []

        if not self.engine:
            return {
                "error": "missing_api_key",
                "message": (
                    "No embedding API key found. "
                    "Set VOYAGE_API_KEY or OPENAI_API_KEY in your .env file."
                ),
            }

        try:
            if self.engine == "voyage":
                result = self._voyage_client.embed(
                    texts, model=VOYAGE_MODEL, input_type="document"
                )
                return result.embeddings
            else:
                result = self._openai_client.embeddings.create(
                    input=texts,
                    model=OPENAI_MODEL,
                    dimensions=OPENAI_DIM,
                )
                return [item.embedding for item in result.data]
        except Exception as exc:
            logger.error("Batch embedding failed: %s", exc)
            return {
                "error": "embedding_failed",
                "message": f"Batch embedding failed: {exc}",
            }
