"""Legal document summarization via Claude API."""

import json
import logging
import os
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

# The model used for summarization — Sonnet 3.5 balances quality and cost.
DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 8192  # Increased to prevent truncation of large summaries

SYSTEM_PROMPT = """\
You are a legal document analyst specializing in Quebec family law.
Analyze the provided court document text and produce a structured JSON summary.

The input text contains [PAGE N] markers indicating which page each section comes from.
For every fact, date, name, and amount you extract, include the source page number(s) based on these markers.

You MUST return ONLY valid JSON with exactly these fields — no markdown, no commentary:

{
  "parties": [
    {"name": "Full Name", "role": "petitioner|respondent|child|expert|judge|lawyer|other", "aliases": ["nickname or alternate spelling"], "source_pages": [1, 3]}
  ],
  "key_facts": [
    {"text": "A concise factual finding or allegation from the document.", "pages": [2]}
  ],
  "timeline": [
    {"date": "YYYY-MM-DD or descriptive date", "event": "What happened on this date.", "pages": [5]}
  ],
  "case_type": "custody|divorce|support|mixed|other",
  "summary": "A 2-4 paragraph plain-language summary with inline (p. N) citations after key facts, dates, and amounts."
}

Rules:
- Extract ALL named parties, including children, experts, and judges.
- For timeline dates, use ISO format (YYYY-MM-DD) when exact dates are given. Use descriptive text ("Summer 2023", "before the hearing") when exact dates are not available.
- Sort timeline entries chronologically.
- case_type should be "mixed" if the case involves multiple family law issues (e.g. custody AND support).
- The summary should be neutral, factual, and written for a lawyer reviewing the file.
- Include inline page citations in the summary using the format (p. N) or (p. N, M) after significant facts.
- Preserve the language of the original document: if the text is in French, write the summary fields in French. If English, write in English.
- If a field cannot be determined from the text, use an empty list [] or "unknown".
- Return ONLY the JSON object. No extra text before or after.\
"""

MERGE_SYSTEM_PROMPT = """\
You are a legal document analyst. You will receive multiple JSON summaries extracted
from consecutive chunks of the same court document. Merge them into a single coherent
summary following the exact same JSON schema.

Rules for merging:
- Deduplicate parties by name (combine aliases and merge source_pages).
- Merge key_facts lists, removing exact duplicates. Preserve page citations from each chunk.
- Merge timeline lists, sort chronologically, remove duplicates. Preserve page citations.
- Pick the most specific case_type (prefer "custody", "divorce", "support" over "other"; use "mixed" if multiple types appear).
- Write a single unified summary paragraph that synthesizes all chunk summaries. Preserve inline (p. N) citations.
- Return ONLY valid JSON, no markdown or commentary.\
"""


