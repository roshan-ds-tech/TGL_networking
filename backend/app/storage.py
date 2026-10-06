"""Payment-screenshot storage.

Threat model handled here:
  * Content-type spoofing  -> the real bytes are sniffed, the client's declared
    Content-Type is never trusted.
  * Path traversal         -> the stored name is a server-generated UUID; the
    client filename is discarded entirely, and every read/delete re-checks the
    stored name against the exact shape this module generates.
  * Oversized uploads      -> read in chunks with a hard byte ceiling, so a
    huge file cannot exhaust memory before being rejected.
  * Stored XSS / drive-by  -> only image + PDF signatures are accepted, and the
    read endpoint sends nosniff with a locked-down CSP.

Two backends, same interface:
  * local    — files under settings.upload_dir. Development, tests, and any
               host with a persistent disk.
  * supabase — a PRIVATE Supabase Storage bucket, reached server-side with the
               service-role key. Production on Render, whose web services have
               no persistent disk unless one is paid for and attached. Objects
               are never publicly readable; the admin endpoint streams them.
"""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from . import http_client
from .config import settings

logger = logging.getLogger("tgl")

# (signature, offset, mime, extension)
_SIGNATURES: list[tuple[bytes, int, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", 0, "image/png", ".png"),
    (b"\xff\xd8\xff", 0, "image/jpeg", ".jpg"),
    (b"%PDF-", 0, "application/pdf", ".pdf"),
    (b"GIF87a", 0, "image/gif", ".gif"),
    (b"GIF89a", 0, "image/gif", ".gif"),
]

_CHUNK = 64 * 1024
# Exactly what save_payment_proof generates — anything else is refused before
# it reaches a filesystem path or a storage URL.
_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|pdf|gif|webp)$")


def _use_supabase() -> bool:
    return settings.storage_backend == "supabase"


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


# ---------------------------------------------------------------- supabase ---

def _sb_headers(content_type: str | None = None) -> dict[str, str]:
    key = settings.supabase_service_role_key
    headers = {"apikey": key}
    # Legacy service_role keys are JWTs and go in Authorization too; the newer
    # sb_secret_ keys are accepted via the apikey header alone.
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _sb_object_url(filename: str, bucket: str | None = None) -> str:
    base = settings.supabase_url.rstrip("/")
    return f"{base}/storage/v1/object/{bucket or settings.supabase_storage_bucket}/{filename}"


async def _sb_put(filename: str, data: bytes, mime: str, bucket: str | None = None) -> None:
    r = await http_client.request(
        "POST",
        _sb_object_url(filename, bucket),
        content=data,
        headers={**_sb_headers(mime), "x-upsert": "false", "Cache-Control": "no-store"},
    )
    if r.status_code >= 300:
        logger.error("Supabase Storage upload failed: HTTP %s", r.status_code)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "We couldn't store your payment proof just now. Please try again in a minute.",
        )


async def _sb_get(filename: str, bucket: str | None = None) -> bytes:
    r = await http_client.request("GET", _sb_object_url(filename, bucket), headers=_sb_headers())
    if r.status_code in (400, 404):
        raise HTTPException(status_code=404, detail="Payment proof not found")
    if r.status_code >= 300:
        logger.error("Supabase Storage download failed: HTTP %s", r.status_code)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Payment proof storage is unavailable.")
    return r.content


async def _sb_delete(filename: str, bucket: str | None = None) -> bool:
    base = settings.supabase_url.rstrip("/")
    r = await http_client.request(
        "DELETE",
        f"{base}/storage/v1/object/{bucket or settings.supabase_storage_bucket}",
        json={"prefixes": [filename]},
        headers=_sb_headers("application/json"),
    )
    if r.status_code >= 300:
        logger.error("Supabase Storage delete failed: HTTP %s", r.status_code)
        return False
    return bool(r.json()) if r.content else False


async def _ensure_bucket(bucket: str, size_limit: int, mime_types: list[str]) -> None:
    base = settings.supabase_url.rstrip("/")
    r = await http_client.request("GET", f"{base}/storage/v1/bucket/{bucket}", headers=_sb_headers())
    if r.status_code == 200:
        if r.json().get("public"):
            # Never serve proofs or member photos from a public bucket.
            logger.error("Supabase bucket %r is PUBLIC — make it private in the Supabase dashboard.", bucket)
        return
    r = await http_client.request(
        "POST",
        f"{base}/storage/v1/bucket",
        json={"id": bucket, "name": bucket, "public": False, "file_size_limit": size_limit, "allowed_mime_types": mime_types},
        headers=_sb_headers("application/json"),
    )
    if r.status_code >= 300 and r.status_code != 409:
        logger.error("Could not create Supabase bucket %r: HTTP %s", bucket, r.status_code)


async def init_storage() -> None:
    """Make sure the storage targets exist. Safe to run on every boot."""
    if not _use_supabase():
        upload_root()
        photo_root()
        return
    await _ensure_bucket(
        settings.supabase_storage_bucket,
        settings.max_upload_bytes,
        ["image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"],
    )
    await _ensure_bucket(settings.supabase_photos_bucket, PHOTO_STORED_MAX_BYTES, ["image/jpeg"])


