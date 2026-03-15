"""Unit tests for semantic_search.preprocessing.cleaner.TextCleaner."""

import pytest

from semantic_search.preprocessing.cleaner import TextCleaner


class TestTextCleanerDefaults:
    """TextCleaner with default settings (strip_html=True, normalize_unicode=True, lowercase=False)."""

    def setup_method(self) -> None:
        self.cleaner = TextCleaner()

    def test_strips_simple_html_tags(self) -> None:
        assert self.cleaner.clean("<p>Hello world</p>") == "Hello world"

    def test_strips_nested_html(self) -> None:
        result = self.cleaner.clean("<div><b>Title</b><span> body text</span></div>")
        assert result == "Title body text"

    def test_replaces_html_tag_with_space_not_nothing(self) -> None:
        # Adjacent tags should not merge words
        result = self.cleaner.clean("word<br/>next")
        assert result == "word next"

    def test_collapses_multiple_spaces(self) -> None:
        assert self.cleaner.clean("hello   world") == "hello world"

    def test_collapses_tabs_and_newlines(self) -> None:
        assert self.cleaner.clean("hello\t\nworld") == "hello world"

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert self.cleaner.clean("  hello world  ") == "hello world"

    def test_empty_string_returns_empty(self) -> None:
        assert self.cleaner.clean("") == ""

    def test_only_whitespace_returns_empty(self) -> None:
        assert self.cleaner.clean("   \t\n  ") == ""

    def test_non_string_coerced(self) -> None:
        assert self.cleaner.clean(42) == "42"  # type: ignore[arg-type]

    def test_unicode_normalization_ligature(self) -> None:
        # 'ﬁ' (U+FB01 LATIN SMALL LIGATURE FI) → 'fi'
        result = self.cleaner.clean("\uFB01le")
        assert result == "file"

    def test_unicode_normalization_fullwidth(self) -> None:
        # Full-width 'Ａ' (U+FF21) → 'A'
        result = self.cleaner.clean("\uFF21BC")
        assert result == "ABC"

    def test_plain_text_unchanged_aside_from_whitespace(self) -> None:
        text = "This is a normal sentence."
        assert self.cleaner.clean(text) == text

    def test_preserves_case_by_default(self) -> None:
        assert self.cleaner.clean("Hello WORLD") == "Hello WORLD"


class TestTextCleanerLowercase:
    """TextCleaner with lowercase=True."""

    def setup_method(self) -> None:
        self.cleaner = TextCleaner(lowercase=True)

    def test_lowercases_text(self) -> None:
        assert self.cleaner.clean("Hello WORLD") == "hello world"

    def test_lowercase_after_html_strip(self) -> None:
        assert self.cleaner.clean("<B>TITLE</B>") == "title"


class TestTextCleanerDisabledSteps:
    """TextCleaner with individual steps disabled."""

    def test_html_not_stripped_when_disabled(self) -> None:
        cleaner = TextCleaner(strip_html=False)
        result = cleaner.clean("<p>hello</p>")
        assert "<p>" in result

    def test_unicode_not_normalized_when_disabled(self) -> None:
        cleaner = TextCleaner(normalize_unicode=False)
        # ligature should survive
        result = cleaner.clean("\uFB01le")
        assert result == "\uFB01le"

    def test_all_steps_disabled_preserves_input(self) -> None:
        cleaner = TextCleaner(strip_html=False, normalize_unicode=False)
        text = "<p>Hello  World\n</p>"
        # Only whitespace collapse still runs
        result = cleaner.clean(text)
        assert result == "<p>Hello World </p>"