class Summarizer:
    """Summarizes legal PDF extractions using the Claude API.

    Usage::

        summarizer = Summarizer()
        result = summarizer.summarize(extraction)
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        """Initialize the summarizer.

        Args:
            api_key: Anthropic API key. If not provided, reads from
                     ANTHROPIC_API_KEY environment variable (loaded from .env).
            model: Claude model ID to use.
            temperature: Sampling temperature (low = more deterministic).
            max_tokens: Maximum tokens in the API response.
        """
        self._load_env()
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def summarize(self, extraction: dict) -> dict:
        """Produce a structured legal summary from a PdfProcessor extraction.

        Args:
            extraction: Output dict from ``PdfProcessor.process()``.

        Returns:
            On success::

                {
                    "parties": [{"name": str, "role": str, "aliases": list}],
                    "key_facts": [str],
                    "timeline": [{"date": str, "event": str}],
                    "case_type": str,
                    "summary": str,
                    "metadata": {"model": str, "chunks_processed": int, "filename": str}
                }

            On error::

                {"error": str, "message": str}
        """
        # Validate API key
        if not self.api_key:
            return {
                "error": "missing_api_key",
                "message": "ANTHROPIC_API_KEY is not set. Add it to your .env file.",
            }

        # Validate extraction input
        error = self._validate_extraction(extraction)
        if error:
            return error

        chunks = extraction["chunks"]
        pages = extraction.get("pages", [])
        filename = extraction["metadata"].get("filename", "unknown")

        if len(chunks) == 1:
            # Single-chunk path
            annotated = self._build_annotated_text(pages, chunks[0].get("source_pages"))
            summary = self._summarize_chunk(annotated)
            if "error" in summary:
                return summary
            summary["metadata"] = {
                "model": self.model,
                "chunks_processed": 1,
                "filename": filename,
            }
            return summary
        else:
            # Multi-chunk path
            chunk_summaries = []
            for chunk in chunks:
                annotated = self._build_annotated_text(pages, chunk.get("source_pages"))
                result = self._summarize_chunk(annotated)
                if "error" in result:
                    return result
                chunk_summaries.append(result)

            merged = self._merge_summaries(chunk_summaries)
            if "error" in merged:
                return merged
            merged["metadata"] = {
                "model": self.model,
                "chunks_processed": len(chunks),
                "filename": filename,
            }
            return merged

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_annotated_text(pages: list[dict], source_pages: Optional[list[int]] = None) -> str:
        """Build text with [PAGE N] markers prepended to each page's content.

        Args:
            pages: List of page dicts from extraction (``{"page_number": int, "text": str}``).
            source_pages: ``[first_page, last_page]`` range to include. If None, all pages.

        Returns:
            Concatenated text with ``[PAGE N]`` markers.
        """
        if not pages:
            return ""

        if source_pages and len(source_pages) == 2:
            first, last = source_pages
        else:
            first, last = pages[0]["page_number"], pages[-1]["page_number"]

        parts: list[str] = []
        for page in pages:
            pn = page["page_number"]
            if first <= pn <= last:
                parts.append(f"[PAGE {pn}]\n{page['text']}")
        return "\n\n".join(parts)

    @staticmethod
    def _load_env() -> None:
        """Load .env file if python-dotenv is available."""
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

    @staticmethod
    def _validate_extraction(extraction: dict) -> Optional[dict]:
        """Return an error dict if the extraction is invalid."""
        if "error" in extraction:
            return {
                "error": "invalid_extraction",
                "message": f"Extraction contains an error: {extraction['error']}",
            }
        if "chunks" not in extraction or not extraction["chunks"]:
            return {
                "error": "empty_extraction",
                "message": "Extraction contains no text chunks to summarize.",
            }
        return None

    def _summarize_chunk(self, text: str) -> dict:
        """Send a single chunk to the Claude API and parse the JSON response."""
        messages = [{"role": "user", "content": text}]
        response_text = self._call_api(SYSTEM_PROMPT, messages)
        if isinstance(response_text, dict):
            return response_text  # error dict from _call_api
        return self._parse_response(response_text)

    def _merge_summaries(self, summaries: list[dict]) -> dict:
        """Merge multiple chunk summaries into one via a second API call."""
        combined_json = json.dumps(summaries, ensure_ascii=False, indent=2)
        messages = [{"role": "user", "content": combined_json}]
        response_text = self._call_api(MERGE_SYSTEM_PROMPT, messages)
        if isinstance(response_text, dict):
            return response_text  # error dict
        return self._parse_response(response_text)

    def _call_api(self, system: str, messages: list[dict]) -> str | dict:
        """Call the Anthropic API. Returns response text or error dict."""
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                messages=messages,
            )
            return response.content[0].text
        except anthropic.AuthenticationError:
            return {
                "error": "auth_error",
                "message": "Invalid ANTHROPIC_API_KEY. Check your .env file.",
            }
        except anthropic.RateLimitError:
            return {
                "error": "rate_limit",
                "message": "API rate limit reached. Please wait and retry.",
            }
        except anthropic.APIError as e:
            return {
                "error": "api_error",
                "message": f"Claude API error: {e}",
            }
        except Exception as e:
            return {
                "error": "api_error",
                "message": f"Unexpected error calling Claude API: {e}",
            }

    @staticmethod
    def _parse_response(text: str) -> dict:
        """Parse JSON from the API response, handling common formatting issues."""
        cleaned = text.strip()

        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        # Find the first '{' and last '}' to extract the JSON object
        # This handles cases where the model adds commentary or markdown fences
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx:end_idx + 1]
        elif start_idx != -1:
            # If we found { but no }, it's likely truncated
            cleaned = cleaned[start_idx:]
        
        cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON. Text length: {len(text)}. Error: {e}")
            logger.error(f"Response starts with: {text[:100]!r}")
            logger.error(f"Response ends with: {text[-100:]!r}")
            return {
                "error": "malformed_response",
                "message": f"Failed to parse API response as JSON: {e}",
                "raw_response": text[:1000],  # Increased to help debug
            }

        # Validate required fields
        required = {"parties", "key_facts", "timeline", "case_type", "summary"}
        missing = required - set(parsed.keys())
        if missing:
            return {
                "error": "incomplete_response",
                "message": f"API response missing required fields: {', '.join(sorted(missing))}",
                "raw_response": text[:500],
            }

        return parsed
