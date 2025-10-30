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
from xml.etree import ElementTree as ET

from .artifacts import (
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
)
from .constants import ARCHIMATE_NS, DEFAULT_TEMPLATE, OUTPUT_DIR, XSI_ATTR
from .rendering import render_view_layout
from .session import (
    get_cached_artifact,
    get_cached_blueprint,
    store_artifact,
    store_blueprint,
)
from .templates import TemplateMetadata, ViewMetadata, load_template_metadata

__all__ = ["generate_layout_preview"]


logger = logging.getLogger(__name__)

_NS = {"a": ARCHIMATE_NS}
_CODE_FENCE_RE = re.compile(
    r"^\s*(?:```|~~~)(?:json)?\s*(?P<body>.*?)(?:```|~~~)\s*$",
    re.IGNORECASE | re.DOTALL,
)


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


def _select_views(
    metadata: TemplateMetadata, view_filter: Iterable[str] | str | None
) -> list[ViewMetadata]:
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


def _text_payload(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    text = element.text.strip()
    return text or None


def _parse_color_element(element: ET.Element | None) -> dict[str, int] | None:
    if element is None:
        return None
    payload: dict[str, int] = {}
    for channel in ("r", "g", "b", "a"):
        value = element.get(channel)
        if value is None:
            continue
        try:
            payload[channel] = int(value)
        except (TypeError, ValueError):
            continue
    return payload or None


def _parse_style_element(element: ET.Element | None) -> dict[str, Any] | None:
    if element is None:
        return None
    style: dict[str, Any] = {}

    fill_color = _parse_color_element(element.find("a:fillColor", _NS))
    if fill_color:
        style["fillColor"] = fill_color

    line_color = _parse_color_element(element.find("a:lineColor", _NS))
    if line_color:
        style["lineColor"] = line_color

    font_element = element.find("a:font", _NS)
    if font_element is not None:
        font: dict[str, Any] = {}
        for attr in ("name", "size", "style"):
            value = font_element.get(attr)
            if value:
                font[attr] = value if attr != "size" else float(value)
        color = _parse_color_element(font_element.find("a:color", _NS))
        if color:
            font["color"] = color
        if font:
            style["font"] = font

    return style or None


def _coerce_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_view_connection(node: ET.Element) -> dict[str, Any]:
    data: dict[str, Any] = {}

    identifier = node.get("identifier")
    if identifier:
        data["id"] = identifier

    conn_type = node.get(XSI_ATTR)
    if conn_type:
        data["type"] = conn_type.split("}")[-1] if "}" in conn_type else conn_type

    for attr in ("relationshipRef", "source", "target"):
        value = node.get(attr)
        if value:
            data[attr] = value

    label = _text_payload(node.find("a:label", _NS))
    if label:
        data["label"] = label

    documentation = _text_payload(node.find("a:documentation", _NS))
    if documentation:
        data["documentation"] = documentation

    style = _parse_style_element(node.find("a:style", _NS))
    if style:
        data["style"] = style

    points: list[dict[str, float]] = []
    for point in node.findall("a:points/a:point", _NS):
        point_payload: dict[str, float] = {}
        for coord in ("x", "y"):
            coord_value = _coerce_float(point.get(coord))
            if coord_value is not None:
                point_payload[coord] = coord_value
        if point_payload:
            points.append(point_payload)
    if points:
        data["points"] = points

    return data


def _parse_view_node(node: ET.Element) -> dict[str, Any]:
    data: dict[str, Any] = {}

    identifier = node.get("identifier")
    if identifier:
        data["id"] = identifier

    node_type = node.get(XSI_ATTR)
    if node_type:
        data["type"] = node_type.split("}")[-1] if "}" in node_type else node_type

    bounds: dict[str, float] = {}
    for attr in ("x", "y", "w", "h"):
        number = _coerce_float(node.get(attr))
        if number is not None:
            bounds[attr] = number
    if bounds:
        data["bounds"] = bounds

    for attr in ("elementRef", "relationshipRef", "viewRef"):
        value = node.get(attr)
        if value:
            data[attr] = value

    label = _text_payload(node.find("a:label", _NS))
    if label:
        data["label"] = label

    documentation = _text_payload(node.find("a:documentation", _NS))
    if documentation:
        data["documentation"] = documentation

    style = _parse_style_element(node.find("a:style", _NS))
    if style:
        data["style"] = style

    child_nodes = [
        _parse_view_node(child) for child in node.findall("a:node", _NS)
    ]
    if child_nodes:
        data["nodes"] = child_nodes

    child_connections = [
        _parse_view_connection(child)
        for child in node.findall("a:connection", _NS)
    ]
    if child_connections:
        data["connections"] = child_connections

    return data


def _parse_view_diagram(view: ET.Element) -> dict[str, Any]:
    data: dict[str, Any] = {}

    identifier = view.get("identifier")
    if identifier:
        data["id"] = identifier

    view_type = view.get(XSI_ATTR)
    if view_type:
        data["type"] = view_type.split("}")[-1] if "}" in view_type else view_type

    name = _text_payload(view.find("a:name", _NS))
    if name:
        data["name"] = name

    documentation = _text_payload(view.find("a:documentation", _NS))
    if documentation:
        data["documentation"] = documentation

    nodes = [_parse_view_node(node) for node in view.findall("a:node", _NS)]
    if nodes:
        data["nodes"] = nodes

    connections = [
        _parse_view_connection(conn)
        for conn in view.findall("a:connection", _NS)
    ]
    if connections:
        data["connections"] = connections

    return data


def _parse_template_blueprint(template_path: Path) -> dict[str, Any]:
    tree = ET.parse(str(template_path))
    root = tree.getroot()

    blueprint: dict[str, Any] = {
        "model_identifier": root.get("identifier"),
        "model_name": _text_payload(root.find("a:name", _NS)),
        "model_documentation": _text_payload(root.find("a:documentation", _NS)),
    }

    elements: list[dict[str, Any]] = []
    for element in root.findall("a:elements/a:element", _NS):
        payload: dict[str, Any] = {}
        identifier = element.get("identifier")
        if identifier:
            payload["id"] = identifier
        element_type = element.get(XSI_ATTR)
        if element_type:
            payload["type"] = (
                element_type.split("}")[-1] if "}" in element_type else element_type
            )
        name = _text_payload(element.find("a:name", _NS))
        if name:
            payload["name"] = name
        documentation = _text_payload(element.find("a:documentation", _NS))
        if documentation:
            payload["documentation"] = documentation
        if payload:
            elements.append(payload)
    if elements:
        blueprint["elements"] = elements

    relationships: list[dict[str, Any]] = []
    for relationship in root.findall("a:relationships/a:relationship", _NS):
        payload = {}
        identifier = relationship.get("identifier")
        if identifier:
            payload["id"] = identifier
        rel_type = relationship.get(XSI_ATTR)
        if rel_type:
            payload["type"] = rel_type.split("}")[-1] if "}" in rel_type else rel_type
        for attr in ("source", "target"):
            value = relationship.get(attr)
            if value:
                payload[attr] = value
        documentation = _text_payload(relationship.find("a:documentation", _NS))
        if documentation:
            payload["documentation"] = documentation
        if payload:
            relationships.append(payload)
    if relationships:
        blueprint["relations"] = relationships

    diagrams = [
        _parse_view_diagram(view)
        for view in root.findall("a:views/a:diagrams/a:view", _NS)
    ]
    if diagrams:
        blueprint["views"] = {"diagrams": diagrams}

    return blueprint


def _load_template_blueprint(
    template_path: Path, session_state: MutableMapping[str, object] | None
) -> dict[str, Any]:
    cached = get_cached_blueprint(session_state, template_path)
    if isinstance(cached, Mapping):
        return cached

    blueprint = _parse_template_blueprint(template_path)
    store_blueprint(session_state, template_path, blueprint)
    return blueprint


def _build_element_lookup(
    blueprint: Mapping[str, Any], datamodel: Mapping[str, Any] | None
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}

    blueprint_elements = blueprint.get("elements")
    if isinstance(blueprint_elements, Sequence):
        for element in blueprint_elements:
            if not isinstance(element, Mapping):
                continue
            identifier = element.get("id")
            if identifier:
                lookup[str(identifier)] = {
                    "name": element.get("name"),
                    "type": element.get("type"),
                }

    if isinstance(datamodel, Mapping):
        datamodel_elements = datamodel.get("elements")
        if isinstance(datamodel_elements, Sequence):
            for element in datamodel_elements:
                if not isinstance(element, Mapping):
                    continue
                identifier = element.get("id")
                if not identifier:
                    continue
                target = lookup.setdefault(str(identifier), {})
                if element.get("name"):
                    target["name"] = element.get("name")
                if element.get("type"):
                    target["type"] = element.get("type")

    return lookup


def _build_relationship_lookup(
    blueprint: Mapping[str, Any], datamodel: Mapping[str, Any] | None
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}

    blueprint_relations = blueprint.get("relations")
    if isinstance(blueprint_relations, Sequence):
        for relation in blueprint_relations:
            if not isinstance(relation, Mapping):
                continue
            identifier = relation.get("id")
            if identifier:
                lookup[str(identifier)] = {
                    "source": relation.get("source"),
                    "target": relation.get("target"),
                    "type": relation.get("type"),
                }

    if isinstance(datamodel, Mapping):
        datamodel_relations = datamodel.get("relations")
        if isinstance(datamodel_relations, Sequence):
            for relation in datamodel_relations:
                if not isinstance(relation, Mapping):
                    continue
                identifier = relation.get("id")
                if not identifier:
                    continue
                target = lookup.setdefault(str(identifier), {})
                for key in ("source", "target", "type"):
                    if relation.get(key):
                        target[key] = relation.get(key)
                if relation.get("name"):
                    target["name"] = relation.get("name")

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

    name = str(base_view.get("name") or metadata.name)
    layout = {
        "nodes": _build_layout_nodes(base_view, element_lookup),
        "connections": _build_layout_connections(base_view, relationship_lookup),
    }

    return {
        "identifier": metadata.identifier,
        "name": name,
        "layout": layout,
        "raw": base_view,
    }


def _build_replacements(render_payload: Mapping[str, Any], view_name: str) -> dict[str, Any]:
    inline = str(render_payload.get("inline_markdown") or "")
    download = str(render_payload.get("download_markdown") or "")
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

    if data_uri:
        inline = f"![Pré-visualização]({data_uri})"
        if not download:
            download = f"[Abrir diagrama em SVG]({data_uri})"

    return {
        "layout_preview.inline": inline,
        "layout_preview.download": download,
        "layout_preview.svg": data_uri,
        "layout_preview.view_name": view_name,
    }


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

    blueprint = _load_template_blueprint(target_template, session_state)
    datamodel_payload = _load_datamodel(datamodel, session_state)

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
    }

    if datamodel_payload is not None:
        artifact["datamodel_snapshot"] = datamodel_payload

    if session_state is not None:
        store_artifact(session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW, artifact)
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_LAYOUT_PREVIEW,
            "view_name": primary_view["name"],
        }

    return artifact
