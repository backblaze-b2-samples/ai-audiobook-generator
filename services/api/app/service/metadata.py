import hashlib
import io
import logging
from datetime import UTC, datetime

from app.types import FileMetadataDetail
from app.types.formatting import humanize_bytes

logger = logging.getLogger(__name__)


def _extract_pdf_metadata(file_data: bytes) -> dict:
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(file_data))
        info = reader.metadata
        return {
            "pdf_pages": len(reader.pages),
            "pdf_author": info.author if info else None,
            "pdf_title": info.title if info else None,
        }
    except Exception:
        logger.warning("PDF metadata extraction failed", exc_info=True)
        return {}


def _extract_audio_metadata(file_data: bytes) -> dict:
    """Read audio header metadata (duration/codec/bitrate) with mutagen.

    mutagen parses container headers only — no decoding, no ffmpeg — so this
    is cheap enough to run inline on every audio upload and on chapter renders.
    """
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(io.BytesIO(file_data))
        if audio is None or audio.info is None:
            return {}
        info = audio.info
        codec = type(info).__module__.rsplit(".", 1)[-1]
        return {
            "duration_seconds": round(getattr(info, "length", 0.0), 2) or None,
            "codec": codec or None,
            "bitrate": getattr(info, "bitrate", None) or None,
        }
    except Exception:
        logger.warning("Audio metadata extraction failed", exc_info=True)
        return {}


def extract_metadata(
    file_data: bytes,
    filename: str,
    content_type: str,
) -> FileMetadataDetail:
    md5 = hashlib.md5(file_data, usedforsecurity=False).hexdigest()
    sha256 = hashlib.sha256(file_data).hexdigest()
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    extra: dict = {}

    if content_type == "application/pdf":
        extra = _extract_pdf_metadata(file_data)
    elif content_type.startswith("audio/") or content_type.startswith("video/"):
        extra = _extract_audio_metadata(file_data)

    return FileMetadataDetail(
        filename=filename,
        size_bytes=len(file_data),
        size_human=humanize_bytes(len(file_data)),
        mime_type=content_type,
        extension=extension,
        md5=md5,
        sha256=sha256,
        uploaded_at=datetime.now(UTC),
        **extra,
    )
