"""Supabase database client for case law storage and retrieval."""

import logging
import os
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None


def _load_env() -> None:
    """Load .env file if present."""
    load_dotenv()


class CaseDatabase:
    """Client for storing and querying Quebec case law in Supabase with pgvector."""

    def __init__(self, supabase_url: Optional[str] = None,
                 supabase_key: Optional[str] = None) -> None:
        _load_env()
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_KEY")
        self._client: Optional["Client"] = None

        if create_client is None:
            return  # SDK not installed — methods will return error dicts

        if self.supabase_url and self.supabase_key:
            self._client = create_client(self.supabase_url, self.supabase_key)

    def _ensure_client(self) -> Optional[dict]:
        """Return an error dict if the client is not configured, else None."""
        if create_client is None:
            return {
                "error": "missing_dependency",
                "message": "supabase package is not installed. Run: pip install supabase",
            }
        if not self._client:
            return {
                "error": "missing_config",
                "message": (
                    "Supabase not configured. "
                    "Set SUPABASE_URL and SUPABASE_KEY in your .env file."
                ),
            }
        return None

    def store_case(self, case_data: dict) -> dict | str:
        """Insert or upsert a case into the database.

        Args:
            case_data: Dict with case fields (must include ``canlii_id``).
                       May include ``embedding`` as a list of floats.

        Returns:
            The case UUID (str) on success, or ``{"error": str, "message": str}``.
        """
        err = self._ensure_client()
        if err:
            return err

        if "canlii_id" not in case_data:
            return {
                "error": "missing_field",
                "message": "case_data must include 'canlii_id'.",
            }

        try:
            result = (
                self._client.table("cases")
                .upsert(case_data, on_conflict="canlii_id")
                .execute()
            )
            return result.data[0]["id"]
        except Exception as exc:
            logger.error("Failed to store case: %s", exc)
            return {
                "error": "database_error",
                "message": f"Failed to store case: {exc}",
            }

    def search_similar(self, query_embedding: list[float],
                       limit: int = 20) -> dict | list[dict]:
        """Find cases similar to the query embedding using cosine similarity.

        Calls the ``match_cases`` RPC function defined in the migration.

        Args:
            query_embedding: 1024-dimensional embedding vector.
            limit: Maximum number of results to return.

        Returns:
            A list of dicts with ``id``, ``title``, ``citation``, ``similarity``
            on success, or ``{"error": str, "message": str}``.
        """
        err = self._ensure_client()
        if err:
            return err

        try:
            result = self._client.rpc(
                "match_cases",
                {"query_embedding": query_embedding, "match_count": limit},
            ).execute()
            return result.data
        except Exception as exc:
            logger.error("Similarity search failed: %s", exc)
            return {
                "error": "database_error",
                "message": f"Similarity search failed: {exc}",
            }

    def get_case(self, case_id: str) -> dict:
        """Retrieve a single case by its UUID.

        Args:
            case_id: The UUID of the case.

        Returns:
            The case dict on success, or ``{"error": str, "message": str}``.
        """
        err = self._ensure_client()
        if err:
            return err

        try:
            result = (
                self._client.table("cases")
                .select("*")
                .eq("id", case_id)
                .execute()
            )
            if not result.data:
                return {
                    "error": "not_found",
                    "message": f"No case found with id '{case_id}'.",
                }
            return result.data[0]
        except Exception as exc:
            logger.error("Failed to retrieve case: %s", exc)
            return {
                "error": "database_error",
                "message": f"Failed to retrieve case: {exc}",
            }

    def get_cases_citing(self, case_id: str) -> dict | list[dict]:
        """Get cases that cite the given case.

        Reads the ``citing_cases`` JSONB field from the target case.

        Args:
            case_id: The UUID of the case.

        Returns:
            A list of citation dicts, or ``{"error": str, "message": str}``.
        """
        err = self._ensure_client()
        if err:
            return err

        try:
            result = (
                self._client.table("cases")
                .select("citing_cases")
                .eq("id", case_id)
                .execute()
            )
            if not result.data:
                return {
                    "error": "not_found",
                    "message": f"No case found with id '{case_id}'.",
                }
            return result.data[0].get("citing_cases", [])
        except Exception as exc:
            logger.error("Failed to get citing cases: %s", exc)
            return {
                "error": "database_error",
                "message": f"Failed to get citing cases: {exc}",
            }

    def get_cases_cited_by(self, case_id: str) -> dict | list[dict]:
        """Get cases cited by the given case.

        Reads the ``cited_cases`` JSONB field from the target case.

        Args:
            case_id: The UUID of the case.

        Returns:
            A list of citation dicts, or ``{"error": str, "message": str}``.
        """
        err = self._ensure_client()
        if err:
            return err

        try:
            result = (
                self._client.table("cases")
                .select("cited_cases")
                .eq("id", case_id)
                .execute()
            )
            if not result.data:
                return {
                    "error": "not_found",
                    "message": f"No case found with id '{case_id}'.",
                }
            return result.data[0].get("cited_cases", [])
        except Exception as exc:
            logger.error("Failed to get cited cases: %s", exc)
            return {
                "error": "database_error",
                "message": f"Failed to get cited cases: {exc}",
            }
