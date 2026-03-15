"""Text cleaning utilities for the preprocessing pipeline.

Provides :class:`TextCleaner`, which strips HTML markup, normalizes Unicode
characters, collapses whitespace, and optionally lowercases text before it
reaches the embedding provider.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["TextCleaner"]

_HTML_TAGS = re.compile(r"<[^>]*>")
_WHITESPACE = re.compile(r"[ \t\r\n\f\v]+")


class TextCleaner:
    """Cleans raw text prior to embedding.

    Applies a configurable sequence of normalization steps:

    1. HTML tag removal (replaces tags with a single space).
    2. Unicode normalization to NFKC form (e.g. ligatures, full-width chars).
    3. Whitespace collapsing (tabs, newlines, multiple spaces → single space).
    4. Optional lowercasing.

    All steps are enabled by default except lowercasing, which can distort
    proper nouns and acronyms relevant to search.

    Args:
        strip_html: Remove HTML tags from the text.  Defaults to ``True``.
        normalize_unicode: Apply NFKC Unicode normalization.  Defaults to
            ``True``.
        lowercase: Convert the result to lowercase.  Defaults to ``False``.

    Example:
        >>> cleaner = TextCleaner()
        >>> cleaner.clean("<p>Hello   World\\n</p>")
        'Hello World'
    """

    def __init__(
        self,
        *,
        strip_html: bool = True,
        normalize_unicode: bool = True,
        lowercase: bool = False,
    ) -> None:
        self._strip_html = strip_html
        self._normalize_unicode = normalize_unicode
        self._lowercase = lowercase

    def clean(self, text: str) -> str:
        """Apply all enabled cleaning steps to *text*.

        Args:
            text: Raw input string.  Non-string values are coerced via
                ``str()``.

        Returns:
            Cleaned string.  Returns an empty string when the input is empty
            or reduces to nothing after cleaning.
        """
        if not isinstance(text, str):
            text = str(text)
        if not text:
            return ""

        if self._strip_html:
            text = _HTML_TAGS.sub(" ", text)

        if self._normalize_unicode:
            text = unicodedata.normalize("NFKC", text)

        text = _WHITESPACE.sub(" ", text).strip()

        if self._lowercase:
            text = text.lower()

        return text
