# Case Lens — Project Context

## Overview
Case Lens is a legal document analysis tool that extracts structured text from PDF files for downstream LLM processing.

## Phase 1: PDF Processing Engine

### What Was Built
- `PdfProcessor` class that extracts, cleans, and chunks text from legal PDFs
- Text cleaning pipeline that strips Bates stamps, page numbers, confidentiality footers (EN/FR), and excessive whitespace
- Smart chunking algorithm (80,000 char max, 500 char overlap) that splits at paragraph/sentence boundaries
- Graceful error handling for scanned PDFs, password-protected files, and missing files
- Full test suite with 14 unit tests using mocked PDF libraries

### File Structure
```
Case Lens/
├── caselens/
│   ├── __init__.py          # Package init, exports PdfProcessor & Summarizer
│   ├── __main__.py          # Entry point for python -m caselens
│   ├── pdf_processor.py     # Core extraction/cleaning/chunking logic
│   ├── summarizer.py        # Claude API integration for legal summaries
│   ├── cli.py               # Click-based CLI
│   ├── formatter.py         # Terminal and markdown output formatters
│   ├── api.py               # FastAPI server with auth, rate limiting
│   ├── rate_limiter.py      # In-memory sliding-window rate limiter
│   └── ocr.py               # Tesseract OCR via PyMuPDF for scanned PDFs
├── tests/
│   ├── __init__.py
│   ├── test_pdf_processor.py  # 14 unit tests
│   ├── test_summarizer.py     # 13 unit tests
│   ├── test_cli.py            # 14 unit tests (CLI + formatter)
│   ├── test_api.py            # 14 unit tests (endpoints + auth)
│   ├── test_rate_limiter.py   # 7 unit tests
│   └── test_ocr.py            # 9 unit tests (OCR engine)
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.ts       # API proxy rewrites
│   ├── postcss.config.mjs
│   ├── .env.example         # Frontend env var docs
│   └── src/app/
│       ├── globals.css      # Tailwind + custom properties + animations
│       ├── layout.tsx       # Root layout with CaseLens header
│       └── page.tsx         # Main page (upload/processing/results)
├── sample_pdfs/
│   └── .gitkeep
├── .gitignore
├── .env.example
├── requirements.txt
├── railway.toml             # Railway deployment config
├── CONTEXT.md
└── CHANGELOG.md
```

### Tech Decisions
| Decision | Rationale |
|----------|-----------|
| **pdfplumber** (primary) | Best text extraction quality for legal documents with tables/columns |
| **pypdf** (fallback) | Maintained successor to PyPDF2; handles edge cases pdfplumber misses |
| **Lazy import for pypdf** | Only loaded when pdfplumber fails, keeps startup fast |
| **Scanned PDF heuristic** | If ≥80% of pages yield <50 chars, classified as scanned → triggers OCR (Phase 7) |
| **Chunk at natural boundaries** | Prefers paragraph > sentence > hard break for LLM readability |
| **Error dicts, not exceptions** | Caller never needs try/except; all outcomes are in the return value |

### API
```python
from caselens.pdf_processor import PdfProcessor

processor = PdfProcessor()
result = processor.process("path/to/document.pdf")

# Success:
# {
#     "pages": [{"page_number": 1, "text": "..."}, ...],
#     "chunks": [{"chunk_index": 0, "text": "...", "char_count": N, "source_pages": [1, 5]}, ...],
#     "metadata": {"total_pages": 10, "filename": "document.pdf", "is_chunked": True}
# }

# Error:
# {"error": "scanned_pdf", "message": "..."}
```

### How to Run Tests
```bash
pip install -r requirements.txt
pytest tests/ -v
```

### What's Next
- ~~OCR support for scanned PDFs~~ → Completed in Phase 7

---

## Phase 2: Claude API Integration

### What Was Built
- `Summarizer` class that sends PdfProcessor output to Claude and returns structured legal summaries
- System prompt tailored for Quebec family law document analysis (EN/FR bilingual)
- Single-chunk path: sends full text, gets JSON summary
- Multi-chunk path: summarizes each chunk, then merges via a second API call
- Graceful error handling for missing API key, auth failures, rate limits, malformed responses
- 10 unit tests using mocked Anthropic API (no real API calls)

