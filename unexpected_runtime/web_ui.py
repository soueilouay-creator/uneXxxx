from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import unquote


WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
ASSET_ROOT = WEB_ROOT / "assets"


def read_index() -> bytes:
    return (WEB_ROOT / "index.html").read_bytes()


def read_asset(request_path: str) -> tuple[bytes, str] | None:
    """Read one fixed command-center asset and reject path traversal."""
    try:
        decoded = unquote(str(request_path), errors="strict")
    except (UnicodeDecodeError, ValueError):
        return None
    if "\x00" in decoded or "\\" in decoded:
        return None
    relative = decoded.lstrip("/")
    if not relative or any(part in {"", ".", ".."} for part in relative.split("/")):
        return None
    root = ASSET_ROOT.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    mime, _ = mimetypes.guess_type(candidate.name)
    return candidate.read_bytes(), mime or "application/octet-stream"
