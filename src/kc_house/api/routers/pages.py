"""The two web pages: the tester at ``/`` and the slides at ``/presentation``."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

WEB_DIR = Path(__file__).resolve().parents[2] / "web"

# Pages are self-contained (inline CSS and JS, no outside requests), so the policy
# can forbid everything else. /docs is not covered: Swagger loads its own assets.
PAGE_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "public, max-age=300",
}

router = APIRouter(include_in_schema=False)


@router.api_route("/", methods=["GET", "HEAD"])
def tester() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", headers=PAGE_HEADERS)


@router.api_route("/presentation", methods=["GET", "HEAD"])
def presentation() -> FileResponse:
    return FileResponse(WEB_DIR / "presentation.html", headers=PAGE_HEADERS)
