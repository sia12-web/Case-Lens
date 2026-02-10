# Changelog

## [0.8.0] - 2026-02-10

### Phase 8: Page Citations + Verification

#### Added
- Page citations on all extracted data: parties get `source_pages`, key_facts become `{text, pages}` objects, timeline events get `pages`, summary gets inline `(p. N)` citations
- `[PAGE N]` marker injection into text sent to Claude for citation tracking
- `_build_annotated_text()` method in Summarizer for page-marker injection
- Verification checklist in both terminal and markdown output (parties, dates, facts)
- AI disclaimer appended to all formatted output
- Backward-compatible formatters: handle both old string and new dict formats for key_facts
- Frontend: Source column in Parties and Timeline tables, page citations on Key Facts
- Frontend: Interactive verification checklist with checkboxes
- Frontend: AI disclaimer footer
- Markdown export includes citations, checklist, and disclaimer
- 7 new tests (3 in `test_summarizer.py`, 4 in `test_cli.py`)

#### Changed
- `SYSTEM_PROMPT` updated to require page citations in all output fields
- `MERGE_SYSTEM_PROMPT` updated to preserve page citations during merge
- `summarize()` now builds page-annotated text instead of using raw chunk text
- Formatter `format_terminal()` and `format_markdown()` display page citations
- Frontend TypeScript interfaces updated: `Party`, `KeyFact`, `TimelineEvent`, `CaseSummary`

#### Test Count
- 76 tests total (69 existing + 7 new)

---

## [0.7.0] - 2026-02-10

### Phase 7: OCR Support for Scanned PDFs

#### Added
- `OcrEngine` class in `caselens/ocr.py` — extracts text from scanned PDF pages using Tesseract OCR via PyMuPDF
- Automatic OCR on scanned/image-based PDFs (previously returned an error)
- Mixed PDF support: only sparse pages (<50 chars) are OCR'd; text-heavy pages keep their extraction
- OCR metadata in results: `ocr_applied`, `ocr_pages` fields in metadata dict
- Graceful degradation: if Tesseract not installed, returns `ocr_unavailable` error with install instructions
- `check_availability()` method validates pymupdf, pytesseract, Pillow, and Tesseract binary
- 14 new tests (9 in `test_ocr.py`, 5 in `test_pdf_processor.py`)

#### Dependencies
- `pymupdf>=1.24.0` — renders PDF pages to images (no poppler required)
- `pytesseract>=0.3.10` — Python wrapper for Tesseract OCR

#### Changed
- `PdfProcessor.process()` now attempts OCR instead of returning `scanned_pdf` error
- `_build_result()` accepts optional `ocr_info` parameter for OCR metadata
- Updated `test_handles_scanned_pdf` to expect `ocr_unavailable` error code

#### Test Count
- 69 tests total (55 existing + 14 new)

---

## [0.6.0] - 2026-02-10

### Phase 6: Auth, Rate Limiting & Deployment

#### Added
- API key authentication via `X-API-Key` header on `/api/summarize`
- `CASELENS_API_KEY` env var — auth disabled when unset (dev mode)
- In-memory sliding-window rate limiter (10 requests/hour per key)
- `caselens/rate_limiter.py` module with `RateLimiter` class
- Security headers middleware: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`
- Configurable CORS via `ALLOWED_ORIGINS` env var (comma-separated)
- `railway.toml` for Railway deployment with health check
- `frontend/.env.example` for Vercel deployment env vars
- Frontend sends `X-API-Key` header from `NEXT_PUBLIC_API_KEY` env var
- 5 new API auth tests + 7 rate limiter unit tests (55 total)

#### Fixed
- Removed duplicate entries in `requirements.txt`

#### Changed
- CORS origins now read from `ALLOWED_ORIGINS` env var (defaults to localhost:3000)
- Tightened `allow_methods` from `["*"]` to `["GET", "POST"]`

## [0.5.0] - 2026-02-10

### Phase 5: Web Frontend

#### Added
- Next.js 16 app in `frontend/` with TypeScript and Tailwind CSS 4
- Single-page interface: Upload → Processing → Results states
- Drag-and-drop and click-to-browse PDF upload zone
- Animated processing state with fake progressive status messages
- Results view: narrative summary, parties table, key facts list, timeline table
- Markdown export button (downloads `<filename>_summary.md`)
- "New Analysis" button to reset and upload another PDF
- API proxy via `next.config.ts` rewrites (`/api/*` → `localhost:8000`)
- Frontend file validation (PDF only, max 20 MB)
- Professional design: navy (#1a2332), white, gold (#c9a84c) accents

## [0.4.0] - 2026-02-10

### Phase 4: Web API

#### Added
- FastAPI server with `POST /api/summarize` (PDF upload → summary JSON)
- `GET /api/health` health check endpoint
- Temp file handling with guaranteed cleanup via `try/finally`
- File validation: PDF extension, content type, 20MB size limit
- CORS middleware for `localhost:3000`
- Consistent JSON error responses (400, 413, 422, 500, 502)
- General exception handler preventing internal details from leaking
- 9 unit tests using FastAPI TestClient
- Dependencies: `fastapi`, `uvicorn`, `python-multipart`, `httpx`

#### Fixed
- `test_summarizer_missing_api_key` now patches `_load_env` to prevent `.env` file from interfering

## [0.3.0] - 2026-02-10

### Phase 3: CLI

#### Added
- Click-based CLI: `python -m caselens <pdf_path>`
- Rich-formatted terminal output with colored sections (parties, summary, facts, timeline)
- Markdown export via `--output` / `-o` flag
- Progress spinner during extraction and summarization
- `--verbose` / `-v` flag for extraction metadata
- `formatter.py` module with `format_terminal()`, `format_markdown()`, `format_error()`, `format_verbose()`
- `__main__.py` entry point for `python -m caselens`
- 10 unit tests for CLI and formatter
- Dependencies: `click`, `rich`

## [0.2.0] - 2026-02-10

### Phase 2: Claude API Integration

#### Added
- `Summarizer` class with `summarize()` method for structured legal summaries
- System prompt for Quebec family law document analysis (EN/FR bilingual)
- Single-chunk and multi-chunk summarization paths with automatic merging
- JSON response parsing with markdown fence stripping fallback
- Error handling for missing API key, auth failures, rate limits, malformed responses
- 10 unit tests with fully mocked Anthropic API
- Dependencies: `anthropic`, `python-dotenv`

## [0.1.0] - 2026-02-10

### Phase 1: PDF Processing Engine — Initial Implementation

#### Added
- `PdfProcessor` class with `process()` method for PDF text extraction
- pdfplumber as primary extractor, pypdf as fallback
- Text cleaning pipeline: Bates stamps, page numbers, confidentiality footers (EN/FR), whitespace normalization
- Chunking with 80,000 char limit and 500 char overlap at natural text boundaries
- Scanned PDF detection heuristic
- Password-protected PDF handling
- French/English bilingual support
- 14 unit tests with full mocking (no real PDFs required)
- Project scaffold: package structure, .gitignore, requirements.txt, CONTEXT.md
