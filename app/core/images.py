"""Validation and local-disk storage for user-uploaded recipe photos.

No image-processing library is available in this project yet, so file type is
verified by sniffing the leading "magic bytes" of the upload rather than
trusting the client-supplied filename or Content-Type header (both are
attacker-controlled) — this is the same class of check `imghdr` used to do
before its removal from the standard library.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.globals import settings

# Signature -> (file extension, human-readable label). Order matters: WEBP's
# signature check also requires bytes 8-11 to equal b"WEBP", handled separately.
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_GIF_SIGNATURES = (b"GIF87a", b"GIF89a")
_RIFF_SIGNATURE = b"RIFF"
_WEBP_SIGNATURE = b"WEBP"


class ImageValidationError(ValueError):
    """Raised when an uploaded file fails the photo type/size checks."""


def _sniff_extension(header: bytes) -> str | None:
    if header.startswith(_JPEG_SIGNATURE):
        return "jpg"
    if header.startswith(_PNG_SIGNATURE):
        return "png"
    if header.startswith(_GIF_SIGNATURES):
        return "gif"
    if header.startswith(_RIFF_SIGNATURE) and header[8:12] == _WEBP_SIGNATURE:
        return "webp"
    return None


def _upload_root() -> Path:
    root = Path(settings.upload_dir) / "recipes"
    root.mkdir(parents=True, exist_ok=True)
    return root


async def save_recipe_image(upload: UploadFile) -> str:
    """Validate and persist an uploaded recipe photo.

    Returns the relative path (under `settings.upload_dir`) it was saved to.
    Raises ImageValidationError if the file isn't a supported image type or
    exceeds the configured size limit.
    """
    contents = await upload.read()
    if len(contents) > settings.max_image_size_bytes:
        max_mb = settings.max_image_size_bytes / (1024 * 1024)
        raise ImageValidationError(f"Image must be no larger than {max_mb:.0f}MB.")
    if not contents:
        raise ImageValidationError("Uploaded file is empty.")

    extension = _sniff_extension(contents[:16])
    if extension is None:
        raise ImageValidationError("File must be a JPEG, PNG, GIF, or WEBP image.")

    filename = f"{uuid.uuid4().hex}.{extension}"
    destination = _upload_root() / filename
    destination.write_bytes(contents)
    return f"recipes/{filename}"


def delete_recipe_image(relative_path: str) -> None:
    """Best-effort delete; missing files are not an error (already gone)."""
    full_path = Path(settings.upload_dir) / relative_path
    full_path.unlink(missing_ok=True)


def image_url(relative_path: str | None) -> str | None:
    if relative_path is None:
        return None
    return f"{settings.media_url_prefix}/{relative_path}"
