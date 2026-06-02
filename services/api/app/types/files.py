from datetime import datetime

from pydantic import BaseModel


class FileMetadata(BaseModel):
    key: str
    filename: str
    folder: str
    size_bytes: int
    size_human: str
    content_type: str
    uploaded_at: datetime
    url: str | None = None


class FileMetadataDetail(BaseModel):
    filename: str
    size_bytes: int
    size_human: str
    mime_type: str
    extension: str
    md5: str
    sha256: str
    uploaded_at: datetime
    # PDF-specific (ebook manuscript sources)
    pdf_pages: int | None = None
    pdf_author: str | None = None
    pdf_title: str | None = None
    # Audio (chapter renders + master)
    duration_seconds: float | None = None
    codec: str | None = None
    bitrate: int | None = None
