"""Geração de pré-visualizações de layout para as visões ArchiMate."""

from __future__ import annotations

import base64
import copy
import json
import logging
import re
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import (
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
)
from .constants import OUTPUT_DIR
from .rendering import render_view_layout
from .session import (
    get_cached_artifact,
    store_artifact,
)
from .templates import (
    TemplateMetadata,
    ViewMetadata,
    load_template_blueprint,
    load_template_metadata,
    resolve_template_path,
)

__all__ = ["generate_layout_preview"]


logger = logging.getLogger(__name__)

_CODE_FENCE_RE = re.compile(
    r"^\s*(?:```|~~~)(?:json)?\s*(?P<body>.*?)(?:```|~~~)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_PLACEHOLDER_RE = re.compile(r"\s*[-–]?\s*\{[^}]+\}")
_WHITESPACE_RE = re.compile(r"\s+")


def _resolve_template_path(template_path: str | None) -> Path:
    return resolve_template_path(template_path)


def _expand_token_variants(value: Any) -> set[str]:
    variants: set[str] = set()
    if value is None:
        return variants
    base = str(value).strip()
    if not base:
        return variants
    normalized = _WHITESPACE_RE.sub(" ", base.casefold()).strip()
    if normalized:
        variants.add(normalized)
        sanitized = _WHITESPACE_RE.sub(" ", _PLACEHOLDER_RE.sub("", normalized)).strip()
        if sanitized:
            variants.add(sanitized)
    return variants


def _normalize_tokens(view_filter: Iterable[str] | str | None) -> set[str]:
    tokens: set[str] = set()
    if view_filter is None:
        return tokens
    values: Iterable[Any]
    if isinstance(view_filter, str):
        values = view_filter.split(",")
    else:
        values = view_filter
    for raw in values:
        tokens.update(_expand_token_variants(raw))
    # Se nenhuma variação foi encontrada, tenta usar o valor literal original.
    if not tokens and isinstance(view_filter, str) and view_filter.strip():
        tokens.add(_WHITESPACE_RE.sub(" ", view_filter.strip().casefold()))
    return {token for token in tokens if token}


def _select_views(
    metadata: TemplateMetadata, view_filter: Iterable[str] | str | None
) -> list[ViewMetadata]:
    tokens = _normalize_tokens(view_filter)
    if not tokens:
        return list(metadata.views)

    matched: list[ViewMetadata] = []
    for view in metadata.views:
        candidates = set()
        candidates.update(_expand_token_variants(view.identifier))
        candidates.update(_expand_token_variants(view.name))
        if view.viewpoint:
            candidates.update(_expand_token_variants(view.viewpoint))
        if candidates & tokens:
            matched.append(view)
    if not matched:
        raise ValueError("Nenhuma visão do template corresponde ao filtro informado.")
    return matched


def _strip_code_fences(text: str) -> str:
    match = _CODE_FENCE_RE.match(text)
    if match:
        return match.group("body").strip()
    return text


def _load_datamodel(
    datamodel: str | Mapping[str, Any] | None,
    session_state: MutableMapping[str, object] | None,
) -> dict[str, Any] | None:
    if isinstance(datamodel, Mapping):
        return copy.deepcopy(dict(datamodel))
    if isinstance(datamodel, str):
        stripped = _strip_code_fences(datamodel)
        if not stripped.strip():
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:  # pragma: no cover - feedback explícito
            raise ValueError("O conteúdo enviado não é um JSON válido.") from exc

    if session_state is not None:
        artifact = get_cached_artifact(session_state, SESSION_ARTIFACT_FINAL_DATAMODEL)
        if isinstance(artifact, Mapping):
            cached = artifact.get("datamodel")
            if isinstance(cached, Mapping):
                return copy.deepcopy(dict(cached))
            cached_json = artifact.get("json")
            if isinstance(cached_json, str):
                try:
                    return json.loads(cached_json)
                except json.JSONDecodeError:
                    logger.debug(
                        "Datamodel armazenado na sessão está inválido.",
                        exc_info=True,
                    )
    return None