### Tech Decisions
| Decision | Rationale |
|----------|-----------|
| **claude-sonnet-4-5-20250929** | Best cost/quality balance for summarization tasks |
| **Temperature 0.1** | Low temperature for consistent, factual legal outputs |
| **anthropic SDK** (top-level import) | Required dependency, enables clean mocking in tests |
| **python-dotenv** | Loads API key from `.env` without manual export |
| **JSON-only responses** | System prompt forces pure JSON — no markdown wrapping |
| **Markdown fence stripping** | Fallback parser strips ` ```json ` fences if model adds them |

### Summary Output Schema
```python
from caselens.summarizer import Summarizer

summarizer = Summarizer()  # reads ANTHROPIC_API_KEY from .env
result = summarizer.summarize(extraction)

# Success:
# {
#     "parties": [
#         {"name": "Marie Tremblay", "role": "petitioner", "aliases": []}
#     ],
#     "key_facts": ["The parties separated in June 2024."],
#     "timeline": [
#         {"date": "2024-06-15", "event": "Parties separated."}
#     ],
#     "case_type": "custody",  # custody|divorce|support|mixed|other
#     "summary": "Plain-language summary of the case...",
#     "metadata": {
#         "model": "claude-sonnet-4-5-20250929",
#         "chunks_processed": 1,
#         "filename": "document.pdf"
#     }
# }

# Error:
# {"error": "missing_api_key", "message": "..."}
```

### How to Run Tests
```bash
pip install -r requirements.txt
pytest tests/ -v
```

All 24 tests pass (14 Phase 1 + 10 Phase 2). Tests use mocked APIs — no real API key needed.

---

## Phase 3: CLI

### What Was Built
- Click-based CLI accessible via `python -m caselens <pdf_path>`
- Rich-formatted terminal output with colored sections (parties, summary, facts, timeline)
- Markdown export via `--output` flag
- Progress spinner during PDF extraction and API summarization
- `--verbose` flag to show extraction metadata (page count, chunks) without exposing raw text
- Separate `formatter.py` module with `format_terminal()`, `format_markdown()`, `format_error()`, `format_verbose()`
- 10 unit tests covering CLI invocation, error handling, markdown export, and formatter output

### Tech Decisions
| Decision | Rationale |
|----------|-----------|
| **Click** | Standard Python CLI framework — decorators, help text, option parsing |
| **Rich** | Professional terminal output — panels, colors, spinners |
| **Separate formatter module** | Keeps CLI thin; formatters are independently testable |
| **`__main__.py`** | Enables `python -m caselens` invocation |

### CLI Usage
```bash
# Basic usage — prints formatted summary to terminal
python -m caselens path/to/document.pdf

# Save markdown summary to file
python -m caselens path/to/document.pdf --output summary.md

# Show extraction metadata (page count, chunk count)
python -m caselens path/to/document.pdf --verbose

# Help
python -m caselens --help
```

### How to Run Tests
```bash
pytest tests/ -v
```

All 34 tests pass (14 Phase 1 + 10 Phase 2 + 10 Phase 3).

---

## Phase 4: Web API

### What Was Built
- FastAPI server with PDF upload endpoint and health check
- `POST /api/summarize`: accepts PDF file upload, returns structured summary JSON
- `GET /api/health`: simple health check returning `{"status": "ok"}`
- Temp file handling with guaranteed cleanup via `try/finally`
- File validation: PDF extension, content type, 20MB size limit
- CORS middleware configured for `localhost:3000` (Next.js dev server)
- Consistent error responses matching the existing `{"error": str, "message": str}` pattern
- Exception handler catches unexpected errors, returns 500 without leaking internals
- 9 unit tests using FastAPI TestClient with mocked pipeline

### Tech Decisions
| Decision | Rationale |
|----------|-----------|
| **FastAPI** | Modern async Python framework with automatic OpenAPI docs |
| **NamedTemporaryFile** | Stdlib temp files, deleted in `finally` block |
| **CORS for localhost:3000** | Ready for Phase 5 Next.js frontend |
| **JSONResponse for errors** | Allows custom status codes while keeping dict format |
| **422 for extraction errors** | Unprocessable Entity — file is valid PDF but can't be extracted |
| **502 for summarizer errors** | Bad Gateway — upstream Claude API failed |

### API Endpoints

#### `GET /api/health`
```
Response: {"status": "ok"}
```

#### `POST /api/summarize`
```
Request: multipart/form-data with field "file" (PDF, max 20MB)

