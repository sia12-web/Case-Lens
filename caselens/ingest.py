"""Ingestion pipeline for fetching CanLII cases and storing them in Supabase."""

import logging
from typing import Optional

from caselens.canlii import CanLIIClient
from caselens.database import CaseDatabase
from caselens.embeddings import EmbeddingEngine

logger = logging.getLogger(__name__)


class CaseIngester:
    """Fetches cases from CanLII, generates embeddings, and stores in Supabase.

    Supports resuming — cases already in Supabase (by canlii_id) are skipped.
    """

    def __init__(self, canlii: CanLIIClient, db: CaseDatabase,
                 embedder: EmbeddingEngine) -> None:
        self.canlii = canlii
        self.db = db
        self.embedder = embedder

    def ingest_database(self, database_id: str,
                        date_after: Optional[str] = None,
                        date_before: Optional[str] = None,
                        batch_size: int = 100) -> dict:
        """Ingest all cases from a CanLII database into Supabase.

        Args:
            database_id: CanLII database identifier (e.g. ``"qccs"``).
            date_after: Optional ``YYYY-MM-DD`` lower bound.
            date_before: Optional ``YYYY-MM-DD`` upper bound.
            batch_size: Log progress every *batch_size* cases.

        Returns:
            Stats dict: ``{"total", "ingested", "skipped", "errors"}``.
        """
        logger.info("Fetching case list for %s...", database_id)
        cases = self.canlii.list_all_cases(
            database_id,
            decision_date_after=date_after,
            decision_date_before=date_before,
        )

        if isinstance(cases, dict) and "error" in cases:
            logger.error("Failed to list cases: %s", cases["message"])
            return {"total": 0, "ingested": 0, "skipped": 0, "errors": 1,
                    "error_details": cases}

        total = len(cases)
        logger.info("Found %d cases in %s", total, database_id)

        stats = {"total": total, "ingested": 0, "skipped": 0, "errors": 0}

        for i, case_summary in enumerate(cases):
            case_id = case_summary.get("caseId", {})
            if isinstance(case_id, dict):
                case_id_str = case_id.get("en", "")
            else:
                case_id_str = str(case_id)

            if not case_id_str:
                stats["errors"] += 1
                continue

            # Build the canlii_id used for deduplication
            canlii_id = f"{database_id}/{case_id_str}"

            # Check if already ingested (by querying Supabase)
            existing = self._check_existing(canlii_id)
            if existing:
                stats["skipped"] += 1
                if (i + 1) % batch_size == 0:
                    logger.info(
                        "Progress: %d/%d (ingested=%d, skipped=%d, errors=%d)",
                        i + 1, total, stats["ingested"], stats["skipped"], stats["errors"],
                    )
                continue

            # Process and store
            result = self._process_case(database_id, case_id_str, case_summary)
            if isinstance(result, dict) and "error" in result:
                stats["errors"] += 1
                logger.warning("Failed to process %s: %s", canlii_id, result["message"])
            else:
                stats["ingested"] += 1

            if (i + 1) % batch_size == 0:
                logger.info(
                    "Progress: %d/%d (ingested=%d, skipped=%d, errors=%d)",
                    i + 1, total, stats["ingested"], stats["skipped"], stats["errors"],
                )

        logger.info(
            "Done: %d total, %d ingested, %d skipped, %d errors",
            stats["total"], stats["ingested"], stats["skipped"], stats["errors"],
        )
        return stats

    def _check_existing(self, canlii_id: str) -> bool:
        """Return True if a case with this canlii_id already exists in Supabase."""
        try:
            result = (
                self.db._client.table("cases")
                .select("id")
                .eq("canlii_id", canlii_id)
                .execute()
            )
            return bool(result.data)
        except Exception:
            return False

    def _process_case(self, database_id: str, case_id: str,
                      case_summary: dict) -> dict | str:
        """Fetch metadata + citator, generate embedding, store in Supabase.

        Returns the stored UUID on success or an error dict on failure.
        """
        # Fetch full metadata
        metadata = self.canlii.get_case_metadata(database_id, case_id)
        if isinstance(metadata, dict) and "error" in metadata:
            return metadata

        # Fetch citator data (failures are non-fatal — store empty lists)
        cited_cases = self.canlii.get_cited_cases(database_id, case_id)
        if isinstance(cited_cases, dict) and "error" in cited_cases:
            cited_cases = []

        citing_cases = self.canlii.get_citing_cases(database_id, case_id)
        if isinstance(citing_cases, dict) and "error" in citing_cases:
            citing_cases = []

        cited_legislation = self.canlii.get_cited_legislation(database_id, case_id)
        if isinstance(cited_legislation, dict) and "error" in cited_legislation:
            cited_legislation = []

        # Build text for embedding
        embedding_text = self._build_embedding_text(
            metadata, cited_cases, cited_legislation
        )

        # Generate embedding
        embedding = self.embedder.generate(embedding_text)
        if isinstance(embedding, dict) and "error" in embedding:
            return embedding

        # Build case record
        canlii_id = f"{database_id}/{case_id}"
        case_data = {
            "canlii_id": canlii_id,
            "database_id": database_id,
            "title": metadata.get("title", ""),
            "citation": metadata.get("citation", ""),
            "decision_date": metadata.get("decisionDate"),
            "court": metadata.get("court", ""),
            "jurisdiction": "qc",
            "language": metadata.get("language", ""),
            "keywords": metadata.get("keywords", ""),
            "case_type": None,  # populated by summarizer later
            "url": metadata.get("url", ""),
            "embedding": embedding,
            "cited_cases": cited_cases,
            "citing_cases": citing_cases,
            "cited_legislation": cited_legislation,
            "metadata": {
                "canlii_case_id": case_id,
                "source": "canlii_api",
            },
        }

        return self.db.store_case(case_data)

    @staticmethod
    def _build_embedding_text(metadata: dict, cited_cases: list,
                              cited_legislation: list) -> str:
        """Combine metadata fields into a rich text for embedding generation.

        The resulting string gives the vector search semantic meaning
        beyond just the title.
        """
        parts = []

        title = metadata.get("title", "")
        if title:
            parts.append(title)

        citation = metadata.get("citation", "")
        if citation:
            parts.append(f"Citation: {citation}")

        court = metadata.get("court", "")
        if court:
            parts.append(f"Court: {court}")

        date = metadata.get("decisionDate", "")
        if date:
            parts.append(f"Date: {date}")

        keywords = metadata.get("keywords", "")
        if keywords:
            parts.append(f"Keywords: {keywords}")

        if cited_legislation:
            leg_titles = []
            for leg in cited_legislation[:20]:  # cap to avoid overly long text
                leg_title = leg.get("title", "")
                if leg_title:
                    leg_titles.append(leg_title)
            if leg_titles:
                parts.append(f"Cited legislation: {', '.join(leg_titles)}")

        if cited_cases:
            case_titles = []
            for c in cited_cases[:10]:  # cap for embedding length
                c_title = c.get("title", "")
                if c_title:
                    case_titles.append(c_title)
            if case_titles:
                parts.append(f"Cited cases: {', '.join(case_titles)}")

        return ". ".join(parts)
