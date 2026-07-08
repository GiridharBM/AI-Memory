"""Tests for ingestion text preprocessing."""

from app.infrastructure.ingestion.utils import clean_text


def test_clean_text_normalizes_whitespace_and_headings() -> None:
    raw_text = """

      ##     Important    Topic


    This     paragraph       has       uneven spacing.



    """

    assert clean_text(raw_text) == "## Important Topic\n\nThis paragraph has uneven spacing."


def test_clean_text_preserves_fenced_code_blocks() -> None:
    raw_text = """
Intro    text

```python
def example():
    value    = "keep internal spacing"
    return value
```

Outro       text
"""

    assert clean_text(raw_text) == (
        "Intro text\n\n"
        "```python\n"
        "def example():\n"
        "    value    = \"keep internal spacing\"\n"
        "    return value\n"
        "```\n\n"
        "Outro text"
    )


def test_clean_text_preserves_list_structure() -> None:
    raw_text = """
    -   first      item
      -     nested      item
    1.    numbered       item
    """

    assert clean_text(raw_text) == "- first item\n  - nested item\n1. numbered item"


def test_clean_text_preserves_markdown_blockquotes() -> None:
    raw_text = """
    >     quoted       idea
    >>       nested      quote
    """

    assert clean_text(raw_text) == "> quoted idea\n> > nested quote"
