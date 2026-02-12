"""Tests for the CaseDatabase class."""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CASE = {
    "canlii_id": "2024qccs1234",
    "database_id": "qccs",
    "title": "Tremblay c. Gagnon",
    "citation": "2024 QCCS 1234",
    "decision_date": "2024-06-15",
    "court": "Superior Court of Quebec",
    "jurisdiction": "qc",
    "language": "fr",
    "case_type": "custody",
    "summary": "The court awarded joint custody with primary residence to the mother.",
    "embedding": [0.01] * 1024,
}

SAMPLE_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _mock_execute(data):
    """Build a mock Supabase execute() response."""
    resp = MagicMock()
    resp.data = data
    return resp


def _build_db_with_mock_client():
    """Create a CaseDatabase with a mocked Supabase client."""
    with patch("caselens.database._load_env"), \
         patch("caselens.database.create_client") as mock_create:
        mock_client = MagicMock()
        mock_create.return_value = mock_client

        from caselens.database import CaseDatabase
        db = CaseDatabase(supabase_url="https://test.supabase.co", supabase_key="test-key")

    return db, mock_client


# ---------------------------------------------------------------------------
# store_case
# ---------------------------------------------------------------------------

def test_store_case():
    """store_case upserts data and returns the new UUID."""
    db, mock_client = _build_db_with_mock_client()

    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.upsert.return_value = mock_table
    mock_table.execute.return_value = _mock_execute([{"id": SAMPLE_UUID}])

    result = db.store_case(SAMPLE_CASE)

    assert result == SAMPLE_UUID
    mock_client.table.assert_called_with("cases")
    mock_table.upsert.assert_called_once_with(SAMPLE_CASE, on_conflict="canlii_id")


def test_store_case_missing_canlii_id():
    """store_case returns error if canlii_id is missing."""
    db, _ = _build_db_with_mock_client()

    result = db.store_case({"title": "No ID"})

    assert isinstance(result, dict)
    assert result["error"] == "missing_field"


def test_store_case_database_error():
    """store_case returns error dict on exception."""
    db, mock_client = _build_db_with_mock_client()

    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.upsert.return_value = mock_table
    mock_table.execute.side_effect = Exception("connection timeout")

    result = db.store_case(SAMPLE_CASE)

    assert isinstance(result, dict)
    assert result["error"] == "database_error"


# ---------------------------------------------------------------------------
# search_similar
# ---------------------------------------------------------------------------

def test_search_similar():
    """search_similar calls RPC and returns ranked results."""
    db, mock_client = _build_db_with_mock_client()

    mock_rpc = MagicMock()
    mock_client.rpc.return_value = mock_rpc
    mock_rpc.execute.return_value = _mock_execute([
        {"id": SAMPLE_UUID, "title": "Tremblay c. Gagnon", "citation": "2024 QCCS 1234", "similarity": 0.95},
        {"id": "other-uuid", "title": "Roy c. Bouchard", "citation": "2023 QCCS 5678", "similarity": 0.82},
    ])

    query_emb = [0.02] * 1024
    result = db.search_similar(query_emb, limit=5)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["similarity"] > result[1]["similarity"]
    mock_client.rpc.assert_called_with(
        "match_cases",
        {"query_embedding": query_emb, "match_count": 5},
    )


# ---------------------------------------------------------------------------
# get_case
# ---------------------------------------------------------------------------

def test_get_case():
    """get_case retrieves a single case by UUID."""
    db, mock_client = _build_db_with_mock_client()

    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = _mock_execute([{
        "id": SAMPLE_UUID,
        "title": "Tremblay c. Gagnon",
        "citation": "2024 QCCS 1234",
    }])

    result = db.get_case(SAMPLE_UUID)

    assert result["id"] == SAMPLE_UUID
    assert result["title"] == "Tremblay c. Gagnon"


def test_get_case_not_found():
    """get_case returns error dict when case doesn't exist."""
    db, mock_client = _build_db_with_mock_client()

    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = _mock_execute([])

    result = db.get_case("nonexistent-uuid")

    assert isinstance(result, dict)
    assert result["error"] == "not_found"


# ---------------------------------------------------------------------------
# Citation graph
# ---------------------------------------------------------------------------

def test_get_cases_citing():
    """get_cases_citing returns the citing_cases JSONB field."""
    db, mock_client = _build_db_with_mock_client()

    citing = [
        {"database_id": "qccs", "case_id": "2023qccs9999", "title": "Roy c. Lavoie", "citation": "2023 QCCS 9999"},
    ]
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = _mock_execute([{"citing_cases": citing}])

    result = db.get_cases_citing(SAMPLE_UUID)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["citation"] == "2023 QCCS 9999"


def test_get_cases_cited_by():
    """get_cases_cited_by returns the cited_cases JSONB field."""
    db, mock_client = _build_db_with_mock_client()

    cited = [
        {"database_id": "qcca", "case_id": "2022qcca5555", "title": "Gagnon c. Tremblay", "citation": "2022 QCCA 5555"},
        {"database_id": "qccs", "case_id": "2021qccs1111", "title": "Dubois c. Martin", "citation": "2021 QCCS 1111"},
    ]
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = _mock_execute([{"cited_cases": cited}])

    result = db.get_cases_cited_by(SAMPLE_UUID)

    assert isinstance(result, list)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Missing config
# ---------------------------------------------------------------------------

@patch("caselens.database._load_env")
@patch("caselens.database.create_client")
def test_missing_config(mock_create, mock_env):
    """Returns error dict when Supabase credentials are missing."""
    from caselens.database import CaseDatabase
    db = CaseDatabase(supabase_url=None, supabase_key=None)

    result = db.store_case(SAMPLE_CASE)

    assert isinstance(result, dict)
    assert result["error"] == "missing_config"
