"""Unit tests for chapter detection (marker-aware + size fallback)."""

from app.service.chapters import MAX_CHARS, split_into_chapters


def test_explicit_chapter_markers():
    text = (
        "Chapter 1\nThe beginning of the story.\n\n"
        "Chapter 2\nThe middle of the story.\n\n"
        "Chapter 3\nThe end of the story."
    )
    chapters = split_into_chapters(text)
    assert len(chapters) == 3
    assert [c.index for c in chapters] == [0, 1, 2]
    assert chapters[0].title == "Chapter 1"
    assert "beginning" in chapters[0].text
    assert chapters[2].char_count == len(chapters[2].text)


def test_markdown_heading_markers():
    text = "# Prologue\nOnce upon a time.\n\n## The Quest\nThey set out at dawn."
    chapters = split_into_chapters(text)
    assert len(chapters) == 2
    assert chapters[0].title == "Prologue"
    assert chapters[1].title == "The Quest"


def test_horizontal_rule_markers():
    text = "First part of the manuscript.\n\n---\n\nSecond part of the manuscript."
    chapters = split_into_chapters(text)
    assert len(chapters) == 2
    # Rules are unnamed boundaries -> auto-titled.
    assert chapters[0].title == "Chapter 1"
    assert chapters[1].title == "Chapter 2"


def test_size_fallback_for_unmarked_long_text():
    paragraph = "word " * 400  # ~2000 chars
    text = "\n\n".join([paragraph] * 8)  # ~16k chars, no markers
    chapters = split_into_chapters(text)
    assert len(chapters) > 1
    for c in chapters:
        assert c.char_count <= MAX_CHARS + len(paragraph)


def test_short_unmarked_text_is_single_chapter():
    text = "A short note with no chapter markers at all."
    chapters = split_into_chapters(text)
    assert len(chapters) == 1
    assert chapters[0].index == 0
    assert chapters[0].title == "Chapter 1"


def test_empty_text_yields_no_chapters():
    assert split_into_chapters("   \n  ") == []


def test_chapter_text_excluded_from_manifest_dump():
    chapters = split_into_chapters("Chapter 1\nHello there.")
    dumped = chapters[0].model_dump()
    assert "text" not in dumped
    assert dumped["title"] == "Chapter 1"
