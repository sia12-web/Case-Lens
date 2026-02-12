"""Tests for the ingestion pipeline."""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from caselens.ingest import CaseIngester


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_METADATA = {
    "title": "Tremblay c. Gagnon",
    "citation": "2024 QCCS 1234",
    "decisionDate": "2024-06-15",
    "court": "Superior Court of Quebec",
    "language": "fr",
    "keywords": "custody, access rights",
    "url": "https://www.canlii.org/en/qc/qccs/doc/2024/2024qccs1234/2024qccs1234.html",
}

SAMPLE_CITED_CASES = [
    {"databaseId": "qcca", "caseId": {"en": "2020qcca999"}, "title": "Droit de la famille — 201234"},
]

SAMPLE_CITED_LEGISLATION = [
    {"title": "Civil Code of Québec", "databaseId": "qc", "legislationId": "ccq-1991"},
]

SAMPLE_EMBEDDING = [0.01] * 1024
SAMPLE_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _make_ingester():
    """Build a CaseIngester with fully mocked dependencies."""
    canlii = MagicMock()
    db = MagicMock()
    embedder = MagicMock()
    return CaseIngester(canlii, db, embedder), canlii, db, embedder


# ---------------------------------------------------------------------------
# _process_case
# ---------------------------------------------------------------------------

def test_ingester_process_case():
    """_process_case fetches metadata + citator, embeds, and stores."""
    ingester, canlii, db, embedder = _make_ingester()

    canlii.get_case_metadata.return_value = SAMPLE_METADATA
    canlii.get_cited_cases.return_value = SAMPLE_CITED_CASES
    canlii.get_citing_cases.return_value = []
    canlii.get_cited_legislation.return_value = SAMPLE_CITED_LEGISLATION
    embedder.generate.return_value = SAMPLE_EMBEDDING
    db.store_case.return_value = SAMPLE_UUID

    case_summary = {"caseId": {"en": "2024qccs1234"}, "title": "Tremblay c. Gagnon"}
    result = ingester._process_case("qccs", "2024qccs1234", case_summary)

    assert result == SAMPLE_UUID

    # Verify store_case was called with correct data
    stored = db.store_case.call_args[0][0]
    assert stored["canlii_id"] == "qccs/2024qccs1234"
    assert stored["title"] == "Tremblay c. Gagnon"
    assert stored["cited_cases"] == SAMPLE_CITED_CASES
    assert stored["cited_legislation"] == SAMPLE_CITED_LEGISLATION
    assert stored["embedding"] == SAMPLE_EMBEDDING


# ---------------------------------------------------------------------------
# Skip existing
# ---------------------------------------------------------------------------

def test_ingester_skip_existing():
    """ingest_database skips cases already in Supabase."""
    ingester, canlii, db, embedder = _make_ingester()

    case_list = [
        {"caseId": {"en": "2024qccs1234"}, "title": "Tremblay c. Gagnon"},
    ]
    canlii.list_all_cases.return_value = case_list

    # Mock the _check_existing to return True (case already exists)
    mock_table = MagicMock()
    db._client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_execute = MagicMock()
    mock_execute.data = [{"id": SAMPLE_UUID}]
    mock_table.execute.return_value = mock_execute

    stats = ingester.ingest_database("qccs")

    assert stats["skipped"] == 1
    assert stats["ingested"] == 0
    # get_case_metadata should NOT have been called
    canlii.get_case_metadata.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_ingester_handles_api_error():
    """Ingester continues after a single case failure."""
    ingester, canlii, db, embedder = _make_ingester()

    case_list = [
        {"caseId": {"en": "case1"}, "title": "Case 1"},
        {"caseId": {"en": "case2"}, "title": "Case 2"},
    ]
    canlii.list_all_cases.return_value = case_list

    # Neither case exists in DB
    mock_table = MagicMock()
    db._client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_execute = MagicMock()
    mock_execute.data = []
    mock_table.execute.return_value = mock_execute

    # First case fails metadata, second succeeds
    canlii.get_case_metadata.side_effect = [
        {"error": "api_error", "message": "CanLII returned 500"},
        SAMPLE_METADATA,
    ]
    canlii.get_cited_cases.return_value = []
    canlii.get_citing_cases.return_value = []
    canlii.get_cited_legislation.return_value = []
    embedder.generate.return_value = SAMPLE_EMBEDDING
    db.store_case.return_value = SAMPLE_UUID

    stats = ingester.ingest_database("qccs")

    assert stats["errors"] == 1
    assert stats["ingested"] == 1
    assert stats["total"] == 2


def test_ingester_handles_list_error():
    """ingest_database returns error stats when case list fetch fails."""
    ingester, canlii, db, embedder = _make_ingester()
    canlii.list_all_cases.return_value = {"error": "api_error", "message": "403 Forbidden"}

    stats = ingester.ingest_database("qccs")

    assert stats["total"] == 0
    assert stats["errors"] == 1


# ---------------------------------------------------------------------------
# _build_embedding_text
# ---------------------------------------------------------------------------

def test_build_embedding_text():
    """Embedding text combines title, keywords, court, date, and legislation."""
    text = CaseIngester._build_embedding_text(
        SAMPLE_METADATA, SAMPLE_CITED_CASES, SAMPLE_CITED_LEGISLATION
    )

    assert "Tremblay c. Gagnon" in text
    assert "custody, access rights" in text
    assert "Superior Court of Quebec" in text
    assert "2024-06-15" in text
    assert "Civil Code of Québec" in text
    assert "Droit de la famille" in text


def test_build_embedding_text_minimal():
    """Embedding text handles minimal metadata gracefully."""
    text = CaseIngester._build_embedding_text(
        {"title": "Test Case"}, [], []
    )

    assert text == "Test Case"