Success (200):
{
    "parties": [...],
    "key_facts": [...],
    "timeline": [...],
    "case_type": "custody",
    "summary": "...",
    "metadata": {"model": "...", "chunks_processed": 1, "filename": "uploaded.pdf"}
}

Errors:
  400: {"error": "invalid_format", "message": "..."}
  413: {"error": "file_too_large", "message": "..."}
  422: {"error": "scanned_pdf|protected_pdf|...", "message": "..."}
  502: {"error": "missing_api_key|api_error|...", "message": "..."}
  500: {"error": "internal_error", "message": "..."}
```

### How to Run the Server
```bash
# Development (with auto-reload)
python -m caselens.api

# Or directly with uvicorn
uvicorn caselens.api:app --reload --port 8000

# Interactive API docs (Swagger UI)
# Open http://localhost:8000/docs
```

### How to Run Tests
```bash
pytest tests/ -v
```

All 43 tests pass (14 Phase 1 + 10 Phase 2 + 10 Phase 3 + 9 Phase 4).

---

## Phase 5: Web Frontend

### What Was Built
- Next.js app in `frontend/` with TypeScript and Tailwind CSS
- Single-page interface with three states: Upload, Processing, Results
- Upload zone with drag-and-drop and click-to-browse PDF selection
- Processing state with animated spinner and fake progressive status messages
- Results view with formatted sections: narrative summary, parties table, key facts list, timeline table
- Markdown export button (downloads `<filename>_summary.md`)
- "New Analysis" button to reset and upload another PDF
- API proxy via `next.config.ts` rewrites — `/api/*` proxied to `localhost:8000`
- Frontend file validation: PDF only, max 20 MB
- Professional law-firm design: navy (#1a2332), white, gold (#c9a84c) accents

### Frontend File Structure
```
frontend/
├── package.json
├── tsconfig.json
├── next.config.ts          # API proxy rewrites to localhost:8000
├── postcss.config.mjs      # Tailwind CSS via @tailwindcss/postcss
└── src/
    └── app/
        ├── globals.css     # Tailwind imports + CSS custom properties + animations
        ├── layout.tsx      # Root layout with CaseLens header branding
        └── page.tsx        # Main page — upload, processing, results states
```

### Tech Decisions
| Decision | Rationale |
|----------|-----------|
| **Next.js 16 (App Router)** | Modern React framework with built-in routing and API proxy |
| **Tailwind CSS 4** | Utility-first styling, no component library needed |
| **API proxy via rewrites** | Avoids CORS issues — frontend `/api/*` proxied to FastAPI on port 8000 |
| **Single page, three states** | Simple state machine — no routing needed for MVP |
| **Fake progressive messages** | Timed status updates provide UX feedback independent of backend progress |
| **No automated tests** | MVP frontend — manual testing checklist only |

### How to Run
```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000

# Backend must also be running:
python -m caselens.api  # starts on port 8000
```

### How Frontend Connects to Backend
- `next.config.ts` defines rewrites: `/api/:path*` → `http://localhost:8000/api/:path*`
- Frontend calls `POST /api/summarize` with PDF as `FormData`
- Backend returns summary JSON, frontend renders it in the Results view
- No API keys are exposed to the frontend — all LLM calls happen server-side

### Manual Test Checklist
- [ ] Upload valid PDF → summary displays correctly
- [ ] Upload non-PDF → error message shown
- [ ] Upload large file (>20MB) → error message shown
- [ ] Export markdown → file downloads
- [ ] Upload another PDF → resets view cleanly

---

## Phase 6: Auth, Rate Limiting & Deployment

### What Was Built
- API key authentication via `X-API-Key` header on `/api/summarize`
- Auth disabled when `CASELENS_API_KEY` env var is unset (dev mode)
- In-memory sliding-window rate limiter: 10 requests/hour per API key
- Security headers middleware: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`
- Configurable CORS via `ALLOWED_ORIGINS` env var
- Railway deployment config (`railway.toml`)
- Frontend updated to send `X-API-Key` from `NEXT_PUBLIC_API_KEY` env var
- 12 new tests (5 auth + 7 rate limiter)

### New Files
| File | Purpose |
|------|---------|
| `caselens/rate_limiter.py` | `RateLimiter` class — sliding-window, per-key, in-memory |
| `tests/test_rate_limiter.py` | 7 unit tests for rate limiter |
| `railway.toml` | Railway deployment config with health check |
| `frontend/.env.example` | Frontend environment variable documentation |

### Tech Decisions
| Decision | Rationale |
|----------|-----------|
| **`Depends()` over middleware** | Auth only on `/api/summarize`; health and docs stay open |
| **Dev mode bypass** | `CASELENS_API_KEY` unset → auth disabled entirely |
| **In-memory rate limiter** | No Redis needed at this scale; resets on restart |
| **Failed requests don't consume slots** | Prevents lockout from retries on 429 |
| **Dependency chaining** | `summarize → check_rate_limit → verify_api_key` |

### Environment Variables

**Backend (`.env`)**:
| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for summarization |
| `CASELENS_API_KEY` | No | API key for frontend auth (unset = dev mode) |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins (default: localhost:3000) |

**Frontend (`.env.local`)**:
| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | No | Backend URL (empty for local proxy) |
| `NEXT_PUBLIC_API_KEY` | No | API key sent in `X-API-Key` header |

### Deployment

**Backend → Railway**:
```bash
# railway.toml handles build and start command
# Set env vars in Railway dashboard:
#   ANTHROPIC_API_KEY, CASELENS_API_KEY, ALLOWED_ORIGINS
```

**Frontend → Vercel**:
```bash
# Standard Next.js deployment
# Set env vars in Vercel dashboard:
#   NEXT_PUBLIC_API_URL = https://your-railway-url.up.railway.app
#   NEXT_PUBLIC_API_KEY = same as CASELENS_API_KEY on backend
```

### How to Run Tests
```bash
pytest tests/ -v
```

All 55 tests pass (14 Phase 1 + 10 Phase 2 + 10 Phase 3 + 14 Phase 4/6 API + 7 rate limiter).

### Security Measures
- API key required on `/api/summarize` (when `CASELENS_API_KEY` is set)
- Rate limiting: 10 req/hour per key with `Retry-After` header on 429
- Security headers on all responses (`nosniff`, `DENY`)
- CORS restricted to configured origins only
- Error responses never expose file paths, API keys, or stack traces
- Temp files cleaned in `finally` block under all code paths
- No secrets in codebase — all keys via environment variables

---

## Phase 7: OCR Support for Scanned PDFs

### What Was Built
- `OcrEngine` class in `caselens/ocr.py` for extracting text from scanned/image-based PDF pages
- Automatic OCR integration into `PdfProcessor.process()` — scanned PDFs are now processed instead of rejected
- Mixed PDF support: only pages with <50 characters are OCR'd; text-heavy pages keep their pdfplumber extraction
- Graceful degradation: if Tesseract/pymupdf not installed, returns `ocr_unavailable` error with install instructions
- OCR metadata in results: `ocr_applied` and `ocr_pages` fields added to metadata dict
- 14 new tests (9 OcrEngine unit tests + 5 PdfProcessor OCR integration tests)

### New Files
| File | Purpose |
|------|---------|
| `caselens/ocr.py` | `OcrEngine` class — renders pages via PyMuPDF, OCRs with Tesseract |
| `tests/test_ocr.py` | 9 unit tests for OcrEngine (availability checks, page OCR, error handling) |

### Tech Decisions
| Decision | Rationale |
|----------|-----------|
| **PyMuPDF (fitz)** for rendering | Pure-pip install, no poppler needed (unlike pdf2image) |
| **pytesseract** for OCR | Standard Tesseract wrapper, well-maintained |
| **Guarded imports** | `fitz`, `pytesseract`, `PIL.Image` set to `None` if missing — module loads regardless |
| **Lazy import in PdfProcessor** | `_attempt_ocr` does `from caselens import ocr` — no coupling when OCR not needed |
| **Per-page selective OCR** | Only sparse pages (<50 chars) get OCR'd; avoids degrading text-heavy pages |
| **300 DPI default** | Good balance of OCR quality vs speed for legal documents |

### OCR Data Flow
```
process()
  → _detect_scanned() → True (≥80% of pages have <50 chars)
  → _attempt_ocr(filepath, pages)
    → OcrEngine.check_availability() → (True, "") or (False, reason)
    → identify sparse pages (< SCANNED_MIN_CHARS_PER_PAGE chars)
    → OcrEngine.ocr_pages(filepath, sparse_page_nums)
      → PyMuPDF renders page → PIL Image → pytesseract → text
    → replace raw_text in pages in-place
  → _clean_text() → _chunk_pages() → _build_result(ocr_info=...)
```

### Error Codes
| Code | When | HTTP (API) |
|------|------|------------|
| `ocr_unavailable` | Scanned PDF but OCR deps not installed | 422 |
| `ocr_failed` | OCR attempted but crashed | 422 |

### Dependencies
```
pymupdf>=1.24.0       # PDF page rendering (no poppler needed)
pytesseract>=0.3.10   # Tesseract OCR wrapper
```

**System requirement**: Tesseract OCR binary must be installed separately:
```bash
# Anaconda
conda install -c conda-forge tesseract

# Or download from https://github.com/tesseract-ocr/tesseract
```

### How to Run Tests
```bash
python -m pytest tests/ -v
```

All 69 tests pass (19 PDF processor + 10 summarizer + 10 CLI + 14 API + 7 rate limiter + 9 OCR).

## Phase 8: Page Citations + Verification

### What Was Built
- Page citations on all extracted data — parties, key facts, timeline events, and narrative summary
- `[PAGE N]` marker injection into text sent to Claude for accurate citation tracking
- Verification checklist generated deterministically in the formatter (not by Claude)
- AI disclaimer appended to all outputs (terminal, markdown, frontend)
- Backward-compatible formatters handling both old string and new dict formats for key_facts

### Changes to Existing Files
| File | Changes |
|------|---------|
| `caselens/summarizer.py` | Updated `SYSTEM_PROMPT` and `MERGE_SYSTEM_PROMPT` for citations; added `_build_annotated_text()`; `summarize()` now passes page-annotated text |
| `caselens/formatter.py` | Added `_extract_fact()`, `_format_cite()`, `_format_cite_plain()`, `_build_checklist()`; updated `format_terminal()` and `format_markdown()` with citations, checklist, disclaimer |
| `frontend/src/app/page.tsx` | New `KeyFact` interface; `extractFact()` and `formatCite()` helpers; Source columns in tables; verification checklist; disclaimer |
| `tests/test_summarizer.py` | Updated `VALID_SUMMARY_JSON` with citations; 3 new tests |
| `tests/test_cli.py` | Updated `VALID_SUMMARY` with citations; 4 new tests |

### Output Schema Changes
```python
# Old key_facts format:
"key_facts": ["A factual finding."]

# New key_facts format:
"key_facts": [{"text": "A factual finding.", "pages": [2]}]

# Old parties format:
"parties": [{"name": "...", "role": "...", "aliases": [...]}]

# New parties format:
"parties": [{"name": "...", "role": "...", "aliases": [...], "source_pages": [1, 3]}]

# Old timeline format:
"timeline": [{"date": "...", "event": "..."}]

# New timeline format:
"timeline": [{"date": "...", "event": "...", "pages": [5]}]

# Summary now includes inline citations:
"summary": "The parties separated (p. 2) and filed for custody (p. 3)..."
```

### Citation Data Flow
```
PdfProcessor.process() → extraction with pages[]
  ↓
Summarizer._build_annotated_text(pages, source_pages)
  → "[PAGE 1]\ntext...\n\n[PAGE 2]\ntext..."
  ↓
Claude API → JSON with page citations on every field
  ↓
Formatter._extract_fact() → handles str (old) or dict (new)
Formatter._format_cite() → " (p. 1, 3)"
Formatter._build_checklist() → ["Verify parties: X (p. 1)", ...]
```

### How to Run Tests
```bash
python -m pytest tests/ -v
```

All 76 tests pass (19 PDF processor + 13 summarizer + 14 CLI + 14 API + 7 rate limiter + 9 OCR).
