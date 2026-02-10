"""Unit tests for Summarizer."""

import json

import pytest
from unittest.mock import patch, MagicMock

from caselens.summarizer import Summarizer


# -- Fixtures & helpers ---------------------------------------------------- #

VALID_SUMMARY_JSON = {
    "parties": [
        {"name": "Marie Tremblay", "role": "petitioner", "aliases": [], "source_pages": [1]},
        {"name": "Jean Dupont", "role": "respondent", "aliases": ["J. Dupont"], "source_pages": [1, 3]},
        {"name": "Sophie Dupont", "role": "child", "aliases": [], "source_pages": [2]},
    ],
    "key_facts": [
        {"text": "The parties separated in June 2024.", "pages": [2]},
        {"text": "The petitioner seeks sole custody of the minor child.", "pages": [1]},
        {"text": "The respondent has exercised access rights every other weekend.", "pages": [3]},
    ],
    "timeline": [
        {"date": "2024-06-15", "event": "Parties separated.", "pages": [2]},
        {"date": "2024-09-01", "event": "Petitioner filed motion for custody.", "pages": [3]},
        {"date": "2025-01-10", "event": "Hearing held before the Superior Court.", "pages": [5]},
    ],
    "case_type": "custody",
    "summary": "This case concerns a custody dispute (p. 1) between Marie Tremblay and Jean Dupont regarding their daughter Sophie. The parties separated in June 2024 (p. 2), and the petitioner filed for sole custody in September 2024 (p. 3).",
}


def _make_extraction(num_chunks=1, chunk_text="Document text content.", num_pages=5):
    """Build a mock PdfProcessor extraction dict."""
    pages = [
        {"page_number": i + 1, "text": f"Page {i + 1} content. {chunk_text}"}
        for i in range(num_pages)
    ]
    chunks = []
    for i in range(num_chunks):
        chunks.append({
            "chunk_index": i,
            "text": chunk_text,
            "char_count": len(chunk_text),
            "source_pages": [1, num_pages],
        })
    return {
        "pages": pages,
        "chunks": chunks,
        "metadata": {
            "total_pages": num_pages,
            "filename": "test_case.pdf",
            "is_chunked": num_chunks > 1,
        },
    }


def _mock_api_response(body: dict) -> MagicMock:
    """Build a mock Anthropic API response."""
    content_block = MagicMock()
    content_block.text = json.dumps(body, ensure_ascii=False)
    response = MagicMock()
    response.content = [content_block]
    return response


@pytest.fixture
def summarizer():
    """Summarizer with a fake API key (tests never hit real API)."""
    return Summarizer(api_key="test-key-not-real")


# -- Required tests -------------------------------------------------------- #

@patch("caselens.summarizer.anthropic")
def test_summarizer_single_chunk(mock_anthropic, summarizer):
    """Mock API call, verify output structure has all required fields."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_api_response(VALID_SUMMARY_JSON)
    mock_anthropic.Anthropic.return_value = mock_client

    extraction = _make_extraction(num_chunks=1)
    result = summarizer.summarize(extraction)

    # No error
    assert "error" not in result

    # All required fields present
    assert "parties" in result
    assert "key_facts" in result
    assert "timeline" in result
    assert "case_type" in result
    assert "summary" in result
    assert "metadata" in result

    # Correct types
    assert isinstance(result["parties"], list)
    assert isinstance(result["key_facts"], list)
    assert isinstance(result["timeline"], list)
    assert isinstance(result["case_type"], str)
    assert isinstance(result["summary"], str)

    # Party structure
    party = result["parties"][0]
    assert "name" in party
    assert "role" in party
    assert "aliases" in party

    # Timeline structure
    event = result["timeline"][0]
    assert "date" in event
    assert "event" in event

    # Metadata
    assert result["metadata"]["model"] == summarizer.model
    assert result["metadata"]["chunks_processed"] == 1
    assert result["metadata"]["filename"] == "test_case.pdf"

    # API was called exactly once (single chunk)
    mock_client.messages.create.assert_called_once()


@patch("caselens.summarizer.anthropic")
def test_summarizer_multi_chunk(mock_anthropic, summarizer):
    """Mock API call with chunked input, verify merge works."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_api_response(VALID_SUMMARY_JSON)
    mock_anthropic.Anthropic.return_value = mock_client

    extraction = _make_extraction(num_chunks=3, chunk_text="Chunk of legal text.")
    result = summarizer.summarize(extraction)

    assert "error" not in result
    assert result["metadata"]["chunks_processed"] == 3

    # 3 chunk summaries + 1 merge call = 4 API calls
    assert mock_client.messages.create.call_count == 4

    # All required fields still present after merge
    assert "parties" in result
    assert "key_facts" in result
    assert "timeline" in result
    assert "case_type" in result
    assert "summary" in result


