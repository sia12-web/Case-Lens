"""FastAPI server for Case Lens PDF summarization."""

import asyncio
import os
import tempfile
import logging

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from caselens.pdf_processor import PdfProcessor
from caselens.summarizer import Summarizer
from caselens.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

# ------------------------------------------------------------------
# Configuration from environment
# ------------------------------------------------------------------

CASELENS_API_KEY = os.environ.get("CASELENS_API_KEY")

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]

rate_limiter = RateLimiter(max_requests=100, window_seconds=3600)

# ------------------------------------------------------------------
# Auth & rate-limit dependencies
# ------------------------------------------------------------------

async def verify_api_key(request: Request) -> str:
    """Validate X-API-Key header. Returns the key for downstream use.

    When CASELENS_API_KEY is not set, auth is disabled (dev mode).
    """
    if not CASELENS_API_KEY:
        return "__dev__"

    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={"error": "missing_api_key", "message": "X-API-Key header is required."},
        )
    if api_key != CASELENS_API_KEY:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_api_key", "message": "Invalid API key."},
        )
    return api_key


async def check_rate_limit(api_key: str = Depends(verify_api_key)) -> str:
    """Enforce per-key rate limiting after auth passes."""
    if not rate_limiter.is_allowed(api_key):
        retry = rate_limiter.retry_after(api_key)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Rate limit exceeded. Try again in {retry} seconds.",
            },
            headers={"Retry-After": str(retry)} if retry else {},
        )
    return api_key

# ------------------------------------------------------------------
# Security headers middleware
# ------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

# ------------------------------------------------------------------
# App setup
# ------------------------------------------------------------------

app = FastAPI(
    title="Case Lens API",
    description="Legal PDF analysis and summarization powered by Claude.",
    version="0.6.0",
)

# Relaxed CORS for production deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    """Health check."""
    return {"status": "ok"}


@app.post("/api/summarize")
async def summarize(
    file: UploadFile = File(...),
    api_key: str = Depends(check_rate_limit),
) -> dict:
    """Upload a PDF and receive a structured legal summary.

    Returns the same summary schema used by the CLI:
    parties, key_facts, timeline, case_type, summary, metadata.
    """
    # --- Validate filename extension ---
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_format", "message": "Only PDF files are accepted."},
        )

    # --- Validate content type ---
    content_type = file.content_type or ""
    if content_type and content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_format", "message": f"Invalid content type: {content_type}. Expected application/pdf."},
        )

    # --- Read and validate size ---
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": "file_too_large", "message": f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit."},
        )

    # --- Process in temp file ---
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, dir=tempfile.gettempdir()
        ) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        # Extract (run in thread to avoid blocking the event loop)
        processor = PdfProcessor()
        extraction = await asyncio.to_thread(processor.process, tmp_path)

        if "error" in extraction:
            return JSONResponse(
                status_code=422,
                content={"error": extraction["error"], "message": extraction["message"]},
            )

        # Summarize (run in thread — Claude API call can take 30+ seconds)
        summarizer = Summarizer()
        summary = await asyncio.to_thread(summarizer.summarize, extraction)

        if "error" in summary:
            return JSONResponse(
                status_code=502,
                content={"error": summary["error"], "message": summary["message"]},
            )

        # Patch filename in metadata to use original upload name
        if "metadata" in summary:
            summary["metadata"]["filename"] = filename

        return summary

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error processing PDF")
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "An unexpected error occurred during processing."},
        )
    finally:
        # Guarantee cleanup
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ------------------------------------------------------------------
# Runner — python -m caselens.api
# ------------------------------------------------------------------

def run_server() -> None:
    """Start the uvicorn server."""
    import uvicorn
    uvicorn.run("caselens.api:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    run_server()
