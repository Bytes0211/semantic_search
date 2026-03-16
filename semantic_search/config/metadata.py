"""Shared metadata splitting helper.

Consolidates the ``_split_metadata`` function that was previously
duplicated across every ``scripts/generate_*_index.py`` file.  Import
from here instead of copying the function into each script.
"""

from __future__ import annotations

from typing import Any, Dict, Set


def split_metadata(
    flat_metadata: Dict[str, Any],
    detail_field_names: Set[str],
) -> Dict[str, Any]:
    """Separate flat metadata into display fields and a nested ``_detail`` dict.

    Fields whose names appear in *detail_field_names* are moved into a
    ``_detail`` sub-dict so the frontend can show them only when the user
    expands the drill-down panel.  All remaining fields stay at the top
    level for result-card display.

    Args:
        flat_metadata: All metadata fields returned by a connector.
        detail_field_names: Field names that belong in the ``_detail``
            block.

    Returns:
        A new metadata dict with top-level display fields and, when at
        least one detail field is present, a ``_detail`` sub-dict.
    """
    display: Dict[str, Any] = {}
    detail: Dict[str, Any] = {}
    for key, value in flat_metadata.items():
        if key in detail_field_names:
            detail[key] = value
        else:
            display[key] = value
    if detail:
        display["_detail"] = detail
    return display
