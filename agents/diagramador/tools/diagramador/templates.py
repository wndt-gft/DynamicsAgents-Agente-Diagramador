"""Funções utilitárias para descoberta e descrição de templates ArchiMate."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence
from xml.etree import ElementTree as ET

from .artifacts import (
    SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
    SESSION_ARTIFACT_TEMPLATE_LISTING,
)
from .constants import ARCHIMATE_NS, DEFAULT_TEMPLATE, DEFAULT_TEMPLATES_DIR, XSI_ATTR
from .session import get_cached_blueprint, store_artifact, store_blueprint
from ...utils.logging_config import get_logger

__all__ = [
    "TemplateMetadata",
    "ViewMetadata",
    "DEFAULT_TEMPLATE",
    "load_template_metadata",
    "list_templates",
    "describe_template",
    "resolve_template_path",
    "load_template_blueprint",
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


logger = get_logger(__name__)


_NS = {"a": ARCHIMATE_NS}
_PLACEHOLDER_RE = re.compile(r"\s*[-–]?\s*\{[^}]+\}")
_WHITESPACE_RE = re.compile(r"\s+")


def _resolve_templates_dir(directory: str | None) -> Path:
    base = Path(directory) if directory else DEFAULT_TEMPLATES_DIR
    if not base.is_absolute():
        base = (Path.cwd() / base).resolve()
    return base


def _read_text(element) -> str | None:
    if element is None or element.text is None:
        return None
    text = element.text.strip()
    return text or None


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

    connections = [
        _parse_view_connection(conn)
        for conn in node.findall("a:connection", _NS)
    ]
    if connections:
        data["connections"] = connections

    return data


def _parse_view_diagram(view: ET.Element) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    identifier = view.get("identifier")
    if identifier:
        payload["id"] = identifier

    view_type = view.get(XSI_ATTR)
    if view_type:
        payload["type"] = view_type.split("}")[-1] if "}" in view_type else view_type

    name = _text_payload(view.find("a:name", _NS))
    if name:
        payload["name"] = name

    documentation = _text_payload(view.find("a:documentation", _NS))
    if documentation:
        payload["documentation"] = documentation

    nodes = [_parse_view_node(node) for node in view.findall("a:node", _NS)]
    if nodes:
        payload["nodes"] = nodes

    connections = [
        _parse_view_connection(conn)
        for conn in view.findall("a:connection", _NS)
    ]
    if connections:
        payload["connections"] = connections

    return payload


def _parse_template_blueprint(template_path: Path) -> dict[str, Any]:
    root = ET.parse(str(template_path)).getroot()
    blueprint: dict[str, Any] = {
        "model_identifier": root.get("identifier"),
        "model_name": _text_payload(root.find("a:name", _NS)),
        "model_documentation": _text_payload(root.find("a:documentation", _NS)),
    }

    elements: list[dict[str, Any]] = []
    for element in root.findall("a:elements/a:element", _NS):
        payload = {}
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

        properties = []
        for prop in element.findall("a:properties/a:property", _NS):
            prop_payload: dict[str, Any] = {}
            ident = prop.get("identifier")
            if ident:
                prop_payload["id"] = ident
            name = prop.get("name")
            if name:
                prop_payload["name"] = name
            value = prop.get("value")
            if value:
                prop_payload["value"] = value
            if prop_payload:
                properties.append(prop_payload)
        if properties:
            payload["properties"] = properties

        children = [
            _parse_view_node(child)
            for child in element.findall("a:node", _NS)
        ]
        if children:
            payload["children"] = children

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


def load_template_blueprint(
    template_path: Path | str,
    session_state: MutableMapping[str, object] | None = None,
) -> dict[str, Any]:
    """Carrega o blueprint completo do template, com caching opcional."""

    target = Path(template_path)
    if not target.is_absolute():
        target = resolve_template_path(target)

    cached = get_cached_blueprint(session_state, target)
    if isinstance(cached, dict):
        views = cached.get("views")
        diagrams = None
        if isinstance(views, dict):
            diagrams = views.get("diagrams")
        if isinstance(diagrams, Sequence) and diagrams:
            logger.debug("load_template_blueprint: reutilizando cache para %s.", target)
            return copy.deepcopy(cached)

    blueprint = _parse_template_blueprint(target)
    store_blueprint(session_state, target, blueprint)
    logger.debug("load_template_blueprint: blueprint carregado e armazenado para %s.", target)
    return copy.deepcopy(blueprint)


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


def resolve_template_path(template_path: str | Path | None) -> Path:
    """Resolve a referência de template reutilizando localização padrão quando necessário."""

    if template_path is None or (isinstance(template_path, str) and not template_path.strip()):
        return DEFAULT_TEMPLATE

    path = Path(template_path)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path.resolve())
    else:
        candidates.extend(
            [
                (Path.cwd() / path).resolve(),
                (DEFAULT_TEMPLATES_DIR / path).resolve(),
                (DEFAULT_TEMPLATE.parent / path).resolve(),
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate

    lookup_key = str(template_path).strip().casefold()
    if lookup_key:
        for xml_file in DEFAULT_TEMPLATES_DIR.rglob("*.xml"):
            try:
                metadata = load_template_metadata(xml_file)
            except ET.ParseError:
                continue
            names = {
                xml_file.name.casefold(),
                xml_file.stem.casefold(),
            }
            if metadata.model_name:
                names.add(metadata.model_name.casefold())
            if metadata.model_identifier:
                names.add(metadata.model_identifier.casefold())
            if lookup_key in names:
                return xml_file.resolve()
        logger.warning(
            "resolve_template_path: template '%s' não encontrado; utilizando template padrão '%s'.",
            template_path,
            DEFAULT_TEMPLATE,
        )

    logger.warning(
        "Template informado '%s' não encontrado; retornando template padrão '%s'.",
        template_path,
        DEFAULT_TEMPLATE,
    )
    return DEFAULT_TEMPLATE


def list_templates(
    directory: str | None = None,
    *,
    session_state: MutableMapping[str, object] | None = None,
) -> dict[str, object]:
    templates_dir = _resolve_templates_dir(directory)
    if not templates_dir.exists():
        raise FileNotFoundError(f"Diretório de templates não encontrado: {templates_dir}")

    logger.info("list_templates: procurando layouts em '%s'.", templates_dir)

    templates: list[dict[str, Any]] = []
    for xml_file in sorted(templates_dir.rglob("*.xml")):
        try:
            template_meta = load_template_metadata(xml_file)
        except ET.ParseError:
            logger.warning("list_templates: arquivo inválido ignorado: %s", xml_file)
            continue

        layout_name = xml_file.stem
        template_name = template_meta.model_name or layout_name
        relative_path = str(xml_file.relative_to(templates_dir))

        view_entries = [
            {
                "view_identifier": view.identifier,
                "view_name": view.name,
                "view_description": view.documentation,
                "view_documentation": view.documentation,
                "view_index": view.index,
                "selector": view.name,
            }
            for view in template_meta.views
        ]

        templates.append(
            {
                "template_key": relative_path,
                "template_name": template_name,
                "template_identifier": template_meta.model_identifier,
                "template_description": template_meta.documentation,
                "template_selector": template_name,
                "layout_name": layout_name,
                "layout_description": template_meta.documentation,
                "layout_file": f"{relative_path}",
                "absolute_path": str(xml_file.resolve()),
                "layout_selector": relative_path,
                "views": view_entries,
            }
        )

    payload = {
        "directory": str(templates_dir),
        "count": len(templates),
        "templates": templates,
    }

    if session_state is not None:
        store_artifact(session_state, SESSION_ARTIFACT_TEMPLATE_LISTING, payload)
        logger.debug(
            "list_templates: artefato '%s' com %d template(s) armazenado na sessão.",
            SESSION_ARTIFACT_TEMPLATE_LISTING,
            len(templates),
        )
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_TEMPLATE_LISTING,
            "count": len(templates),
            "templates": templates,
        }

    return payload


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


def _normalize_filter_tokens(filter_value: Iterable[str] | str | None) -> set[str]:
    tokens: set[str] = set()
    if filter_value is None:
        return tokens
    values: Iterable[Any]
    if isinstance(filter_value, str):
        values = filter_value.split(",")
    else:
        values = filter_value
    for raw in values:
        tokens.update(_expand_token_variants(raw))
    if not tokens and isinstance(filter_value, str) and filter_value.strip():
        literal = _WHITESPACE_RE.sub(" ", filter_value.strip().casefold())
        if literal:
            tokens.add(literal)
    return {token for token in tokens if token}


def _filter_views(views: Iterable[ViewMetadata], filter_tokens: set[str]) -> list[ViewMetadata]:
    if not filter_tokens:
        return list(views)

    filtered: list[ViewMetadata] = []
    for view in views:
        candidates = set()
        candidates.update(_expand_token_variants(view.identifier))
        candidates.update(_expand_token_variants(view.name))
        if view.viewpoint:
            candidates.update(_expand_token_variants(view.viewpoint))
        if candidates & filter_tokens:
            filtered.append(view)
    if filtered:
        return filtered

    logger.warning(
        "describe_template: nenhum match para filtro '%s'; retornando todas as visões.",
        ", ".join(sorted(filter_tokens)),
    )
    return list(views)


def describe_template(
    template_path: str | None = None,
    view_filter: Iterable[str] | str | None = None,
    *,
    session_state: MutableMapping[str, object] | None = None,
) -> dict[str, object]:
    target_path = resolve_template_path(template_path)
    metadata = load_template_metadata(target_path)
    blueprint = load_template_blueprint(target_path, session_state)

    filter_tokens = _normalize_filter_tokens(view_filter)
    filtered_views = _filter_views(metadata.views, filter_tokens)

    diagrams: Sequence[Any] | None = None
    views_container = blueprint.get("views")
    if isinstance(views_container, Mapping):
        diagrams = views_container.get("diagrams")  # type: ignore[assignment]
    elif isinstance(views_container, Sequence):
        diagrams = views_container

    diagrams_map: dict[str, Mapping[str, Any]] = {}
    if isinstance(diagrams, Sequence):
        for entry in diagrams:
            if not isinstance(entry, Mapping):
                continue
            identifier = entry.get("id") or entry.get("identifier")
            if identifier:
                diagrams_map[str(identifier)] = entry

    guidance = {
        "model": {
            "identifier": metadata.model_identifier or blueprint.get("model_identifier"),
            "name": metadata.model_name or blueprint.get("model_name"),
            "documentation": metadata.documentation or blueprint.get("model_documentation"),
            "path": str(metadata.absolute_path),
        },
        "elements": copy.deepcopy(blueprint.get("elements", [])),
        "relations": copy.deepcopy(blueprint.get("relations", [])),
        "views": [],
    }

    for view in filtered_views:
        diagram_payload = diagrams_map.get(view.identifier)
        view_entry: dict[str, Any] = {
            "identifier": view.identifier,
            "name": view.name,
            "documentation": view.documentation or (diagram_payload or {}).get("documentation"),
            "viewpoint": view.viewpoint,
            "index": view.index,
        }
        if diagram_payload is not None:
            view_entry["diagram"] = copy.deepcopy(diagram_payload)
        guidance["views"].append(view_entry)

    logger.info(
        "describe_template: %d visão(ões) preparada(s) para '%s' (%s).",
        len(guidance["views"]),
        metadata.model_name or metadata.model_identifier or "modelo",
        metadata.path,
    )

    if session_state is not None:
        store_artifact(session_state, SESSION_ARTIFACT_TEMPLATE_GUIDANCE, guidance)
        logger.debug(
            "describe_template: artefato '%s' persistido no estado de sessão.",
            SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
        )
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
            "view_count": len(guidance["views"]),
        }

    return guidance
