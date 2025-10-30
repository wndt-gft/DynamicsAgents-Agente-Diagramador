"""Geração de artefatos de pré-visualização do layout das visões."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, MutableMapping

from .artifacts import SESSION_ARTIFACT_LAYOUT_PREVIEW
from .constants import DEFAULT_TEMPLATE, OUTPUT_DIR
from .rendering import render_view_layout
from .session import store_artifact
from .templates import TemplateMetadata, ViewMetadata, load_template_metadata

__all__ = ["generate_layout_preview"]


def _resolve_template_path(template_path: str | None) -> Path:
    path = Path(template_path) if template_path else DEFAULT_TEMPLATE
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _normalize_tokens(view_filter: Iterable[str] | str | None) -> set[str]:
    if view_filter is None:
        return set()
    if isinstance(view_filter, str):
        candidates = [token.strip().casefold() for token in view_filter.split(",")]
    else:
        candidates = [str(token).strip().casefold() for token in view_filter]
    return {token for token in candidates if token}


def _select_views(metadata: TemplateMetadata, view_filter: Iterable[str] | str | None) -> list[ViewMetadata]:
    tokens = _normalize_tokens(view_filter)
    if not tokens:
        return list(metadata.views)

    matched: list[ViewMetadata] = []
    for view in metadata.views:
        values = {view.identifier.casefold(), view.name.casefold()}
        if values & tokens:
            matched.append(view)
    if not matched:
        raise ValueError("Nenhuma visão do template corresponde ao filtro informado.")
    return matched


def _build_replacements(render_payload: dict[str, object], view_name: str) -> dict[str, object]:
    inline = render_payload.get("inline_markdown", "")
    download = render_payload.get("download_markdown", "")
    data_uri = render_payload.get("svg_data_uri", "")
    return {
        "layout_preview.inline": inline,
        "layout_preview.download": download,
        "layout_preview.svg": data_uri,
        "layout_preview.view_name": view_name,
    }


def generate_layout_preview(
    datamodel: str | dict | None,
    template_path: str | None,
    *,
    view_filter: Iterable[str] | str | None = None,
    session_state: MutableMapping[str, object] | None = None,
) -> dict[str, object]:
    target_template = _resolve_template_path(template_path)
    metadata = load_template_metadata(target_template)
    available_views = _select_views(metadata, view_filter)
    if not available_views:
        raise ValueError("O template selecionado não possui visões para pré-visualização.")

    primary_view = available_views[0]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    render_payload = render_view_layout(
        primary_view.name,
        primary_view.identifier,
        layout=None,
        output_dir=OUTPUT_DIR,
    )

    artifact = {
        "template": str(target_template),
        "view": {
            "identifier": primary_view.identifier,
            "name": primary_view.name,
        },
        "replacements": _build_replacements(render_payload, primary_view.name),
        "render": render_payload,
        "views": [
            {
                "identifier": view.identifier,
                "name": view.name,
                "index": view.index,
            }
            for view in available_views
        ],
    }

    if session_state is not None:
        store_artifact(session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW, artifact)
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_LAYOUT_PREVIEW,
            "view_name": primary_view.name,
        }

    return artifact
