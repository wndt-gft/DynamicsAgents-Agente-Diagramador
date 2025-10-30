"""Tool para renderizar layouts em SVG/PNG a partir de dados estruturados."""

from __future__ import annotations

import json
from typing import Any, Mapping, MutableMapping

from ..diagramador import OUTPUT_DIR, SESSION_ARTIFACT_LAYOUT_PREVIEW
from ..diagramador.rendering import render_view_layout
from ..diagramador.session import store_artifact
from ...utils import coerce_session_state, empty_string_to_none

__all__ = ["SESSION_ARTIFACT_LAYOUT_PREVIEW", "render_svg_preview"]


def _coerce_layout(layout: Any) -> Mapping[str, Any] | None:
    if layout is None:
        return None
    if isinstance(layout, Mapping):
        return layout
    if isinstance(layout, str):
        payload = layout.strip()
        if not payload:
            return None
        return json.loads(payload)
    raise TypeError("layout must be mapping, string or null")


def render_svg_preview(
    view_name: str,
    view_alias: str | None,
    layout: Mapping[str, Any] | str | None,
    session_state: str | MutableMapping[str, Any] | None = None,
):
    state = coerce_session_state(session_state)
    layout_payload = _coerce_layout(layout)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    preview = render_view_layout(
        view_name,
        empty_string_to_none(view_alias) or view_name,
        layout_payload,
        output_dir=OUTPUT_DIR,
    )

    if state is not None and isinstance(preview, Mapping):
        replacements = {
            "layout_preview.inline": preview.get("inline_markdown", ""),
            "layout_preview.download": preview.get("download_markdown", ""),
            "layout_preview.svg": preview.get("svg_data_uri", ""),
            "layout_preview.view_name": view_name,
        }
        artifact = {
            "view": {"name": view_name},
            "render": preview,
            "replacements": replacements,
        }
        store_artifact(state, SESSION_ARTIFACT_LAYOUT_PREVIEW, artifact)
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_LAYOUT_PREVIEW,
            "format": preview.get("format"),
            "path": preview.get("local_path"),
        }

    return preview
