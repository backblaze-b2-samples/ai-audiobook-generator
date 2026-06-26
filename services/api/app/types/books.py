from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class NarrationStatus(StrEnum):
    """Lifecycle of a book (and of each chapter render within it)."""

    PENDING = "pending"
    RENDERING = "rendering"
    ASSEMBLING = "assembling"
    COMPLETE = "complete"
    FAILED = "failed"


class Voice(BaseModel):
    """A single narrator voice offered by the active TTS provider."""

    id: str
    name: str
    description: str | None = None


class Chapter(BaseModel):
    index: int
    title: str
    char_count: int
    status: NarrationStatus = NarrationStatus.PENDING
    # Text is kept on the in-memory chapter for narration but is NOT serialized
    # into the manifest (the full source lives in source.txt). Excluded below.
    text: str = Field(default="", exclude=True)
    audio_key: str | None = None
    duration_seconds: float | None = None
    error: str | None = None


class Book(BaseModel):
    """Full book record. This is exactly what manifest.json stores in B2."""

    id: str
    owner_id: str = "local-dev"
    title: str
    status: NarrationStatus = NarrationStatus.PENDING
    voice_id: str
    chapters: list[Chapter] = []
    master_key: str | None = None
    created_at: datetime
    updated_at: datetime
    error: str | None = None

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)

    @property
    def chapters_rendered(self) -> int:
        return sum(
            1 for c in self.chapters if c.status == NarrationStatus.COMPLETE
        )

    @property
    def duration_seconds(self) -> float:
        return sum(c.duration_seconds or 0.0 for c in self.chapters)


class ChapterDetail(BaseModel):
    index: int
    title: str
    char_count: int
    status: NarrationStatus
    audio_key: str | None = None
    duration_seconds: float | None = None
    error: str | None = None


class BookDetail(BaseModel):
    """API response shape for a single book (mirrors the shared `Book` TS type).

    Differs from the stored `Book` manifest by exposing the derived counts and
    human-readable duration as concrete fields and omitting per-chapter text.
    """

    id: str
    title: str
    status: NarrationStatus
    voice_id: str
    chapter_count: int
    chapters_rendered: int
    duration_seconds: float
    duration_human: str
    master_key: str | None = None
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    chapters: list[ChapterDetail] = []


class BookSummary(BaseModel):
    id: str
    title: str
    status: NarrationStatus
    chapter_count: int
    chapters_rendered: int
    duration_seconds: float
    duration_human: str
    created_at: datetime


class CreateBookRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)
    voice_id: str | None = None


class BookStats(BaseModel):
    total_books: int
    total_chapters: int
    total_duration_seconds: float
    total_duration_human: str
    total_size_bytes: int
    total_size_human: str


class DailyNarrationHours(BaseModel):
    date: str
    hours: float
