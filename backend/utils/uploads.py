"""Upload validation shared by every route that accepts a file."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass

from fastapi import HTTPException, status
from PIL import Image

MAX_PIXELS = 60_000_000          # decompression-bomb guard (~7750x7750)
_SIGNATURES = (
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"%PDF-", "pdf", "application/pdf"),
)


@dataclass
class ValidatedUpload:
    data: bytes
    extension: str        # canonical, derived from the file CONTENT (never from the client's filename)
    media_type: str

    @property
    def safe_filename(self) -> str:
        return f"upload.{self.extension}"


def max_upload_bytes() -> int:
    try:
        return int(os.getenv("MAX_FILE_SIZE_MB", "10")) * 1024 * 1024
    except ValueError:
        return 10 * 1024 * 1024


def validate_upload(data: bytes, declared_content_type: str | None) -> ValidatedUpload:
    """
    Enforce size, then identify the file by its magic bytes — the declared Content-Type and
    filename are client-controlled and are never trusted. Images must also decode and be of
    a sane size. Raises HTTPException (413 / 415 / 422).
    """
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The uploaded file is empty")
    if len(data) > max_upload_bytes():
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"File exceeds {max_upload_bytes() // (1024 * 1024)} MB limit")

    for magic, ext, media in _SIGNATURES:
        if data.startswith(magic):
            break
    else:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Unsupported file type. Allowed: JPG, PNG, PDF")

    if ext in ("jpg", "png"):
        try:
            with Image.open(io.BytesIO(data)) as im:
                w, h = im.size
                im.verify()
        except Exception:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The image file is corrupted or unreadable")
        if w * h > MAX_PIXELS:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image dimensions are too large")
    return ValidatedUpload(data, ext, media)
