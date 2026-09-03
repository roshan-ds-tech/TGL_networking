"""Payment-screenshot storage.

Threat model handled here:
  * Content-type spoofing  -> the real bytes are sniffed, the client's declared
    Content-Type is never trusted.
  * Path traversal         -> the stored name is a server-generated UUID; the
    client filename is discarded entirely, and reads are re-checked to be
    inside the upload root.
  * Oversized uploads      -> streamed in chunks with a hard byte ceiling, so a
    huge file cannot exhaust memory before being rejected.
  * Stored XSS / drive-by  -> only image + PDF signatures are accepted, and the
    read endpoint sends nosniff with a locked-down CSP.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from .config import settings

# (signature, offset, mime, extension)
_SIGNATURES: list[tuple[bytes, int, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", 0, "image/png", ".png"),
    (b"\xff\xd8\xff", 0, "image/jpeg", ".jpg"),
    (b"%PDF-", 0, "application/pdf", ".pdf"),
    (b"GIF87a", 0, "image/gif", ".gif"),
    (b"GIF89a", 0, "image/gif", ".gif"),
]

_CHUNK = 64 * 1024


def upload_root() -> Path:
    root = Path(settings.upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sniff(head: bytes) -> tuple[str, str] | None:
    for sig, offset, mime, ext in _SIGNATURES:
        if head[offset : offset + len(sig)] == sig:
            return mime, ext
    # WebP: "RIFF" .... "WEBP"
    if head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


async def save_payment_proof(upload: UploadFile) -> tuple[str, str, int]:
    """Validate and persist an upload. Returns (filename, mime, size)."""
    head = await upload.read(32)
    sniffed = _sniff(head)
    if sniffed is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Payment proof must be a PNG, JPG, WEBP, GIF or PDF file.",
        )
    mime, ext = sniffed

    filename = f"{uuid.uuid4().hex}{ext}"
    destination = upload_root() / filename

    size = 0
    try:
        with destination.open("wb") as out:
            out.write(head)
            size += len(head)
            while chunk := await upload.read(_CHUNK):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            "Payment proof exceeds "
                            f"{settings.max_upload_bytes // (1024 * 1024)} MB."
                        ),
                    )
                out.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    if size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Payment proof file is empty.")

    return filename, mime, size


def resolve_proof(filename: str) -> Path:
    """Resolve a stored filename, refusing anything that escapes the root."""
    root = upload_root()
    candidate = (root / filename).resolve()
    if not candidate.is_file() or root not in candidate.parents:
        raise HTTPException(status_code=404, detail="Payment proof not found")
    return candidate
