"""Tests for the CanLII API client."""

from unittest.mock import MagicMock, patch

import pytest

from caselens.canlii import CanLIIClient, MIN_REQUEST_INTERVAL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CASE_LIST = [
    {
        "caseId": {"en": "2024qccs1234"},
        "title": "Tremblay c. Gagnon",
        "citation": "2024 QCCS 1234",
    },
    {
        "caseId": {"en": "2024qccs5678"},
        "title": "Roy c. Bouchard",
        "citation": "2024 QCCS 5678",
    },
]

SAMPLE_METADATA = {
    "caseId": {"en": "2024qccs1234"},
    "title": "Tremblay c. Gagnon",
    "citation": "2024 QCCS 1234",
    "decisionDate": "2024-06-15",
    "court": "Superior Court of Quebec",
    "language": "fr",
    "keywords": "custody, access rights, best interest of the child",
    "url": "https://www.canlii.org/en/qc/qccs/doc/2024/2024qccs1234/2024qccs1234.html",
}

SAMPLE_CITED_CASES = {
    "citedCases": [
        {"databaseId": "qcca", "caseId": {"en": "2020qcca999"}, "title": "Droit de la famille — 201234", "citation": "2020 QCCA 999"},
    ]
}

SAMPLE_CITING_CASES = {
    "citingCases": [
        {"databaseId": "qccs", "caseId": {"en": "2025qccs100"}, "title": "A v. B", "citation": "2025 QCCS 100"},
    ]
}

SAMPLE_CITED_LEGISLATION = {
    "citedLegislations": [
        {"title": "Civil Code of Québec", "databaseId": "qc", "legislationId": "ccq-1991"},
    ]
}


def _make_client():
    """Build a CanLIIClient with a fake API key."""
    with patch("caselens.canlii._load_env"):
        client = CanLIIClient(api_key="test-key")
    # Reset throttle so tests don't wait
    client._last_request_time = 0.0
    return client


def _mock_response(json_data, status_code=200):
    """Build a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# ---------------------------------------------------------------------------
# list_cases
# ---------------------------------------------------------------------------

def test_canlii_list_cases():
    """list_cases returns a list of case summary dicts."""
    client = _make_client()
    client._http = MagicMock()
    client._http.get.return_value = _mock_response(SAMPLE_CASE_LIST)

    result = client.list_cases("qccs", offset=0, count=100)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["title"] == "Tremblay c. Gagnon"


def test_canlii_list_cases_with_date_filters():
    """list_cases passes date filters as query params."""
    client = _make_client()
    client._http = MagicMock()
    client._http.get.return_value = _mock_response(SAMPLE_CASE_LIST)

    client.list_cases("qccs", decision_date_after="2024-01-01",
                      decision_date_before="2024-12-31")

    call_kwargs = client._http.get.call_args
    params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
    assert params["decisionDateAfter"] == "2024-01-01"
    assert params["decisionDateBefore"] == "2024-12-31"


# ---------------------------------------------------------------------------
# get_case_metadata
# ---------------------------------------------------------------------------

def test_canlii_get_metadata():
    """get_case_metadata returns full metadata dict."""
    client = _make_client()
    client._http = MagicMock()
    client._http.get.return_value = _mock_response(SAMPLE_METADATA)

    result = client.get_case_metadata("qccs", "2024qccs1234")

    assert result["title"] == "Tremblay c. Gagnon"
    assert result["decisionDate"] == "2024-06-15"
    assert result["keywords"] == "custody, access rights, best interest of the child"


# ---------------------------------------------------------------------------
# Citator
# ---------------------------------------------------------------------------

def test_canlii_get_cited_cases():
    """get_cited_cases unwraps the citedCases envelope."""
    client = _make_client()
    client._http = MagicMock()
    client._http.get.return_value = _mock_response(SAMPLE_CITED_CASES)

    result = client.get_cited_cases("qccs", "2024qccs1234")

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["citation"] == "2020 QCCA 999"


def test_canlii_get_citing_cases():
    """get_citing_cases unwraps the citingCases envelope."""
    client = _make_client()
    client._http = MagicMock()
    client._http.get.return_value = _mock_response(SAMPLE_CITING_CASES)

    result = client.get_citing_cases("qccs", "2024qccs1234")

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["citation"] == "2025 QCCS 100"


def test_canlii_get_cited_legislation():
    """get_cited_legislation unwraps the citedLegislations envelope."""
    client = _make_client()
    client._http = MagicMock()
    client._http.get.return_value = _mock_response(SAMPLE_CITED_LEGISLATION)

    result = client.get_cited_legislation("qccs", "2024qccs1234")

    assert isinstance(result, list)
    assert result[0]["title"] == "Civil Code of Québec"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

@patch("caselens.canlii.time.sleep")
def test_canlii_rate_limiting(mock_sleep):
    """Verifies throttle sleeps when requests are too fast."""
    client = _make_client()
    client._http = MagicMock()
    client._http.get.return_value = _mock_response(SAMPLE_CASE_LIST)

    # Simulate the last request happening just now
    import time
    client._last_request_time = time.time()

    client.list_cases("qccs")

    mock_sleep.assert_called_once()
    sleep_arg = mock_sleep.call_args[0][0]
    assert 0 < sleep_arg <= MIN_REQUEST_INTERVAL


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@patch("caselens.canlii._load_env")
def test_canlii_missing_key(mock_env):
    """Returns error dict when API key is missing."""
    client = CanLIIClient(api_key=None)

    result = client.list_cases("qccs")

    assert isinstance(result, dict)
    assert result["error"] == "missing_api_key"


def test_canlii_api_error():
    """Returns error dict on HTTP error."""
    client = _make_client()
    client._http = MagicMock()
    client._http.get.return_value = _mock_response({}, status_code=403)

    result = client.get_case_metadata("qccs", "2024qccs1234")

    assert isinstance(result, dict)
    assert result["error"] == "api_error"
    assert "403" in result["message"]
