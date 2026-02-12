"""CanLII API client for fetching Quebec case law metadata and citator data."""

import logging
import os
import time
from typing import Optional

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_URL = "https://api.canlii.org/v1"
LANGUAGE = "en"
MAX_RESULTS_PER_PAGE = 10000
MIN_REQUEST_INTERVAL = 0.5  # seconds between requests (max 2 req/s)


def _load_env() -> None:
    """Load .env file if present."""
    load_dotenv()


class CanLIIClient:
    """Client for the CanLII REST API (v1).

    Handles case browsing, metadata retrieval, and citator lookups
    with built-in rate limiting to stay within CanLII's API limits.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        _load_env()
        self.api_key = api_key or os.getenv("CANLII_API_KEY")
        self._last_request_time: float = 0.0
        self._http = httpx.Client(timeout=30.0)

    def _ensure_key(self) -> Optional[dict]:
        """Return an error dict if the API key is not configured."""
        if not self.api_key:
            return {
                "error": "missing_api_key",
                "message": "CANLII_API_KEY is not set. Add it to your .env file.",
            }
        return None

    def _throttle(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _get(self, path: str, params: Optional[dict] = None) -> dict | list:
        """Make a GET request to the CanLII API.

        Returns parsed JSON on success, or ``{"error": str, "message": str}``
        on failure.
        """
        err = self._ensure_key()
        if err:
            return err

        self._throttle()

        url = f"{BASE_URL}{path}"
        all_params = {"api_key": self.api_key}
        if params:
            all_params.update(params)

        try:
            resp = self._http.get(url, params=all_params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("CanLII API error %s: %s", exc.response.status_code, path)
            return {
                "error": "api_error",
                "message": f"CanLII API returned {exc.response.status_code} for {path}",
            }
        except Exception as exc:
            logger.error("CanLII request failed: %s", exc)
            return {
                "error": "request_failed",
                "message": f"CanLII request failed: {exc}",
            }

    # -----------------------------------------------------------------
    # Case browsing
    # -----------------------------------------------------------------

    def list_databases(self) -> dict | list[dict]:
        """Fetch all available case databases.

        Returns:
            A list of database dicts (each with ``databaseId``, ``jurisdiction``, etc.)
            or an error dict.
        """
        return self._get(f"/caseBrowse/{LANGUAGE}/")

    def list_cases(self, database_id: str, offset: int = 0,
                   count: int = MAX_RESULTS_PER_PAGE,
                   decision_date_after: Optional[str] = None,
                   decision_date_before: Optional[str] = None) -> dict | list[dict]:
        """Fetch a page of cases from a database.

        Args:
            database_id: CanLII database identifier (e.g. ``"qccs"``).
            offset: Pagination offset.
            count: Number of results per page (max 10000).
            decision_date_after: Optional ``YYYY-MM-DD`` lower bound.
            decision_date_before: Optional ``YYYY-MM-DD`` upper bound.

        Returns:
            A list of case summary dicts or an error dict.
        """
        params: dict = {"offset": offset, "resultCount": count}
        if decision_date_after:
            params["decisionDateAfter"] = decision_date_after
        if decision_date_before:
            params["decisionDateBefore"] = decision_date_before

        return self._get(f"/caseBrowse/{LANGUAGE}/{database_id}/", params)

    def list_all_cases(self, database_id: str,
                       decision_date_after: Optional[str] = None,
                       decision_date_before: Optional[str] = None) -> dict | list[dict]:
        """Fetch all cases from a database, paginating automatically.

        Returns:
            A complete list of case summary dicts or an error dict.
        """
        all_cases: list[dict] = []
        offset = 0

        while True:
            page = self.list_cases(
                database_id, offset=offset, count=MAX_RESULTS_PER_PAGE,
                decision_date_after=decision_date_after,
                decision_date_before=decision_date_before,
            )
            if isinstance(page, dict) and "error" in page:
                return page

            if not page:
                break

            all_cases.extend(page)

            if len(page) < MAX_RESULTS_PER_PAGE:
                break
            offset += MAX_RESULTS_PER_PAGE

        return all_cases

    # -----------------------------------------------------------------
    # Case metadata
    # -----------------------------------------------------------------

    def get_case_metadata(self, database_id: str, case_id: str) -> dict:
        """Fetch full metadata for a single case.

        Args:
            database_id: CanLII database identifier.
            case_id: CanLII case identifier.

        Returns:
            A metadata dict or an error dict.
        """
        return self._get(f"/caseBrowse/{LANGUAGE}/{database_id}/{case_id}/")

    # -----------------------------------------------------------------
    # Citator
    # -----------------------------------------------------------------

    def get_cited_cases(self, database_id: str, case_id: str) -> dict | list[dict]:
        """Fetch cases cited by the given case."""
        result = self._get(
            f"/caseCitator/{LANGUAGE}/{database_id}/{case_id}/citedCases"
        )
        if isinstance(result, dict) and "error" in result:
            return result
        # CanLII wraps the list in {"citedCases": [...]}
        if isinstance(result, dict) and "citedCases" in result:
            return result["citedCases"]
        return result

    def get_citing_cases(self, database_id: str, case_id: str) -> dict | list[dict]:
        """Fetch cases that cite the given case."""
        result = self._get(
            f"/caseCitator/{LANGUAGE}/{database_id}/{case_id}/citingCases"
        )
        if isinstance(result, dict) and "error" in result:
            return result
        if isinstance(result, dict) and "citingCases" in result:
            return result["citingCases"]
        return result

    def get_cited_legislation(self, database_id: str, case_id: str) -> dict | list[dict]:
        """Fetch legislation cited by the given case."""
        result = self._get(
            f"/caseCitator/{LANGUAGE}/{database_id}/{case_id}/citedLegislations"
        )
        if isinstance(result, dict) and "error" in result:
            return result
        if isinstance(result, dict) and "citedLegislations" in result:
            return result["citedLegislations"]
        return result
