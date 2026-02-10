"""Unit tests for CLI and formatter modules."""

import json
import os

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from caselens.cli import main
from caselens.formatter import (
    format_terminal,
    format_markdown,
    format_error,
    format_verbose,
)


# -- Shared test data ------------------------------------------------------ #

VALID_SUMMARY = {
    "parties": [
        {"name": "Marie Tremblay", "role": "petitioner", "aliases": [], "source_pages": [1]},
        {"name": "Jean Dupont", "role": "respondent", "aliases": ["J. Dupont"], "source_pages": [1, 3]},
    ],
    "key_facts": [
        {"text": "The parties separated in June 2024.", "pages": [2]},
        {"text": "The petitioner seeks sole custody.", "pages": [1]},
    ],
    "timeline": [
        {"date": "2024-06-15", "event": "Parties separated.", "pages": [2]},
        {"date": "2024-09-01", "event": "Motion filed.", "pages": [3]},
    ],
    "case_type": "custody",
    "summary": "A custody dispute (p. 1) between the parties regarding their child.",
    "metadata": {
        "model": "claude-sonnet-4-5-20250929",
        "chunks_processed": 1,
        "filename": "test_case.pdf",
    },
}

VALID_EXTRACTION = {
    "pages": [{"page_number": 1, "text": "Extracted content."}],
    "chunks": [{"chunk_index": 0, "text": "Chunk text.", "char_count": 11, "source_pages": [1, 1]}],
    "metadata": {"total_pages": 1, "filename": "test_case.pdf", "is_chunked": False},
}


# -- Formatter tests ------------------------------------------------------- #

def test_formatter_terminal():
    """Verify formatter produces expected string structure."""
    output = format_terminal(VALID_SUMMARY)

    assert "CASE LENS" in output
    assert "PARTIES" in output
    assert "Marie Tremblay" in output
    assert "Jean Dupont" in output
    assert "J. Dupont" in output
    assert "SUMMARY" in output
    assert "custody dispute" in output
    assert "KEY FACTS" in output
    assert "separated in June 2024" in output
    assert "TIMELINE" in output
    assert "2024-06-15" in output
    assert "test_case.pdf" in output


def test_formatter_markdown():
    """Verify markdown output has correct headers and sections."""
    md = format_markdown(VALID_SUMMARY, "test_case.pdf")

    assert "# Case Lens Summary: test_case.pdf" in md
    assert "## Parties" in md
    assert "Marie Tremblay" in md
    assert "Jean Dupont" in md
    assert "## Summary" in md
    assert "custody dispute" in md
    assert "## Key Facts" in md
    assert "separated in June 2024" in md
    assert "## Timeline" in md
    assert "2024-06-15" in md
    assert "Case Type" in md


def test_formatter_error():
    """Verify error formatting."""
    err = {"error": "scanned_pdf", "message": "PDF is scanned."}
    output = format_error(err)

    assert "scanned_pdf" in output
    assert "PDF is scanned" in output


def test_formatter_verbose():
    """Verify verbose extraction metadata formatting."""
    output = format_verbose(VALID_EXTRACTION)

    assert "Pages: 1" in output
    assert "Chunks: 1" in output


def test_formatter_terminal_empty_sections():
    """Verify formatter handles summary with empty lists."""
    minimal = {
        "parties": [],
        "key_facts": [],
        "timeline": [],
        "case_type": "unknown",
        "summary": "",
        "metadata": {"model": "test", "chunks_processed": 1, "filename": "f.pdf"},
    }
    output = format_terminal(minimal)
    # Should not crash, should still have header
    assert "CASE LENS" in output


# -- CLI tests ------------------------------------------------------------- #

@patch("caselens.cli.Summarizer")
@patch("caselens.cli.PdfProcessor")
def test_cli_with_valid_pdf(mock_processor_cls, mock_summarizer_cls):
    """Mock pipeline, verify CLI runs without error and outputs text."""
    mock_processor = MagicMock()
    mock_processor.process.return_value = VALID_EXTRACTION
    mock_processor_cls.return_value = mock_processor

    mock_summarizer = MagicMock()
    mock_summarizer.summarize.return_value = VALID_SUMMARY
    mock_summarizer_cls.return_value = mock_summarizer

    runner = CliRunner()
    result = runner.invoke(main, ["test.pdf"])

    assert result.exit_code == 0
    assert "Marie Tremblay" in result.output
    assert "CASE LENS" in result.output


@patch("caselens.cli.Summarizer")
@patch("caselens.cli.PdfProcessor")
def test_cli_missing_file(mock_processor_cls, mock_summarizer_cls):
    """Verify clean error message for nonexistent file."""
    mock_processor = MagicMock()
    mock_processor.process.return_value = {
        "error": "file_not_found",
        "message": "File not found: missing.pdf",
    }
    mock_processor_cls.return_value = mock_processor

    runner = CliRunner()
    result = runner.invoke(main, ["missing.pdf"])

    assert result.exit_code == 1
    assert "file_not_found" in result.output


