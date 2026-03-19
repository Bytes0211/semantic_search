"""Display configuration dataclasses for UI rendering.

Defines how search results are presented in the web UI: which metadata
fields appear as result-card columns, which detail fields appear in the
drill-down panel, what labels to use, and what order to render them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class DisplayConfigError(ValueError):
    """Raised when display configuration is invalid."""


@dataclass(frozen=True, slots=True)
class ColumnConfig:
    """A single metadata column shown on a result card.

    Attributes:
        field: Metadata key to display.
        label: Human-readable label shown in the UI.  Defaults to the
            field name with the first letter capitalised.
        type: Optional column type hint for UI rendering.  Supported
            values: ``"link"`` (render as a clickable anchor).  Defaults
            to ``None`` (plain text).
        link_field: Optional metadata key whose value supplies the URL
            for ``type="link"`` columns.  When set, ``field`` provides
            the display text and ``link_field`` provides the href.
            When absent, ``field`` is used for both.
    """

    field: str
    label: str = ""
    type: Optional[str] = None
    link_field: Optional[str] = None

    def __post_init__(self) -> None:
        """Auto-derive label from field name when not provided."""
        if not self.field:
            raise DisplayConfigError("Column 'field' must be non-empty.")
        if not self.label:
            object.__setattr__(self, "label", self.field.replace("_", " ").title())


@dataclass(frozen=True, slots=True)
class DetailSectionConfig:
    """A single detail section shown in the drill-down panel.

    Attributes:
        field: Detail key to display.
        label: Human-readable label.  Defaults to the field name with
            the first letter capitalised.
    """

    field: str
    label: str = ""

    def __post_init__(self) -> None:
        """Auto-derive label from field name when not provided."""
        if not self.field:
            raise DisplayConfigError("Detail section 'field' must be non-empty.")
        if not self.label:
            object.__setattr__(self, "label", self.field.replace("_", " ").title())


@dataclass(frozen=True, slots=True)
class DisplayConfig:
    """Complete display configuration for a single data source.

    Attributes:
        title_field: Metadata field to use as the result card heading.
            Falls back to ``record_id`` in the frontend when absent.
        columns: Ordered list of metadata columns for the result card.
        detail_sections: Ordered list of detail sections for the
            drill-down panel.
    """

    title_field: Optional[str] = None
    columns: List[ColumnConfig] = field(default_factory=list)
    detail_sections: List[DetailSectionConfig] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict suitable for JSON responses.

        Returns:
            Dict matching the ``/v1/config`` ``display`` schema.
        """
        return {
            "title_field": self.title_field,
            "columns": [
                {
                    "field": c.field,
                    "label": c.label,
                    **({"type": c.type} if c.type else {}),
                    **({"link_field": c.link_field} if c.link_field else {}),
                }
                for c in self.columns
            ],
            "detail_sections": [
                {"field": s.field, "label": s.label} for s in self.detail_sections
            ],
        }


def parse_display_config(raw: Dict[str, Any]) -> DisplayConfig:
    """Parse a ``display`` block from a source YAML into a :class:`DisplayConfig`.

    Args:
        raw: The ``display`` mapping from the source configuration file.

    Returns:
        A validated :class:`DisplayConfig` instance.

    Raises:
        DisplayConfigError: If required fields are missing or malformed.
    """
    if not raw or not isinstance(raw, dict):
        return DisplayConfig()

    result_card = raw.get("result_card") or {}
    record_detail = raw.get("record_detail") or {}

    title_field = result_card.get("title_field")

    columns: List[ColumnConfig] = []
    for entry in result_card.get("columns") or []:
        if isinstance(entry, str):
            columns.append(ColumnConfig(field=entry))
        elif isinstance(entry, dict):
            columns.append(
                ColumnConfig(
                    field=entry.get("field", ""),
                    label=entry.get("label", ""),
                    type=entry.get("type"),
                    link_field=entry.get("link_field"),
                )
            )
        else:
            raise DisplayConfigError(
                f"Invalid column entry: expected string or dict, got {type(entry).__name__}."
            )

    detail_sections: List[DetailSectionConfig] = []
    for entry in record_detail.get("sections") or []:
        if isinstance(entry, str):
            detail_sections.append(DetailSectionConfig(field=entry))
        elif isinstance(entry, dict):
            detail_sections.append(
                DetailSectionConfig(
                    field=entry.get("field", ""),
                    label=entry.get("label", ""),
                )
            )
        else:
            raise DisplayConfigError(
                f"Invalid detail section entry: expected string or dict, got {type(entry).__name__}."
            )

    return DisplayConfig(
        title_field=title_field,
        columns=columns,
        detail_sections=detail_sections,
    )