@patch.object(Summarizer, "_load_env")
def test_summarizer_missing_api_key(mock_load):
    """Verify clear error when ANTHROPIC_API_KEY not set."""
    with patch.dict("os.environ", {}, clear=True):
        s = Summarizer(api_key="")
        result = s.summarize(_make_extraction())

    assert result["error"] == "missing_api_key"
    assert "ANTHROPIC_API_KEY" in result["message"]


@patch("caselens.summarizer.anthropic")
def test_summarizer_malformed_response(mock_anthropic, summarizer):
    """Verify graceful handling of bad JSON from API."""
    content_block = MagicMock()
    content_block.text = "This is not valid JSON at all."
    mock_response = MagicMock()
    mock_response.content = [content_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic.Anthropic.return_value = mock_client

    result = summarizer.summarize(_make_extraction())

    assert result["error"] == "malformed_response"
    assert "raw_response" in result


# -- Additional edge-case tests -------------------------------------------- #

def test_summarizer_rejects_error_extraction(summarizer):
    """Verify that passing an extraction with an error is caught."""
    bad_extraction = {"error": "scanned_pdf", "message": "Scanned PDF."}
    result = summarizer.summarize(bad_extraction)

    assert result["error"] == "invalid_extraction"


def test_summarizer_rejects_empty_extraction(summarizer):
    """Verify that an extraction with no chunks is caught."""
    empty = {
        "pages": [],
        "chunks": [],
        "metadata": {"total_pages": 0, "filename": "empty.pdf", "is_chunked": False},
    }
    result = summarizer.summarize(empty)

    assert result["error"] == "empty_extraction"


@patch("caselens.summarizer.anthropic")
def test_summarizer_handles_markdown_fenced_json(mock_anthropic, summarizer):
    """Verify JSON wrapped in markdown code fences is parsed correctly."""
    fenced = "```json\n" + json.dumps(VALID_SUMMARY_JSON) + "\n```"
    content_block = MagicMock()
    content_block.text = fenced
    mock_response = MagicMock()
    mock_response.content = [content_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic.Anthropic.return_value = mock_client

    result = summarizer.summarize(_make_extraction())

    assert "error" not in result
    assert result["case_type"] == "custody"


@patch("caselens.summarizer.anthropic")
def test_summarizer_incomplete_response(mock_anthropic, summarizer):
    """Verify error when API returns JSON missing required fields."""
    incomplete = {"parties": [], "summary": "Just a summary."}
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_api_response(incomplete)
    mock_anthropic.Anthropic.return_value = mock_client

    result = summarizer.summarize(_make_extraction())

    assert result["error"] == "incomplete_response"
    assert "missing required fields" in result["message"]


@patch("caselens.summarizer.anthropic")
def test_summarizer_auth_error(mock_anthropic, summarizer):
    """Verify authentication error is caught."""
    import anthropic as real_anthropic

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = real_anthropic.AuthenticationError(
        message="Invalid API key",
        response=MagicMock(status_code=401),
        body={"error": {"message": "Invalid API key"}},
    )
    mock_anthropic.Anthropic.return_value = mock_client
    mock_anthropic.AuthenticationError = real_anthropic.AuthenticationError
    mock_anthropic.RateLimitError = real_anthropic.RateLimitError
    mock_anthropic.APIError = real_anthropic.APIError

    result = summarizer.summarize(_make_extraction())

    assert result["error"] == "auth_error"


@patch("caselens.summarizer.anthropic")
def test_summarizer_french_output(mock_anthropic, summarizer):
    """Verify French content is preserved in the summary."""
    french_summary = {
        "parties": [
            {"name": "Marie-Ève Côté", "role": "petitioner", "aliases": [], "source_pages": [1]},
            {"name": "François Bélanger", "role": "respondent", "aliases": [], "source_pages": [1]},
        ],
        "key_facts": [
            {"text": "Les parties se sont séparées en juin 2024.", "pages": [2]},
            {"text": "La demanderesse réclame la garde exclusive de l'enfant.", "pages": [1]},
        ],
        "timeline": [
            {"date": "2024-06-15", "event": "Séparation des parties.", "pages": [2]},
        ],
        "case_type": "custody",
        "summary": "Cette affaire concerne un litige de garde entre Marie-Ève Côté et François Bélanger (p. 1).",
    }

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_api_response(french_summary)
    mock_anthropic.Anthropic.return_value = mock_client

    result = summarizer.summarize(_make_extraction())

    assert "error" not in result
    assert "Côté" in result["parties"][0]["name"]
    assert "séparées" in result["key_facts"][0]["text"]
    assert "Séparation" in result["timeline"][0]["event"]


# -- Page citation tests --------------------------------------------------- #

@patch("caselens.summarizer.anthropic")
def test_prompt_has_page_markers(mock_anthropic, summarizer):
    """Verify the text sent to Claude includes [PAGE N] markers."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_api_response(VALID_SUMMARY_JSON)
    mock_anthropic.Anthropic.return_value = mock_client

    extraction = _make_extraction(num_chunks=1, num_pages=3)
    summarizer.summarize(extraction)

    # Inspect the user message sent to the API
    call_args = mock_client.messages.create.call_args
    user_content = call_args.kwargs["messages"][0]["content"]
    assert "[PAGE 1]" in user_content
    assert "[PAGE 2]" in user_content
    assert "[PAGE 3]" in user_content


@patch("caselens.summarizer.anthropic")
def test_summary_preserves_page_citations(mock_anthropic, summarizer):
    """Verify parsed output includes page citations on facts and timeline."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_api_response(VALID_SUMMARY_JSON)
    mock_anthropic.Anthropic.return_value = mock_client

    result = summarizer.summarize(_make_extraction())

    assert "error" not in result

    # Parties should have source_pages
    assert "source_pages" in result["parties"][0]
    assert isinstance(result["parties"][0]["source_pages"], list)

    # Key facts should be dicts with text and pages
    fact = result["key_facts"][0]
    assert isinstance(fact, dict)
    assert "text" in fact
    assert "pages" in fact

    # Timeline events should have pages
    event = result["timeline"][0]
    assert "pages" in event
    assert isinstance(event["pages"], list)


@patch("caselens.summarizer.anthropic")
def test_multi_chunk_uses_page_annotated_text(mock_anthropic, summarizer):
    """Verify each chunk's text sent to API starts with [PAGE N] markers."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _mock_api_response(VALID_SUMMARY_JSON)
    mock_anthropic.Anthropic.return_value = mock_client

    extraction = _make_extraction(num_chunks=2, num_pages=5)
    summarizer.summarize(extraction)

    # First two calls are chunk summarizations, third is merge
    assert mock_client.messages.create.call_count == 3

    # Both chunk calls should have [PAGE markers in user content
    for i in range(2):
        call_args = mock_client.messages.create.call_args_list[i]
        user_content = call_args.kwargs["messages"][0]["content"]
        assert "[PAGE" in user_content