def _build_element_lookup(
    blueprint: Mapping[str, Any], datamodel: Mapping[str, Any] | None
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}

    def register(element: Mapping[str, Any], *, prefer_existing: bool = False) -> None:
        identifier = element.get("id") or element.get("identifier")
        if not identifier:
            return
        key = str(identifier)
        target = lookup.setdefault(key, {})
        if prefer_existing and target:
            return
        name = element.get("name") or element.get("label")
        elem_type = element.get("type") or element.get("kind")
        if name:
            target["name"] = name
        if elem_type:
            target["type"] = elem_type

    def walk(elements: Sequence[Any] | None, *, prefer_existing: bool = False) -> None:
        if not isinstance(elements, Sequence):
            return
        for element in elements:
            if not isinstance(element, Mapping):
                continue
            register(element, prefer_existing=prefer_existing)
            walk(element.get("children"), prefer_existing=prefer_existing)

    walk(blueprint.get("elements"))

    if isinstance(datamodel, Mapping):
        walk(datamodel.get("elements"), prefer_existing=False)

    return lookup


def _build_relationship_lookup(
    blueprint: Mapping[str, Any], datamodel: Mapping[str, Any] | None
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}

    def register(relation: Mapping[str, Any], *, prefer_existing: bool = False) -> None:
        identifier = relation.get("id") or relation.get("identifier")
        if not identifier:
            return
        key = str(identifier)
        target = lookup.setdefault(key, {})
        if prefer_existing and target:
            return
        for attr in ("source", "target", "type"):
            value = relation.get(attr)
            if value:
                target[attr] = value
        label = relation.get("label") or relation.get("name")
        if label:
            target["name"] = label

    relations = blueprint.get("relations")
    if isinstance(relations, Sequence):
        for relation in relations:
            if isinstance(relation, Mapping):
                register(relation, prefer_existing=True)

    if isinstance(datamodel, Mapping):
        datamodel_relations = datamodel.get("relations")
        if isinstance(datamodel_relations, Sequence):
            for relation in datamodel_relations:
                if isinstance(relation, Mapping):
                    register(relation, prefer_existing=False)

    return lookup


def _collect_nodes(nodes: Sequence[Any] | None, store: list[dict[str, Any]]) -> None:
    if not isinstance(nodes, Sequence):
        return
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        store.append(copy.deepcopy(dict(node)))
        _collect_nodes(node.get("nodes"), store)


def _collect_connections(
    container: Mapping[str, Any] | None, store: list[dict[str, Any]]
) -> None:
    if not isinstance(container, Mapping):
        return
    connections = container.get("connections")
    if isinstance(connections, Sequence):
        for connection in connections:
            if isinstance(connection, Mapping):
                store.append(copy.deepcopy(dict(connection)))
    nodes = container.get("nodes")
    if isinstance(nodes, Sequence):
        for node in nodes:
            _collect_connections(node, store)