# ------------------------------------------------------------------ public ---

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

    # Bounded read: the ceiling is enforced chunk by chunk, before the whole
    # body is ever held in memory.
    buf = bytearray(head)
    while chunk := await upload.read(_CHUNK):
        buf += chunk
        if len(buf) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Payment proof exceeds {settings.max_upload_bytes // (1024 * 1024)} MB.",
            )
    if not buf:
        raise HTTPException(status_code=400, detail="Payment proof file is empty.")

    if _use_supabase():
        await _sb_put(filename, bytes(buf), mime)
    else:
        (upload_root() / filename).write_bytes(buf)
    return filename, mime, len(buf)


def _checked(filename: str) -> str | None:
    return filename if _NAME_RE.fullmatch(filename or "") else None


async def read_proof(filename: str) -> bytes:
    """Bytes of a stored proof. 404 for anything unknown or malformed."""
    name = _checked(filename)
    if name is None:
        raise HTTPException(status_code=404, detail="Payment proof not found")
    if _use_supabase():
        return await _sb_get(name)
    root = upload_root()
    candidate = (root / name).resolve()
    if not candidate.is_file() or root not in candidate.parents:
        raise HTTPException(status_code=404, detail="Payment proof not found")
    return candidate.read_bytes()


async def delete_proof(filename: str) -> bool:
    """Delete a stored proof. Returns True if something was removed.

    A missing or malformed name is not an error: the caller is deleting the
    registration either way, and a proof that is already gone must not block
    that.
    """
    name = _checked(filename)
    if name is None:
        return False
    if _use_supabase():
        return await _sb_delete(name)
    root = upload_root()
    candidate = (root / name).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return False
    candidate.unlink(missing_ok=True)
    return True


# ------------------------------------------------------------ profile photos ---
# Accepted as PNG / JPEG / WebP up to PHOTO_UPLOAD_MAX_BYTES, then RE-ENCODED
# server-side (Pillow) to a square JPEG of at most PHOTO_SIZE px:
#   * strips every byte of metadata — phone photos carry GPS location in EXIF;
#   * normalises orientation, colour mode and size (fast directory pages);
#   * anything that isn't a decodable image is refused, and decompression
#     bombs are rejected before they are decoded.
PHOTO_UPLOAD_MAX_BYTES = 5 * 1024 * 1024
PHOTO_STORED_MAX_BYTES = 1024 * 1024
PHOTO_SIZE = 512
_PHOTO_MAX_PIXELS = 40_000_000
_PHOTO_NAME_RE = re.compile(r"^[0-9a-f]{32}\.jpg$")


def photo_root() -> Path:
    root = (Path(settings.upload_dir) / "photos").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _process_photo(raw: bytes) -> bytes:
    import io
    import warnings

    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = _PHOTO_MAX_PIXELS
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            img = Image.open(io.BytesIO(raw))
            if img.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("format")
            img.load()
        except Exception as exc:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Photo must be a PNG, JPG or WEBP image."
            ) from exc
    img = ImageOps.exif_transpose(img)
    img = ImageOps.fit(img.convert("RGB"), (PHOTO_SIZE, PHOTO_SIZE), method=Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)  # no exif/icc passed: metadata stripped
    return out.getvalue()


async def save_profile_photo(upload: UploadFile) -> str:
    """Validate, re-encode and store a profile photo. Returns its stored name."""
    import anyio

    head = await upload.read(32)
    sniffed = _sniff(head)
    if sniffed is None or sniffed[0] not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Photo must be a PNG, JPG or WEBP image.")
    buf = bytearray(head)
    while chunk := await upload.read(_CHUNK):
        buf += chunk
        if len(buf) > PHOTO_UPLOAD_MAX_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Photo must be under 5 MB.")
    data = await anyio.to_thread.run_sync(_process_photo, bytes(buf))  # CPU work off the event loop
    name = f"{uuid.uuid4().hex}.jpg"
    if _use_supabase():
        await _sb_put(name, data, "image/jpeg", settings.supabase_photos_bucket)
    else:
        (photo_root() / name).write_bytes(data)
    return name


async def read_profile_photo(name: str) -> bytes:
    if not _PHOTO_NAME_RE.fullmatch(name or ""):
        raise HTTPException(status_code=404, detail="Photo not found")
    if _use_supabase():
        return await _sb_get(name, settings.supabase_photos_bucket)
    candidate = (photo_root() / name).resolve()
    if not candidate.is_file() or photo_root() not in candidate.parents:
        raise HTTPException(status_code=404, detail="Photo not found")
    return candidate.read_bytes()


async def delete_profile_photo(name: str | None) -> bool:
    if not name or not _PHOTO_NAME_RE.fullmatch(name):
        return False
    if _use_supabase():
        return await _sb_delete(name, settings.supabase_photos_bucket)
    candidate = (photo_root() / name).resolve()
    if photo_root() not in candidate.parents or not candidate.is_file():
        return False
    candidate.unlink(missing_ok=True)
    return True
