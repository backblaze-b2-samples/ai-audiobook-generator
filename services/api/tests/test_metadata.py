"""Tests for metadata extraction — audio path added, image path removed."""

from app.service import metadata as metadata_service
from app.service.metadata import extract_metadata


def test_checksums_always_present():
    md = extract_metadata(b"hello world", "notes.txt", "text/plain")
    assert md.md5 and md.sha256
    assert md.extension == "txt"
    assert md.size_bytes == 11


def test_no_image_fields_on_model():
    md = extract_metadata(b"data", "x.bin", "application/octet-stream")
    # Image fields were trimmed from FileMetadataDetail entirely.
    assert not hasattr(md, "image_width")
    assert not hasattr(md, "exif")


def test_audio_metadata_extracted(monkeypatch):
    monkeypatch.setattr(
        metadata_service,
        "_extract_audio_metadata",
        lambda data: {"duration_seconds": 30.5, "codec": "mp3", "bitrate": 128000},
    )
    md = extract_metadata(b"fakeaudio", "ch-001.mp3", "audio/mpeg")
    assert md.duration_seconds == 30.5
    assert md.codec == "mp3"
    assert md.bitrate == 128000


def test_pdf_branch_still_supported(monkeypatch):
    monkeypatch.setattr(
        metadata_service,
        "_extract_pdf_metadata",
        lambda data: {"pdf_pages": 12, "pdf_author": "A", "pdf_title": "T"},
    )
    md = extract_metadata(b"%PDF-1.4", "book.pdf", "application/pdf")
    assert md.pdf_pages == 12
    assert md.pdf_author == "A"
