"""Funções utilitárias para descoberta e descrição de templates ArchiMate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, MutableMapping
from xml.etree import ElementTree as ET

from .artifacts import (
    SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
    SESSION_ARTIFACT_TEMPLATE_LISTING,
)
from .constants import ARCHIMATE_NS, DEFAULT_TEMPLATE, DEFAULT_TEMPLATES_DIR
from .session import get_cached_blueprint, store_artifact, store_blueprint

__all__ = [
    "TemplateMetadata",
    "ViewMetadata",
    "DEFAULT_TEMPLATE",
    "load_template_metadata",
    "list_templates",
    "describe_template",
]


@dataclass(frozen=True)
class ViewMetadata:
    identifier: str
    name: str
    documentation: str | None
    viewpoint: str | None
    index: int


@dataclass(frozen=True)
class TemplateMetadata:
    path: Path
    model_identifier: str | None
    model_name: str | None
    documentation: str | None
    views: tuple[ViewMetadata, ...]

    @property
    def absolute_path(self) -> Path:
        return self.path.resolve()


_NS = {"a": ARCHIMATE_NS}


def _resolve_templates_dir(directory: str | None) -> Path:
    base = Path(directory) if directory else DEFAULT_TEMPLATES_DIR
    if not base.is_absolute():
        base = Path.cwd() / base
    return base.resolve()


def _read_text(element) -> str | None:
    if element is None or element.text is None:
        return None
    text = element.text.strip()
    return text or None


def load_template_metadata(template_path: Path) -> TemplateMetadata:
    tree = ET.parse(str(template_path))
    root = tree.getroot()
    model_id = root.get("identifier")
    model_name = _read_text(root.find("a:name", _NS))
    documentation = _read_text(root.find("a:documentation", _NS))

    views: list[ViewMetadata] = []
    for index, view in enumerate(root.findall("a:views/a:diagrams/a:view", _NS)):
        identifier = view.get("identifier") or f"view-{index+1}"
        name = _read_text(view.find("a:name", _NS)) or identifier
        doc = _read_text(view.find("a:documentation", _NS))
        viewpoint = view.get("viewpoint") or view.get("viewpointRef")
        views.append(
            ViewMetadata(
                identifier=identifier,
                name=name,
                documentation=doc,
                viewpoint=viewpoint,
                index=index,
            )
        )

    return TemplateMetadata(
        path=template_path,
        model_identifier=model_id,
        model_name=model_name,
        documentation=documentation,
        views=tuple(views),
    )


def list_templates(
    directory: str | None = None,
    *,
    session_state: MutableMapping[str, object] | None = None,
) -> dict[str, object]:
    templates_dir = _resolve_templates_dir(directory)
    if not templates_dir.exists():
        raise FileNotFoundError(f"Diretório de templates não encontrado: {templates_dir}")

    metadata: list[dict[str, object]] = []
    for xml_file in sorted(templates_dir.rglob("*.xml")):
        try:
            template_meta = load_template_metadata(xml_file)
        except ET.ParseError:
            continue

        metadata.append(
            {
                "path": str(template_meta.absolute_path),
                "relative_path": str(xml_file.relative_to(templates_dir)),
                "model_identifier": template_meta.model_identifier,
                "model_name": template_meta.model_name,
                "documentation": template_meta.documentation,
                "views": [
                    {
                        "identifier": view.identifier,
                        "name": view.name,
                        "documentation": view.documentation,
                        "viewpoint": view.viewpoint,
                        "index": view.index,
                    }
                    for view in template_meta.views
                ],
            }
        )

    payload = {
        "directory": str(templates_dir),
        "count": len(metadata),
        "templates": metadata,
    }

    if session_state is not None:
        store_artifact(session_state, SESSION_ARTIFACT_TEMPLATE_LISTING, payload)
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_TEMPLATE_LISTING,
            "count": len(metadata),
        }

    return payload


def _normalize_filter_tokens(filter_value: Iterable[str] | str | None) -> set[str]:
    if filter_value is None:
        return set()
    if isinstance(filter_value, str):
        tokens = [token.strip().casefold() for token in filter_value.split(",")]
    else:
        tokens = [str(token).strip().casefold() for token in filter_value]
    return {token for token in tokens if token}


def _filter_views(views: Iterable[ViewMetadata], filter_tokens: set[str]) -> list[ViewMetadata]:
    if not filter_tokens:
        return list(views)

    filtered: list[ViewMetadata] = []
    for view in views:
        candidates = {
            view.identifier.casefold(),
            view.name.casefold(),
        }
        if any(token in candidates for token in filter_tokens):
            filtered.append(view)
    if not filtered:
        raise ValueError("Nenhuma visão corresponde ao filtro informado.")
    return filtered


def describe_template(
    template_path: str | None = None,
    view_filter: Iterable[str] | str | None = None,
    *,
    session_state: MutableMapping[str, object] | None = None,
) -> dict[str, object]:
    target_path = Path(template_path) if template_path else DEFAULT_TEMPLATE
    if not target_path.is_absolute():
        target_path = (Path.cwd() / target_path).resolve()

    if not target_path.exists():
        raise FileNotFoundError(f"Template não encontrado: {target_path}")

    cached = get_cached_blueprint(session_state, target_path)
    if cached is None:
        metadata = load_template_metadata(target_path)
        blueprint = {
            "template_path": str(metadata.absolute_path),
            "model": {
                "identifier": metadata.model_identifier,
                "name": metadata.model_name,
                "documentation": metadata.documentation,
            },
            "views": [view.__dict__ for view in metadata.views],
        }
        store_blueprint(session_state, target_path, blueprint)
    else:
        metadata = TemplateMetadata(
            path=target_path,
            model_identifier=cached.get("model", {}).get("identifier"),
            model_name=cached.get("model", {}).get("name"),
            documentation=cached.get("model", {}).get("documentation"),
            views=tuple(
                ViewMetadata(
                    identifier=view.get("identifier", ""),
                    name=view.get("name", view.get("identifier", "")),
                    documentation=view.get("documentation"),
                    viewpoint=view.get("viewpoint"),
                    index=int(view.get("index", idx)),
                )
                for idx, view in enumerate(cached.get("views", []))
                if isinstance(view, dict)
            ),
        )

    filter_tokens = _normalize_filter_tokens(view_filter)
    filtered_views = _filter_views(metadata.views, filter_tokens)

    guidance = {
        "model": {
            "identifier": metadata.model_identifier,
            "name": metadata.model_name,
            "documentation": metadata.documentation,
            "path": str(metadata.absolute_path),
        },
        "views": [
            {
                "identifier": view.identifier,
                "name": view.name,
                "documentation": view.documentation,
                "viewpoint": view.viewpoint,
                "index": view.index,
            }
            for view in filtered_views
        ],
    }

    if session_state is not None:
        store_artifact(session_state, SESSION_ARTIFACT_TEMPLATE_GUIDANCE, guidance)
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
            "view_count": len(guidance["views"]),
        }

    return guidance
