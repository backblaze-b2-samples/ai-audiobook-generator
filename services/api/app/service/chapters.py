"""Split a manuscript into ordered chapters.

Strategy:
  1. Marker-aware split — honor explicit chapter boundaries:
       * lines like `Chapter 1`, `CHAPTER IV`, `Chapter One:`
       * Markdown headings (`# Title`, `## Title`)
       * horizontal rules (`---`, `***`, `___`)
  2. Size-based fallback — if no markers are found, chunk by paragraph into
     pieces under `MAX_CHARS`, never splitting mid-paragraph.

Returns ordered Chapter models (index, title, text, char_count).
"""

import re

from app.types import Chapter

MAX_CHARS = 8000  # ~ a few minutes of narration per fallback chunk

_HEADING_RE = re.compile(r"^\s{0,3}#{1,3}\s+(?P<title>.+?)\s*#*\s*$")
_CHAPTER_RE = re.compile(
    r"^\s*(?:chapter|part|book|section)\b[\s:.\-]*(?P<rest>.*)$",
    re.IGNORECASE,
)
_RULE_RE = re.compile(r"^\s*([-*_])\1{2,}\s*$")


def _is_marker(line: str) -> str | None:
    """Return a chapter title if `line` is a boundary marker, else None."""
    m = _HEADING_RE.match(line)
    if m:
        return m.group("title").strip()
    m = _CHAPTER_RE.match(line)
    if m:
        title = line.strip()
        # Require the marker to be a short standalone line, not prose that
        # merely starts with the word "Chapter".
        if len(title) <= 80:
            return title
    if _RULE_RE.match(line):
        return ""  # rule = unnamed boundary
    return None


def _finalize(index: int, title: str, body: list[str]) -> Chapter | None:
    text = "\n".join(body).strip()
    if not text:
        return None
    return Chapter(
        index=index,
        title=title or f"Chapter {index + 1}",
        char_count=len(text),
        text=text,
    )


def _split_by_markers(text: str) -> list[Chapter]:
    chapters: list[Chapter] = []
    current_title = ""
    body: list[str] = []
    for line in text.splitlines():
        marker = _is_marker(line)
        if marker is not None:
            ch = _finalize(len(chapters), current_title, body)
            if ch:
                chapters.append(ch)
            current_title = marker
            body = []
        else:
            body.append(line)
    ch = _finalize(len(chapters), current_title, body)
    if ch:
        chapters.append(ch)
    return chapters


def _split_by_size(text: str) -> list[Chapter]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chapters: list[Chapter] = []
    buf: list[str] = []
    size = 0
    for para in paragraphs:
        if buf and size + len(para) > MAX_CHARS:
            ch = _finalize(len(chapters), "", buf)
            if ch:
                chapters.append(ch)
            buf, size = [], 0
        buf.append(para)
        size += len(para)
    ch = _finalize(len(chapters), "", buf)
    if ch:
        chapters.append(ch)
    return chapters


def split_into_chapters(text: str) -> list[Chapter]:
    """Split `text` into ordered chapters (marker-aware, size fallback)."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    chapters = _split_by_markers(text)
    # If markers produced a single oversized chapter (no real markers found),
    # fall back to size-based chunking for that chapter.
    if len(chapters) <= 1 and len(text) > MAX_CHARS:
        return _split_by_size(text)
    if not chapters:
        return _split_by_size(text)
    # Re-index defensively so indexes are contiguous 0..n-1.
    for i, ch in enumerate(chapters):
        ch.index = i
        if not ch.title:
            ch.title = f"Chapter {i + 1}"
    return chapters