@patch("caselens.cli.Summarizer")
@patch("caselens.cli.PdfProcessor")
def test_cli_markdown_export(mock_processor_cls, mock_summarizer_cls, tmp_path):
    """Mock pipeline, verify .md file is created with correct content."""
    mock_processor = MagicMock()
    mock_processor.process.return_value = VALID_EXTRACTION
    mock_processor_cls.return_value = mock_processor

    mock_summarizer = MagicMock()
    mock_summarizer.summarize.return_value = VALID_SUMMARY
    mock_summarizer_cls.return_value = mock_summarizer

    output_path = str(tmp_path / "summary.md")

    runner = CliRunner()
    result = runner.invoke(main, ["test.pdf", "--output", output_path])

    assert result.exit_code == 0
    assert os.path.exists(output_path)

    with open(output_path, encoding="utf-8") as f:
        md_content = f.read()

    assert "# Case Lens Summary" in md_content
    assert "Marie Tremblay" in md_content
    assert "## Timeline" in md_content


@patch("caselens.cli.Summarizer")
@patch("caselens.cli.PdfProcessor")
def test_cli_verbose_flag(mock_processor_cls, mock_summarizer_cls):
    """Verify --verbose shows extraction metadata."""
    mock_processor = MagicMock()
    mock_processor.process.return_value = VALID_EXTRACTION
    mock_processor_cls.return_value = mock_processor

    mock_summarizer = MagicMock()
    mock_summarizer.summarize.return_value = VALID_SUMMARY
    mock_summarizer_cls.return_value = mock_summarizer

    runner = CliRunner()
    result = runner.invoke(main, ["test.pdf", "--verbose"])

    assert result.exit_code == 0
    assert "Pages: 1" in result.output


@patch("caselens.cli.Summarizer")
@patch("caselens.cli.PdfProcessor")
def test_cli_summarizer_error(mock_processor_cls, mock_summarizer_cls):
    """Verify CLI handles summarizer error gracefully."""
    mock_processor = MagicMock()
    mock_processor.process.return_value = VALID_EXTRACTION
    mock_processor_cls.return_value = mock_processor

    mock_summarizer = MagicMock()
    mock_summarizer.summarize.return_value = {
        "error": "missing_api_key",
        "message": "ANTHROPIC_API_KEY is not set.",
    }
    mock_summarizer_cls.return_value = mock_summarizer

    runner = CliRunner()
    result = runner.invoke(main, ["test.pdf"])

    assert result.exit_code == 1
    assert "missing_api_key" in result.output


# -- Page citation formatter tests ----------------------------------------- #

def test_formatter_shows_citations():
    """Verify page citations appear in terminal output."""
    output = format_terminal(VALID_SUMMARY)

    # Party citation
    assert "(p. 1)" in output
    assert "(p. 1, 3)" in output

    # Key fact citation
    assert "(p. 2)" in output

    # Timeline citation
    assert "(p. 2)" in output
    assert "(p. 3)" in output


def test_formatter_disclaimer_present():
    """Verify disclaimer appears in both terminal and markdown output."""
    terminal = format_terminal(VALID_SUMMARY)
    md = format_markdown(VALID_SUMMARY, "test.pdf")

    assert "AI-generated" in terminal
    assert "verified against the source document" in terminal
    assert "AI-generated" in md
    assert "verified against the source document" in md


def test_formatter_checklist_present():
    """Verify verification checklist appears in both outputs."""
    terminal = format_terminal(VALID_SUMMARY)
    md = format_markdown(VALID_SUMMARY, "test.pdf")

    assert "VERIFICATION CHECKLIST" in terminal
    assert "Verify parties" in terminal
    assert "Verify dates" in terminal
    assert "Verify 2 key facts" in terminal

    assert "## Verification Checklist" in md
    assert "- [ ] Verify parties" in md
    assert "- [ ] Verify dates" in md


def test_formatter_backward_compat():
    """Verify old-format data (no page citations) renders without crash."""
    old_format = {
        "parties": [
            {"name": "Alice", "role": "petitioner", "aliases": []},
        ],
        "key_facts": [
            "A plain string fact with no page info.",
        ],
        "timeline": [
            {"date": "2024-01-01", "event": "Something happened."},
        ],
        "case_type": "custody",
        "summary": "A case summary without inline citations.",
        "metadata": {"model": "test", "chunks_processed": 1, "filename": "old.pdf"},
    }

    terminal = format_terminal(old_format)
    md = format_markdown(old_format, "old.pdf")

    assert "Alice" in terminal
    assert "plain string fact" in terminal
    assert "Something happened" in terminal

    assert "Alice" in md
    assert "plain string fact" in md
    assert "Something happened" in md
