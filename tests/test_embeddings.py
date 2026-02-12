"""Tests for the EmbeddingEngine class."""

from unittest.mock import MagicMock, patch

import pytest

from caselens.embeddings import EMBEDDING_DIM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_voyage_embedding(dim=EMBEDDING_DIM):
    """Return a list of floats simulating a Voyage embedding."""
    return [0.01 * i for i in range(dim)]


def _make_voyage_response(embeddings):
    """Build a mock Voyage API response."""
    resp = MagicMock()
    resp.embeddings = embeddings
    return resp


def _make_openai_response(embeddings):
    """Build a mock OpenAI embeddings response."""
    resp = MagicMock()
    items = []
    for emb in embeddings:
        item = MagicMock()
        item.embedding = emb
        items.append(item)
    resp.data = items
    return resp


# ---------------------------------------------------------------------------
# Voyage engine tests
# ---------------------------------------------------------------------------

@patch("caselens.embeddings._load_env")
@patch("caselens.embeddings.voyageai")
def test_generate_single_voyage(mock_voyageai, mock_env):
    """Voyage engine returns a 1024-dim vector for a single text."""
    fake_emb = _fake_voyage_embedding()
    mock_client = MagicMock()
    mock_client.embed.return_value = _make_voyage_response([fake_emb])
    mock_voyageai.Client.return_value = mock_client

    from caselens.embeddings import EmbeddingEngine
    engine = EmbeddingEngine(voyage_api_key="test-key")

    result = engine.generate("The court ruled in favor of the petitioner.")

    assert isinstance(result, list)
    assert len(result) == EMBEDDING_DIM
    mock_client.embed.assert_called_once()


@patch("caselens.embeddings._load_env")
@patch("caselens.embeddings.voyageai")
def test_generate_batch_voyage(mock_voyageai, mock_env):
    """Voyage engine returns correct number of embeddings for batch."""
    texts = ["First case.", "Second case.", "Third case."]
    fake_embs = [_fake_voyage_embedding() for _ in texts]
    mock_client = MagicMock()
    mock_client.embed.return_value = _make_voyage_response(fake_embs)
    mock_voyageai.Client.return_value = mock_client

    from caselens.embeddings import EmbeddingEngine
    engine = EmbeddingEngine(voyage_api_key="test-key")

    result = engine.generate_batch(texts)

    assert isinstance(result, list)
    assert len(result) == 3
    assert all(len(v) == EMBEDDING_DIM for v in result)


# ---------------------------------------------------------------------------
# OpenAI fallback tests
# ---------------------------------------------------------------------------

@patch("caselens.embeddings._load_env")
@patch("caselens.embeddings.voyageai", None)
@patch("caselens.embeddings.openai")
def test_generate_single_openai_fallback(mock_openai, mock_env):
    """Falls back to OpenAI when voyageai is unavailable."""
    fake_emb = _fake_voyage_embedding()
    mock_client = MagicMock()
    mock_client.embeddings.create.return_value = _make_openai_response([fake_emb])
    mock_openai.OpenAI.return_value = mock_client

    from caselens.embeddings import EmbeddingEngine
    engine = EmbeddingEngine(openai_api_key="test-openai-key")

    result = engine.generate("Test text for OpenAI fallback embedding generation.")

    assert isinstance(result, list)
    assert len(result) == EMBEDDING_DIM
    assert engine.engine == "openai"


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

@patch("caselens.embeddings._load_env")
@patch("caselens.embeddings.voyageai", None)
@patch("caselens.embeddings.openai", None)
def test_generate_missing_key(mock_env):
    """Returns error dict when no API key is available."""
    from caselens.embeddings import EmbeddingEngine
    engine = EmbeddingEngine()

    result = engine.generate("Some text that needs embedding.")

    assert isinstance(result, dict)
    assert result["error"] == "missing_api_key"


@patch("caselens.embeddings._load_env")
@patch("caselens.embeddings.voyageai")
def test_generate_api_error(mock_voyageai, mock_env):
    """Returns error dict when the API call fails."""
    mock_client = MagicMock()
    mock_client.embed.side_effect = Exception("API rate limit exceeded")
    mock_voyageai.Client.return_value = mock_client

    from caselens.embeddings import EmbeddingEngine
    engine = EmbeddingEngine(voyage_api_key="test-key")

    result = engine.generate("Text that triggers an error.")

    assert isinstance(result, dict)
    assert result["error"] == "embedding_failed"
    assert "rate limit" in result["message"]


@patch("caselens.embeddings._load_env")
def test_generate_batch_empty(mock_env):
    """Batch with empty list returns empty list."""
    from caselens.embeddings import EmbeddingEngine
    engine = EmbeddingEngine(voyage_api_key="test-key")

    result = engine.generate_batch([])

    assert result == []