def _deep_merge(target: dict[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in source.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), Mapping):
            _deep_merge(target[key], value)
        elif isinstance(value, list):
            target[key] = copy.deepcopy(value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def _build_layout_nodes(
    view_payload: Mapping[str, Any],
    element_lookup: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    _collect_nodes(view_payload.get("nodes"), flattened)

    layout_nodes: list[dict[str, Any]] = []
    for node in flattened:
        bounds = node.get("bounds")
        if not isinstance(bounds, Mapping):
            continue
        try:
            x = float(bounds["x"])
            y = float(bounds["y"])
            w = float(bounds["w"])
            h = float(bounds["h"])
        except (KeyError, TypeError, ValueError):
            continue

        identifier = (
            str(node.get("id") or node.get("identifier") or node.get("elementRef") or "node")
        )
        element_ref = node.get("elementRef")
        lookup = element_lookup.get(str(element_ref)) if element_ref else None

        title = (
            node.get("title")
            or node.get("label")
            or (lookup.get("name") if lookup else None)
            or node.get("name")
            or element_ref
        )

        layout_nodes.append(
            {
                "id": identifier,
                "identifier": identifier,
                "alias": node.get("alias") or identifier,
                "bounds": {"x": x, "y": y, "w": w, "h": h},
                "style": node.get("style"),
                "element_ref": element_ref,
                "relationship_ref": node.get("relationshipRef"),
                "element_name": lookup.get("name") if lookup else None,
                "element_type": lookup.get("type") if lookup else node.get("type"),
                "type": node.get("type"),
                "title": title,
                "label": node.get("label"),
            }
        )

    return layout_nodes


def _build_layout_connections(
    view_payload: Mapping[str, Any],
    relationship_lookup: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    _collect_connections(view_payload, flattened)

    layout_connections: list[dict[str, Any]] = []
    for connection in flattened:
        source = connection.get("source") or connection.get("sourceRef")
        target = connection.get("target") or connection.get("targetRef")
        if not source or not target:
            continue

        identifier = str(connection.get("id") or connection.get("identifier") or f"conn-{len(layout_connections)+1}")
        relationship_ref = connection.get("relationshipRef")
        relation_info = (
            relationship_lookup.get(str(relationship_ref)) if relationship_ref else None
        )
        label = (
            connection.get("label")
            or (relation_info.get("name") if relation_info else None)
        )

        layout_connections.append(
            {
                "id": identifier,
                "identifier": identifier,
                "source": source,
                "target": target,
                "relationship_ref": relationship_ref,
                "label": label,
                "style": connection.get("style"),
            }
        )

    return layout_connections


def _build_view_payload(
    metadata: ViewMetadata,
    blueprint_view: Mapping[str, Any] | None,
    datamodel_view: Mapping[str, Any] | None,
    element_lookup: Mapping[str, Mapping[str, Any]],
    relationship_lookup: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    base_view: dict[str, Any] = copy.deepcopy(blueprint_view) if blueprint_view else {}
    if isinstance(datamodel_view, Mapping):
        base_view = _deep_merge(base_view, datamodel_view)

    def build_layout(source: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "nodes": _build_layout_nodes(source, element_lookup),
            "connections": _build_layout_connections(source, relationship_lookup),
        }

    layout = build_layout(base_view)
    if not layout["nodes"] and blueprint_view:
        fallback_view = copy.deepcopy(blueprint_view)
        fallback_layout = build_layout(fallback_view)
        if fallback_layout["nodes"]:
            layout = fallback_layout
            base_view.setdefault("nodes", fallback_view.get("nodes"))
            base_view.setdefault("connections", fallback_view.get("connections"))

    name = str(base_view.get("name") or metadata.name)
    return {
        "identifier": metadata.identifier,
        "name": name,
        "layout": layout,
        "raw": base_view,
    }


def _build_replacements(render_payload: Mapping[str, Any], view_name: str) -> dict[str, Any]:
    label = "Abrir diagrama em SVG"
    data_uri = render_payload.get("svg_data_uri") or ""
    if not data_uri:
        local_path = render_payload.get("local_path")
        if isinstance(local_path, str):
            try:
                encoded = base64.b64encode(Path(local_path).read_bytes()).decode("ascii")
            except OSError:
                encoded = ""
            if encoded:
                data_uri = f"data:image/svg+xml;base64,{encoded}"

    inline_markdown = render_payload.get("inline_markdown")
    if data_uri:
        inline_value = f"![Pré-visualização]({data_uri})"
    else:
        inline_value = str(inline_markdown or "")

    replacements = {
        "layout_preview.inline": inline_value,
        "layout_preview.svg": data_uri,
        "layout_preview.view_name": view_name,
        "layout_preview.download.url": data_uri,
        "layout_preview.download.label": label,
        "layout_preview.download.markdown": f"[{label}]({data_uri})" if data_uri else str(render_payload.get("download_markdown") or ""),
    }
    replacements["layout_preview.download"] = replacements["layout_preview.download.markdown"]

    return replacements


def _index_datamodel_views(datamodel: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(datamodel, Mapping):
        return {}

    views = datamodel.get("views")
    diagrams: Sequence[Any] | None
    if isinstance(views, Mapping):
        diagrams = views.get("diagrams")  # type: ignore[assignment]
    else:
        diagrams = views

    lookup: dict[str, Mapping[str, Any]] = {}
    if isinstance(diagrams, Sequence):
        for view in diagrams:
            if not isinstance(view, Mapping):
                continue
            identifier = view.get("id") or view.get("identifier")
            if identifier:
                lookup[str(identifier)] = view
    return lookup


def _match_blueprint_view(
    blueprint: Mapping[str, Any], identifier: str
) -> Mapping[str, Any] | None:
    views = blueprint.get("views")
    diagrams: Sequence[Any] | None
    if isinstance(views, Mapping):
        diagrams = views.get("diagrams")  # type: ignore[assignment]
    else:
        diagrams = views
    if not isinstance(diagrams, Sequence):
        return None
    for view in diagrams:
        if not isinstance(view, Mapping):
            continue
        view_id = view.get("id") or view.get("identifier")
        if view_id and str(view_id) == identifier:
            return view
    return None


def generate_layout_preview(
    datamodel: str | dict | None,
    template_path: str | None,
    *,
    view_filter: Iterable[str] | str | None = None,
    session_state: MutableMapping[str, object] | None = None,
) -> dict[str, Any]:
    target_template = _resolve_template_path(template_path)
    metadata = load_template_metadata(target_template)
    available_views = _select_views(metadata, view_filter)
    if not available_views:
        raise ValueError("O template selecionado não possui visões para pré-visualização.")

    blueprint = load_template_blueprint(target_template, session_state)
    datamodel_payload = _load_datamodel(datamodel, session_state)
    logger.info(
        "generate_layout_preview: template='%s', filtro='%s', datamodel=%s",
        target_template,
        view_filter or "<todas>",
        "fornecido" if datamodel_payload else "template-base",
    )

    datamodel_views = _index_datamodel_views(datamodel_payload)
    element_lookup = _build_element_lookup(blueprint, datamodel_payload)
    relationship_lookup = _build_relationship_lookup(blueprint, datamodel_payload)

    view_payloads: list[dict[str, Any]] = []
    for meta in available_views:
        blueprint_view = _match_blueprint_view(blueprint, meta.identifier)
        datamodel_view = datamodel_views.get(meta.identifier)
        view_payloads.append(
            _build_view_payload(
                meta,
                blueprint_view,
                datamodel_view,
                element_lookup,
                relationship_lookup,
            )
        )

    primary_view = view_payloads[0]

    if not primary_view["layout"]["nodes"]:
        raise ValueError("A visão selecionada não possui elementos para renderização.")

    node_count = len(primary_view["layout"]["nodes"])
    conn_count = len(primary_view["layout"].get("connections", []))
    logger.info(
        "generate_layout_preview: visão '%s' renderizada (%d nós / %d conexões).",
        primary_view["name"],
        node_count,
        conn_count,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    render_payload = render_view_layout(
        primary_view["name"],
        primary_view["identifier"],
        layout=primary_view["layout"],
        output_dir=OUTPUT_DIR,
    )
    if not isinstance(render_payload, Mapping):
        raise ValueError("Não foi possível renderizar a pré-visualização solicitada.")

    replacements = _build_replacements(render_payload, primary_view["name"])

    artifact = {
        "template": str(target_template),
        "view": {
            "identifier": primary_view["identifier"],
            "name": primary_view["name"],
            "layout": primary_view["layout"],
        },
        "views": [
            {
                "identifier": payload["identifier"],
                "name": payload["name"],
                "index": meta.index,
            }
            for payload, meta in zip(view_payloads, available_views)
        ],
        "render": dict(render_payload),
        "replacements": replacements,
        "links": {
            "layout_svg": {
                "label": replacements.get("layout_preview.download.label"),
                "url": replacements.get("layout_preview.download.url"),
                "format": "svg",
            }
        },
    }

    if datamodel_payload is not None:
        artifact["datamodel_snapshot"] = datamodel_payload

    if session_state is not None:
        store_artifact(session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW, artifact)
        logger.debug(
            "generate_layout_preview: artefato '%s' armazenado no estado de sessão.",
            SESSION_ARTIFACT_LAYOUT_PREVIEW,
        )
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_LAYOUT_PREVIEW,
            "view_name": primary_view["name"],
        }

    logger.debug(
        "generate_layout_preview: retornando artefato sem sessão explícita (modo fallback)."
    )
    return artifact
