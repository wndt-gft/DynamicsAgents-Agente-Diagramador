"""Agente Diagramador responsável por gerar datamodels e diagramas ArchiMate."""

from __future__ import annotations

"""Operações principais do agente Diagramador."""

import base64
import copy
import hashlib
import itertools
import json
import logging
import re
import textwrap
import uuid
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List, MutableMapping, Optional, Tuple
from xml.etree import ElementTree as ET

from google.genai import types

import requests

from ..archimate_exchange import xml_exchange

from .constants import (
    ARCHIMATE_NS,
    DEFAULT_DATAMODEL_FILENAME,
    DEFAULT_DIAGRAM_FILENAME,
    DEFAULT_TEMPLATE,
    DEFAULT_TEMPLATES_DIR,
    DEFAULT_XSD_DIR,
    DEFAULT_KROKI_URL,
    DEFAULT_MERMAID_IMAGE_FORMAT,
    DEFAULT_MERMAID_VALIDATION_URL,
    FETCH_MERMAID_IMAGES,
    OUTPUT_DIR,
    XML_LANG_ATTR,
    XSI_ATTR,
)
from .session import (
    get_cached_blueprint,
    get_cached_preview,
    store_blueprint,
    store_preview,
)

warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")

logger = logging.getLogger(__name__)


_GLOBAL_PREVIEW_CACHE: Dict[str, Dict[str, Any]] = {}


def _store_preview_fallback(preview_id: str, payload: Dict[str, Any]) -> None:
    _GLOBAL_PREVIEW_CACHE[preview_id] = copy.deepcopy(payload)


def _get_preview_fallback(preview_id: str) -> Optional[Dict[str, Any]]:
    preview = _GLOBAL_PREVIEW_CACHE.get(preview_id)
    return copy.deepcopy(preview) if isinstance(preview, dict) else None


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def _resolve_package_path(path: Path) -> Path:
    """Resolve a resource path relative to the package when needed."""

    candidate = Path(path)

    if candidate.is_absolute():
        return candidate

    repo_root = PACKAGE_ROOT.parent.parent
    search_order = [
        Path.cwd() / candidate,
        PACKAGE_ROOT / candidate,
        repo_root / candidate,
    ]

    parts = candidate.parts

    if parts:
        if parts[0].lower() == "agents" and len(parts) > 1:
            stripped = Path(*parts[1:])
            search_order.extend(
                [
                    PACKAGE_ROOT / stripped,
                    PACKAGE_ROOT / "templates" / stripped,
                ]
            )
        elif parts[0].lower() != "templates":
            search_order.append(PACKAGE_ROOT / "templates" / candidate)
    else:
        search_order.append(PACKAGE_ROOT / "templates")

    for option in search_order:
        if option.exists():
            return option

    return search_order[0]


def _ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def _kroki_base_url() -> str:
    return DEFAULT_KROKI_URL.rstrip("/")


def _mermaid_validator_base_url() -> str:
    return DEFAULT_MERMAID_VALIDATION_URL.rstrip("/")


def _encode_mermaid_for_validator(mermaid: str) -> str:
    encoded = base64.urlsafe_b64encode(mermaid.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _resolve_mermaid_format(fmt: Optional[str]) -> str:
    candidate = (fmt or DEFAULT_MERMAID_IMAGE_FORMAT or "png").lower()
    if candidate not in {"png", "svg"}:
        logger.warning(
            "Formato Mermaid '%s' não suportado, utilizando 'png' como fallback.",
            candidate,
        )
        return "png"
    return candidate


def _mermaid_mime_type(fmt: str) -> str:
    if fmt == "svg":
        return "image/svg+xml"
    if fmt == "png":
        return "image/png"
    return "application/octet-stream"


def _build_mermaid_image_payload(
    mermaid: str,
    *,
    alias: str,
    title: str,
    fmt: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_format = _resolve_mermaid_format(fmt)
    base_url = _kroki_base_url()
    url = f"{base_url}/render"
    mime_type = _mermaid_mime_type(resolved_format)
    request_payload = {
        "diagram_source": mermaid,
        "diagram_type": "mermaid",
        "output_format": resolved_format,
    }
    headers = {
        "Accept": mime_type,
    }

    payload: Dict[str, Any] = {
        "format": resolved_format,
        "mime_type": mime_type,
        "url": url,
        "source": "kroki",
        "alt_text": title,
        "status": "url",
        "method": "POST",
        "body": request_payload,
        "headers": headers,
    }

    if not FETCH_MERMAID_IMAGES:
        return payload

    try:
        response = requests.post(url, json=request_payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Falha ao baixar imagem Mermaid", exc_info=exc)
        return payload

    content_type = response.headers.get("Content-Type", "") or ""
    content: bytes | None = None

    if "application/json" in content_type.lower():
        try:
            data = response.json()
        except ValueError:
            data = None
        if isinstance(data, dict):
            raw_content = data.get("content") or data.get("data")
            if isinstance(raw_content, str):
                if raw_content.startswith("data:"):
                    payload["data_uri"] = raw_content
                    try:
                        encoded = raw_content.split(",", 1)[1]
                    except IndexError:
                        encoded = ""
                else:
                    encoded = raw_content
                if encoded:
                    try:
                        content = base64.b64decode(encoded)
                    except (ValueError, TypeError):
                        content = None
    else:
        content = response.content

    if not content:
        logger.warning("Resposta vazia ao solicitar imagem Mermaid via Kroki")
        return payload

    payload["status"] = "cached"
    payload["data_uri"] = (
        f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"
    )

    try:
        output_dir = _ensure_output_dir()
        digest = hashlib.sha256(mermaid.encode("utf-8")).hexdigest()[:12]
        filename = f"{alias}_{digest}.{resolved_format}"
        image_path = output_dir / filename
        image_path.write_bytes(content)
        payload["path"] = str(image_path.resolve())
    except OSError as exc:
        logger.warning("Falha ao salvar imagem Mermaid", exc_info=exc)

    return payload


def _mermaid_validation_request(url: str) -> requests.Response:
    return requests.get(url, timeout=10)


def _extract_mermaid_error_message(svg_payload: str) -> Optional[str]:
    if not svg_payload:
        return None

    if "Syntax error" in svg_payload:
        match = re.search(r"Syntax error[^<]*", svg_payload, re.IGNORECASE)
        if match:
            return match.group(0).strip()
        return "Syntax error"

    if "Parse error" in svg_payload:
        match = re.search(r"Parse error[^<]*", svg_payload, re.IGNORECASE)
        if match:
            return match.group(0).strip()
        return "Parse error"

    return None


def _validate_mermaid_syntax(mermaid: str) -> None:
    if not mermaid.strip():
        return

    encoded = _encode_mermaid_for_validator(mermaid)
    base_url = _mermaid_validator_base_url()
    url = f"{base_url}/svg/{encoded}"

    try:
        response = _mermaid_validation_request(url)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Não foi possível validar o Mermaid gerado", exc_info=exc)
        return

    payload = response.text or ""
    if 'aria-roledescription="error"' in payload or "Syntax error" in payload or "Parse error" in payload:
        message = _extract_mermaid_error_message(payload) or "Erro de sintaxe Mermaid detectado"
        raise ValueError(message)


def _resolve_templates_dir(directory: str | None = None) -> Path:
    """Resolves the directory that stores template XML files.

    If a custom directory is provided but cannot be located, the default
    templates directory is returned as a graceful fallback so the agent keeps
    operating with the bundled assets.
    """

    base = Path(directory) if directory else DEFAULT_TEMPLATES_DIR
    resolved = _resolve_package_path(base)

    if resolved.exists():
        return resolved

    if directory:
        logger.warning(
            "Diretório de templates '%s' não encontrado, utilizando diretório padrão.",
            directory,
        )
        default_dir = _resolve_package_path(DEFAULT_TEMPLATES_DIR)
        if default_dir.exists():
            return default_dir

        logger.error(
            "Diretório padrão de templates '%s' também não foi localizado.",
            DEFAULT_TEMPLATES_DIR,
        )

    return resolved


_BREAK_TAG_PATTERN = re.compile(r"<\s*/?\s*br\s*/?\s*>", re.IGNORECASE)
_INLINE_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_MERMAID_COMMENT_PREFIX = "%%"
_MERMAID_NO_TERMINATOR_PREFIXES = (
    "C4Context",
    "C4Container",
    "C4Component",
    "C4Dynamic",
    "C4Deployment",
    "title",
    "Person",
    "Person_Ext",
    "System",
    "System_Ext",
    "Container",
    "Container_Ext",
    "Component",
    "Component_Ext",
    "Boundary",
    "Enterprise_Boundary",
    "System_Boundary",
    "Container_Boundary",
    "Component_Boundary",
    "Rel",
    "Rel_D",
    "Rel_U",
    "Rel_R",
    "Rel_L",
    "Rel_Back",
    "BiRel",
    "UpdateElementStyle",
    "UpdateRelStyle",
    "SHOW_LEGEND",
    "Hide",
    "IncludeElement",
    "IncludeRelationship",
    "Lay",
    "Lay_D",
    "Lay_R",
)


def _clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""

    # Normaliza quebras de linha vindas de HTML e sequências de espaços.
    normalized = _BREAK_TAG_PATTERN.sub("\n", value)
    normalized = normalized.replace("\r", "\n")
    normalized = _INLINE_WHITESPACE_RE.sub(" ", normalized)
    normalized = normalized.replace(" \n", "\n").replace("\n ", "\n")
    # Evita múltiplas quebras consecutivas que não agregam informação.
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)

    return normalized.strip()


def _finalize_mermaid_lines(lines: Iterable[str]) -> str:
    """Normaliza linhas Mermaid garantindo separadores explícitos.

    Alguns consumidores removem quebras de linha ao serializar a saída. O Mermaid
    permite utilizar ponto e vírgula como delimitador explícito entre comandos,
    por isso garantimos o caractere ao final de todas as instruções não
    comentadas. Comentários (`%%`) e linhas vazias são preservados exatamente
    como foram construídos.
    """

    finalized: List[str] = []

    for original in lines:
        if original is None:
            continue

        text = original.rstrip()
        if not text:
            finalized.append("")
            continue

        stripped = text.lstrip()
        if stripped.startswith(_MERMAID_COMMENT_PREFIX):
            finalized.append(text)
            continue

        if stripped.startswith("}"):
            finalized.append(text)
            continue

        prefix = stripped.split("(", 1)[0].strip()
        prefixes_to_check = {prefix}
        if " " in stripped:
            prefixes_to_check.add(stripped.split(" ", 1)[0].strip())
        if any(candidate in _MERMAID_NO_TERMINATOR_PREFIXES for candidate in prefixes_to_check):
            finalized.append(text.rstrip(";"))
            continue

        if not stripped.endswith(";"):
            text = f"{text};"

        finalized.append(text)

    return "\n".join(finalized)


def _text_payload(element: Optional[ET.Element]) -> Optional[Dict[str, str]]:
    if element is None:
        return None
    text = _clean_text(element.text or "")
    lang = element.get(XML_LANG_ATTR)
    if not text:
        return None
    payload: Dict[str, str] = {"text": text}
    if lang:
        payload["lang"] = lang
    return payload


def _payload_text(payload: Optional[Dict[str, Any]]) -> Optional[str]:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload.get("text")
    if isinstance(payload, str):
        return payload
    return None


def _normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, dict):
        return _payload_text(value)
    if isinstance(value, (str, bytes)):
        text = value.decode("utf-8") if isinstance(value, bytes) else value
        return _clean_text(text)
    return None


def _truncate_text(text: str, limit: int = 160) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _local_name(tag: Any) -> str:
    text = str(tag)
    if "}" in text:
        return text.rsplit("}", 1)[1]
    return text


def _mermaid_escape(value: str) -> str:
    """Escape strings for safe embedding inside Mermaid diagrams."""

    sanitized = value.replace("\\", "\\\\").replace("\r", "\n")
    sanitized = sanitized.replace("\"", "\\\"")

    # Mermaid interpreta pipes como delimitadores de rótulos de arestas e colchetes
    # como parte da sintaxe de nós. Convertê-los em entidades HTML evita erros de
    # sintaxe mantendo a renderização correta.
    sanitized = sanitized.replace("|", "&#124;")
    sanitized = sanitized.replace("[", "&#91;").replace("]", "&#93;")

    # Converte quebras de linha explícitas para o formato aceito pelo Mermaid.
    sanitized = sanitized.replace("\n", "<br/>")

    return sanitized


def _sanitize_mermaid_identifier(identifier: str, fallback: str = "node") -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in identifier)
    cleaned = cleaned.strip("_")
    if not cleaned:
        cleaned = fallback
    if cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return cleaned


def _format_comment_lines(text: str, width: int = 100) -> List[str]:
    if not text:
        return []
    normalized = _clean_text(text)
    if not normalized:
        return []

    wrapped: List[str] = []
    for paragraph in normalized.split("\n"):
        stripped = paragraph.strip()
        if not stripped:
            continue
        wrapped.extend(textwrap.wrap(stripped, width=width))

    return wrapped


def _coerce_number(value: Optional[str]) -> Optional[float | int | str]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if number.is_integer():
        return int(number)
    return number


def _parse_color_element(element: Optional[ET.Element]) -> Optional[Dict[str, Any]]:
    if element is None:
        return None
    data: Dict[str, Any] = {}
    for attr in ("r", "g", "b", "a"):
        coerced = _coerce_number(element.get(attr))
        if coerced is not None:
            data[attr] = coerced
    return data or None


def _parse_font_element(element: Optional[ET.Element], ns: Dict[str, str]) -> Optional[Dict[str, Any]]:
    if element is None:
        return None
    font: Dict[str, Any] = {}
    for attr in ("name", "size", "style"):
        value = element.get(attr)
        if value is not None:
            coerced = _coerce_number(value) if attr == "size" else value
            font[attr] = coerced
    color_el = element.find("a:color", ns)
    color = _parse_color_element(color_el)
    if color:
        font["color"] = color
    return font or None


def _parse_style_element(element: Optional[ET.Element], ns: Dict[str, str]) -> Optional[Dict[str, Any]]:
    if element is None:
        return None
    style: Dict[str, Any] = {}
    fill = _parse_color_element(element.find("a:fillColor", ns))
    if fill:
        style["fillColor"] = fill
    line = _parse_color_element(element.find("a:lineColor", ns))
    if line:
        style["lineColor"] = line
    font = _parse_font_element(element.find("a:font", ns), ns)
    if font:
        style["font"] = font
    return style or None


def _parse_properties_container(container: Optional[ET.Element], ns: Dict[str, str]) -> Optional[List[Dict[str, Any]]]:
    if container is None:
        return None
    properties: List[Dict[str, Any]] = []
    for prop in container.findall("a:property", ns):
        item: Dict[str, Any] = {}
        for attr in ("identifier", "key", "value"):
            value = prop.get(attr)
            if value is not None:
                item[attr] = value
        documentation = _text_payload(prop.find("a:documentation", ns))
        if documentation:
            item["documentation"] = documentation
        if item:
            properties.append(item)
    return properties or None


def _parse_organization_item_full(node: ET.Element, ns: Dict[str, str]) -> Dict[str, Any]:
    item: Dict[str, Any] = {}
    identifier_ref = node.get("identifierRef")
    identifier = node.get("identifier")
    if identifier_ref:
        item["identifierRef"] = identifier_ref
    if identifier:
        item["identifier"] = identifier
    label = _text_payload(node.find("a:label", ns))
    if label:
        item["label"] = label
    documentation = _text_payload(node.find("a:documentation", ns))
    if documentation:
        item["documentation"] = documentation
    children = [
        _parse_organization_item_full(child, ns)
        for child in node.findall("a:item", ns)
    ]
    if children:
        item["items"] = children
    return item


def _parse_view_connection_full(node: ET.Element, ns: Dict[str, str]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    identifier = node.get("identifier")
    if identifier:
        data["id"] = identifier
    conn_type = node.get(XSI_ATTR)
    if conn_type:
        data["type"] = conn_type
    for attr in ("relationshipRef", "source", "target"):
        value = node.get(attr)
        if value:
            data[attr] = value

    child_order: List[str] = []
    for child in list(node):
        local = _local_name(child.tag)
        if local == "style":
            child_order.append("style")
            style = _parse_style_element(child, ns)
            if style:
                data["style"] = style
        elif local == "label":
            child_order.append("label")
            label = _text_payload(child)
            if label:
                data["label"] = label
        elif local == "documentation":
            documentation = _text_payload(child)
            if documentation:
                data["documentation"] = documentation
        elif local == "points":
            child_order.append("points")
            points: List[Dict[str, Any]] = []
            for pt in child.findall("a:point", ns):
                point_data: Dict[str, Any] = {}
                for coord in ("x", "y"):
                    coord_value = _coerce_number(pt.get(coord))
                    if coord_value is not None:
                        point_data[coord] = coord_value
                if point_data:
                    points.append(point_data)
            if points:
                data["points"] = points
        elif local == "properties":
            child_order.append("properties")
            properties = _parse_properties_container(child, ns)
            if properties:
                data["properties"] = properties
    if child_order:
        data["child_order"] = child_order
    return data


def _parse_view_node_full(node: ET.Element, ns: Dict[str, str]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    identifier = node.get("identifier")
    if identifier:
        data["id"] = identifier
    node_type = node.get(XSI_ATTR)
    if node_type:
        data["type"] = node_type
    bounds: Dict[str, Any] = {}
    for attr in ("x", "y", "w", "h"):
        value = _coerce_number(node.get(attr))
        if value is not None:
            bounds[attr] = value
    if bounds:
        data["bounds"] = bounds
    for attr in ("elementRef", "relationshipRef", "viewRef"):
        value = node.get(attr)
        if value:
            data[attr] = value

    child_order: List[str] = []
    nodes: List[Dict[str, Any]] = []
    connections: List[Dict[str, Any]] = []

    for child in list(node):
        local = _local_name(child.tag)
        if local == "style":
            child_order.append("style")
            style = _parse_style_element(child, ns)
            if style:
                data["style"] = style
        elif local == "label":
            child_order.append("label")
            label = _text_payload(child)
            if label:
                data["label"] = label
        elif local == "documentation":
            documentation = _text_payload(child)
            if documentation:
                data["documentation"] = documentation
        elif local == "node":
            child_order.append("node")
            nodes.append(_parse_view_node_full(child, ns))
        elif local == "connection":
            child_order.append("connection")
            connections.append(_parse_view_connection_full(child, ns))
        elif local == "viewRef":
            child_order.append("viewRef")
            view_ref = child.get("ref")
            if view_ref:
                data.setdefault("refs", {})["viewRef"] = view_ref
        elif local == "properties":
            child_order.append("properties")
            properties = _parse_properties_container(child, ns)
            if properties:
                data["properties"] = properties
    if nodes:
        data["nodes"] = nodes
    if connections:
        data["connections"] = connections
    if child_order:
        data["child_order"] = child_order
    return data


def _parse_view_diagram_full(view: ET.Element, ns: Dict[str, str]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    identifier = view.get("identifier")
    if identifier:
        data["id"] = identifier
    view_type = view.get(XSI_ATTR)
    if view_type:
        data["type"] = view_type

    nodes: List[Dict[str, Any]] = []
    connections: List[Dict[str, Any]] = []
    child_order: List[str] = []

    for child in list(view):
        local = _local_name(child.tag)
        if local == "name":
            name = _text_payload(child)
            if name:
                data["name"] = name
        elif local == "documentation":
            documentation = _text_payload(child)
            if documentation:
                data["documentation"] = documentation
        elif local == "style":
            child_order.append("style")
            style = _parse_style_element(child, ns)
            if style:
                data["style"] = style
        elif local == "label":
            child_order.append("label")
            label = _text_payload(child)
            if label:
                data["label"] = label
        elif local == "node":
            child_order.append("node")
            nodes.append(_parse_view_node_full(child, ns))
        elif local == "connection":
            child_order.append("connection")
            connections.append(_parse_view_connection_full(child, ns))
        elif local == "properties":
            child_order.append("properties")
            properties = _parse_properties_container(child, ns)
            if properties:
                data["properties"] = properties
    if nodes:
        data["nodes"] = nodes
    if connections:
        data["connections"] = connections
    if child_order:
        data["child_order"] = child_order
    return data


def _parse_element_full(element: ET.Element, ns: Dict[str, str]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    identifier = element.get("identifier")
    if identifier:
        data["id"] = identifier
    element_type = element.get(XSI_ATTR)
    if element_type:
        data["type"] = element_type
    name = _text_payload(element.find("a:name", ns))
    if name:
        data["name"] = name
    documentation = _text_payload(element.find("a:documentation", ns))
    if documentation:
        data["documentation"] = documentation
    properties = _parse_properties_container(element.find("a:properties", ns), ns)
    if properties:
        data["properties"] = properties
    return data


def _parse_relationship_full(relationship: ET.Element, ns: Dict[str, str]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    identifier = relationship.get("identifier")
    if identifier:
        data["id"] = identifier
    rel_type = relationship.get(XSI_ATTR)
    if rel_type:
        data["type"] = rel_type
    for attr in ("source", "target"):
        value = relationship.get(attr)
        if value:
            data[attr] = value
    documentation = _text_payload(relationship.find("a:documentation", ns))
    if documentation:
        data["documentation"] = documentation
    properties = _parse_properties_container(relationship.find("a:properties", ns), ns)
    if properties:
        data["properties"] = properties
    return data


def _parse_template_blueprint(template: Path) -> Dict[str, Any]:
    tree = ET.parse(template)
    root = tree.getroot()
    ns = {"a": ARCHIMATE_NS}

    blueprint: Dict[str, Any] = {
        "model_identifier": root.get("identifier"),
    }

    name = _text_payload(root.find("a:name", ns))
    if name:
        blueprint["model_name"] = name
    documentation = _text_payload(root.find("a:documentation", ns))
    if documentation:
        blueprint["model_documentation"] = documentation

    elements = [
        _parse_element_full(el, ns)
        for el in root.findall("a:elements/a:element", ns)
    ]
    if elements:
        blueprint["elements"] = elements

    relationships = [
        _parse_relationship_full(rel, ns)
        for rel in root.findall("a:relationships/a:relationship", ns)
    ]
    if relationships:
        blueprint["relations"] = relationships

    organizations = [
        _parse_organization_item_full(item, ns)
        for item in root.findall("a:organizations/a:item", ns)
    ]
    if organizations:
        blueprint["organizations"] = organizations

    views_root = root.find("a:views", ns)
    if views_root is not None:
        views_payload: Dict[str, Any] = {}
        viewpoints = []
        for viewpoint in views_root.findall("a:viewpoints/a:viewpoint", ns):
            vp: Dict[str, Any] = {}
            vp_id = viewpoint.get("identifier")
            if vp_id:
                vp["id"] = vp_id
            vp_name = _text_payload(viewpoint.find("a:name", ns))
            if vp_name:
                vp["name"] = vp_name
            vp_doc = _text_payload(viewpoint.find("a:documentation", ns))
            if vp_doc:
                vp["documentation"] = vp_doc
            if vp:
                viewpoints.append(vp)
        if viewpoints:
            views_payload["viewpoints"] = viewpoints

        diagrams = [
            _parse_view_diagram_full(view, ns)
            for view in views_root.findall("a:diagrams/a:view", ns)
        ]
        if diagrams:
            views_payload["diagrams"] = diagrams
        if views_payload:
            blueprint["views"] = views_payload

    return blueprint


def _simplify_organization_item(item: Dict[str, Any]) -> Dict[str, Any]:
    simplified: Dict[str, Any] = {}
    if item.get("identifierRef"):
        simplified["identifierRef"] = item["identifierRef"]
    if item.get("identifier"):
        simplified["identifier"] = item["identifier"]
    label_text = _payload_text(item.get("label"))
    if label_text:
        simplified["label"] = label_text
    doc_text = _payload_text(item.get("documentation"))
    if doc_text:
        simplified["documentation"] = doc_text
    children = [
        _simplify_organization_item(child)
        for child in item.get("items", [])
    ]
    if children:
        simplified["items"] = children
    return simplified


def _simplify_view_connection(connection: Dict[str, Any]) -> Dict[str, Any]:
    simplified: Dict[str, Any] = {}
    if connection.get("id"):
        simplified["identifier"] = connection["id"]
    if connection.get("type"):
        simplified["type"] = connection["type"]
    for attr in ("relationshipRef", "source", "target"):
        value = connection.get(attr)
        if value:
            simplified[attr] = value
    label_text = _payload_text(connection.get("label"))
    if label_text:
        simplified["label_hint"] = label_text
    doc_text = _payload_text(connection.get("documentation"))
    if doc_text:
        simplified["documentation_hint"] = doc_text
    return simplified


def _simplify_view_node(node: Dict[str, Any]) -> Dict[str, Any]:
    simplified: Dict[str, Any] = {}
    if node.get("id"):
        simplified["identifier"] = node["id"]
    if node.get("type"):
        simplified["type"] = node["type"]

    element_ref = node.get("elementRef") or (node.get("refs") or {}).get("elementRef")
    if element_ref:
        simplified["elementRef"] = element_ref
    relationship_ref = node.get("relationshipRef") or (node.get("refs") or {}).get("relationshipRef")
    if relationship_ref:
        simplified["relationshipRef"] = relationship_ref
    view_ref = node.get("viewRef") or (node.get("refs") or {}).get("viewRef")
    if view_ref:
        simplified["viewRef"] = view_ref

    label_text = _payload_text(node.get("label"))
    if label_text:
        simplified["label_hint"] = label_text
    doc_text = _payload_text(node.get("documentation"))
    if doc_text:
        simplified["documentation_hint"] = doc_text

    children = [
        _simplify_view_node(child)
        for child in node.get("nodes", [])
    ]
    if children:
        simplified["nodes"] = children

    connections = [
        _simplify_view_connection(conn)
        for conn in node.get("connections", [])
    ]
    if connections:
        simplified["connections"] = connections

    return simplified


def _simplify_view_diagram(diagram: Dict[str, Any]) -> Dict[str, Any]:
    simplified: Dict[str, Any] = {}
    if diagram.get("id"):
        simplified["identifier"] = diagram["id"]
    if diagram.get("type"):
        simplified["type"] = diagram["type"]
    name_text = _payload_text(diagram.get("name"))
    if name_text:
        simplified["name"] = name_text
    doc_text = _payload_text(diagram.get("documentation"))
    if doc_text:
        simplified["documentation"] = doc_text

    nodes = [
        _simplify_view_node(node)
        for node in diagram.get("nodes", [])
    ]
    if nodes:
        simplified["nodes"] = nodes

    connections = [
        _simplify_view_connection(conn)
        for conn in diagram.get("connections", [])
    ]
    if connections:
        simplified["connections"] = connections
    return simplified


def _build_guidance_from_blueprint(blueprint: Dict[str, Any]) -> Dict[str, Any]:
    guidance: Dict[str, Any] = {
        "model": {
            "identifier": blueprint.get("model_identifier"),
        }
    }
    name_text = _payload_text(blueprint.get("model_name"))
    if name_text:
        guidance["model"]["name"] = name_text
    doc_text = _payload_text(blueprint.get("model_documentation"))
    if doc_text:
        guidance["model"]["documentation"] = doc_text

    elements_guidance: List[Dict[str, Any]] = []
    for element in blueprint.get("elements", []):
        entry: Dict[str, Any] = {
            "identifier": element.get("id"),
            "type": element.get("type"),
        }
        name_hint = _payload_text(element.get("name"))
        if name_hint:
            entry["name_hint"] = name_hint
        doc_hint = _payload_text(element.get("documentation"))
        if doc_hint:
            entry["documentation_hint"] = doc_hint
        elements_guidance.append(entry)
    guidance["elements"] = elements_guidance

    relations_guidance: List[Dict[str, Any]] = []
    for relation in blueprint.get("relations", []):
        entry = {
            "identifier": relation.get("id"),
            "type": relation.get("type"),
        }
        if relation.get("source"):
            entry["source"] = relation.get("source")
        if relation.get("target"):
            entry["target"] = relation.get("target")
        doc_hint = _payload_text(relation.get("documentation"))
        if doc_hint:
            entry["documentation_hint"] = doc_hint
        relations_guidance.append(entry)
    guidance["relationships"] = relations_guidance

    guidance["organizations"] = [
        _simplify_organization_item(item)
        for item in blueprint.get("organizations", [])
    ]

    if blueprint.get("views"):
        diagrams = [
            _simplify_view_diagram(diagram)
            for diagram in blueprint.get("views", {}).get("diagrams", [])
        ]
        view_section: Dict[str, Any] = {}
        if diagrams:
            view_section["diagrams"] = diagrams
        if view_section:
            guidance["views"] = view_section

    return guidance


def _strip_template_keys(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    cleaned = copy.deepcopy(data)
    cleaned.pop("template_identifier", None)
    cleaned.pop("template_id", None)
    identifier = cleaned.pop("identifier", None)
    if identifier and "id" not in cleaned:
        cleaned["id"] = identifier
    return cleaned


def _apply_textual_override(
    target: Dict[str, Any],
    source: Dict[str, Any],
    target_key: str,
    keys: Iterable[str],
) -> None:
    for key in keys:
        if key in source and source[key] is not None:
            target[target_key] = source[key]
            return


def _view_node_key(node: Dict[str, Any]) -> Optional[str]:
    if not node:
        return None
    for key in ("id", "identifier"):
        value = node.get(key)
        if value:
            return str(value)
    for key in ("elementRef", "relationshipRef"):
        value = node.get(key)
        if not value and isinstance(node.get("refs"), dict):
            value = node["refs"].get(key)
        if value:
            return f"{key}:{value}"
    return None


def _merge_view_connections(
    template_connections: List[Dict[str, Any]],
    override_connections: Optional[Iterable[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    template_connections = [copy.deepcopy(conn) for conn in template_connections or []]
    overrides = list(override_connections or [])
    if not template_connections and not overrides:
        return []

    override_map: Dict[str, Dict[str, Any]] = {}
    extras: List[Dict[str, Any]] = []
    for conn in overrides:
        clean = _strip_template_keys(conn) or {}
        key = clean.get("id") or clean.get("identifier")
        if key:
            override_map[str(key)] = clean
        else:
            extras.append(clean)

    merged: List[Dict[str, Any]] = []
    for conn in template_connections:
        key = conn.get("id")
        override = override_map.get(str(key)) if key else None
        if override:
            _apply_textual_override(conn, override, "label", ("label", "label_hint"))
            _apply_textual_override(conn, override, "documentation", ("documentation", "documentation_hint"))
        merged.append(conn)

    merged.extend(copy.deepcopy(extra) for extra in extras)
    return merged


def _merge_view_nodes(
    template_nodes: List[Dict[str, Any]],
    override_nodes: Optional[Iterable[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    template_nodes = [copy.deepcopy(node) for node in template_nodes or []]
    for node in template_nodes:
        _standardize_view_tree(node)

    overrides = list(override_nodes or [])
    if not template_nodes and not overrides:
        return []

    override_map: Dict[str, Dict[str, Any]] = {}
    extras: List[Dict[str, Any]] = []
    for node in overrides:
        clean = _strip_template_keys(node) or {}
        _standardize_view_tree(clean)
        key = _view_node_key(clean)
        if key:
            override_map[key] = clean
        else:
            extras.append(clean)

    merged: List[Dict[str, Any]] = []
    for node in template_nodes:
        key = _view_node_key(node)
        override = override_map.get(key) if key else None
        merged.append(_merge_view_node(node, override))

    for extra in extras:
        extra_copy = copy.deepcopy(extra)
        _standardize_view_tree(extra_copy)
        merged.append(extra_copy)
    return merged


def _merge_view_node(template_node: Dict[str, Any], override_node: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = copy.deepcopy(template_node)
    clean_override = copy.deepcopy(override_node) if override_node else None
    if clean_override:
        _apply_textual_override(merged, clean_override, "label", ("label", "label_hint"))
        _apply_textual_override(merged, clean_override, "documentation", ("documentation", "documentation_hint"))

        for key in ("type", "elementRef", "relationshipRef", "viewRef"):
            if clean_override.get(key) is not None:
                merged[key] = clean_override[key]

        if "refs" in clean_override:
            merged["refs"] = copy.deepcopy(clean_override.get("refs"))

        if "bounds" in clean_override:
            merged["bounds"] = copy.deepcopy(clean_override.get("bounds"))

        if "style" in clean_override:
            merged["style"] = copy.deepcopy(clean_override.get("style"))

        if "child_order" in clean_override:
            merged["child_order"] = list(clean_override.get("child_order") or [])

    template_children = _node_children(template_node)
    override_children = _node_children(clean_override) if clean_override else None
    merged_children = _merge_view_nodes(template_children, override_children)
    if merged_children:
        merged["nodes"] = merged_children
    elif "nodes" in merged:
        merged.pop("nodes", None)

    template_connections = template_node.get("connections", [])
    override_connections = clean_override.get("connections") if clean_override else None
    merged_connections = _merge_view_connections(template_connections, override_connections)
    if merged_connections:
        merged["connections"] = merged_connections
    elif "connections" in merged:
        merged.pop("connections", None)

    return merged


def _looks_like_view_diagram(candidate: Any) -> bool:
    """Return ``True`` when the payload resembles a diagram definition."""

    if not isinstance(candidate, dict):
        return False

    if candidate.get("type") == "Diagram":
        return True

    for key in ("nodes", "connections", "children"):
        value = candidate.get(key)
        if isinstance(value, list) and value:
            return True

    return False


def _deduplicate_views(views: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove visão duplicadas preservando a ordem original."""

    unique: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for view in views:
        if not isinstance(view, dict):
            continue

        key_parts: List[str] = []
        identifier = view.get("id") or view.get("identifier")
        if identifier:
            key_parts.append(f"id:{identifier}")
        name = _normalize_text(view.get("name"))
        if name:
            key_parts.append(f"name:{name.lower()}")

        dedupe_key = "|".join(key_parts)
        if dedupe_key and dedupe_key in seen:
            continue
        if dedupe_key:
            seen.add(dedupe_key)
        unique.append(view)

    return unique


def _normalize_view_diagrams(views_payload: Any) -> List[Dict[str, Any]]:
    """Normalize assorted view payload formats into a list of diagrams."""

    if views_payload is None:
        return []

    diagrams: List[Dict[str, Any]] = []

    def _add_candidate(candidate: Any) -> None:
        if not _looks_like_view_diagram(candidate):
            return
        prepared = copy.deepcopy(candidate)
        identifier = prepared.get("identifier")
        if identifier and not prepared.get("id"):
            prepared["id"] = identifier
        diagrams.append(prepared)

    if isinstance(views_payload, dict):
        explicit = views_payload.get("diagrams")
        if isinstance(explicit, list):
            for entry in explicit:
                _add_candidate(entry)
        elif isinstance(explicit, dict):
            _add_candidate(explicit)

        for key, value in views_payload.items():
            if key in {"diagrams", "viewpoints"}:
                continue
            if isinstance(value, dict):
                _add_candidate(value)
            elif isinstance(value, list):
                for item in value:
                    _add_candidate(item)

        _add_candidate(views_payload)
    elif isinstance(views_payload, list):
        for entry in views_payload:
            _add_candidate(entry)
    else:
        _add_candidate(views_payload)

    return _deduplicate_views(diagrams)


def _extract_view_selectors(payload: Dict[str, Any]) -> Dict[str, set[str]]:
    """Coleta identificadores ou nomes de visão informados pelo agente."""

    selectors: Dict[str, set[str]] = {"ids": set(), "names": set()}

    def _register(value: Any, bucket: str) -> None:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                _register(item, bucket)
            return
        if isinstance(value, (int, float)):
            text = str(value)
        elif isinstance(value, str):
            text = value.strip()
        else:
            return
        if not text:
            return
        if bucket == "names":
            selectors[bucket].add(text.lower())
        else:
            selectors[bucket].add(text)

    id_keys = (
        "view_identifier",
        "view_id",
        "viewIdentifier",
        "viewId",
        "selected_view_identifier",
        "selected_view_id",
    )
    name_keys = (
        "view_name",
        "viewName",
        "view",
        "selected_view",
        "selected_view_name",
        "View-Name",
    )

    for key in id_keys:
        _register(payload.get(key), "ids")
    for key in name_keys:
        _register(payload.get(key), "names")

    view_metadata_keys = (
        "view_metadata",
        "viewMeta",
        "view_info",
        "viewInfo",
        "selected_view_metadata",
    )
    for meta_key in view_metadata_keys:
        meta = payload.get(meta_key)
        if isinstance(meta, dict):
            for key in id_keys:
                _register(meta.get(key), "ids")
            for key in name_keys:
                _register(meta.get(key), "names")
            _register(meta.get("identifier"), "ids")
            _register(meta.get("id"), "ids")
            _register(meta.get("name"), "names")

    views_payload = payload.get("views")
    if isinstance(views_payload, dict):
        for key in ("selected", "selected_view", "selectedView"):
            value = views_payload.get(key)
            if isinstance(value, dict):
                _register(value.get("identifier"), "ids")
                _register(value.get("id"), "ids")
                _register(value.get("name"), "names")
            else:
                _register(value, "names")

    return selectors


def _filter_views_by_selectors(
    views: List[Dict[str, Any]], selectors: Dict[str, set[str]]
) -> List[Dict[str, Any]]:
    if not selectors.get("ids") and not selectors.get("names"):
        return views

    filtered: List[Dict[str, Any]] = []
    target_ids = {str(value) for value in selectors.get("ids", set()) if value}
    target_names = selectors.get("names", set())

    for view in views:
        if not isinstance(view, dict):
            continue

        matches = False
        identifier = view.get("id") or view.get("identifier")
        if identifier and str(identifier) in target_ids:
            matches = True
        else:
            name = _normalize_text(view.get("name"))
            if name and name.lower() in target_names:
                matches = True

        if matches:
            filtered.append(view)

    return filtered


def _merge_view_diagram(
    template_diagram: Dict[str, Any],
    override_diagram: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    merged = copy.deepcopy(template_diagram)
    clean_override = copy.deepcopy(override_diagram) if override_diagram else None
    if clean_override:
        _apply_textual_override(merged, clean_override, "name", ("name", "name_hint"))
        _apply_textual_override(merged, clean_override, "documentation", ("documentation", "documentation_hint"))

    merged["nodes"] = _merge_view_nodes(
        template_diagram.get("nodes", []),
        clean_override.get("nodes") if clean_override else None,
    )
    merged["connections"] = _merge_view_connections(
        template_diagram.get("connections", []),
        clean_override.get("connections") if clean_override else None,
    )
    return merged


def _merge_views(
    template_views: Dict[str, Any],
    override_views: Optional[Any],
) -> Dict[str, Any]:
    template_views = copy.deepcopy(template_views or {})
    template_diagrams = template_views.get("diagrams", [])
    overrides = _normalize_view_diagrams(override_views)

    override_map: Dict[str, Dict[str, Any]] = {}
    extras: List[Dict[str, Any]] = []
    for diagram in overrides:
        clean = _strip_template_keys(diagram) or {}
        key = clean.get("id") or clean.get("identifier")
        if key:
            override_map[str(key)] = clean
        else:
            extras.append(clean)

    merged_diagrams: List[Dict[str, Any]] = []
    for diagram in template_diagrams:
        key = diagram.get("id")
        override = override_map.get(str(key)) if key else None
        merged_diagrams.append(_merge_view_diagram(diagram, override))

    merged_diagrams.extend(copy.deepcopy(extra) for extra in extras)

    result: Dict[str, Any] = {"diagrams": merged_diagrams}
    if template_views.get("viewpoints"):
        result["viewpoints"] = template_views["viewpoints"]
    return result


def _organization_key(item: Dict[str, Any]) -> Optional[str]:
    for key in ("identifier", "identifierRef"):
        value = item.get(key)
        if value:
            return f"{key}:{value}"
    label = _payload_text(item.get("label"))
    if label:
        return f"label:{label}"
    return None


def _merge_organization_node(
    template_node: Dict[str, Any],
    override_node: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    merged = copy.deepcopy(template_node)
    if override_node:
        label = override_node.get("label")
        if label is not None:
            merged["label"] = label
        documentation = override_node.get("documentation")
        if documentation is not None:
            merged["documentation"] = documentation
    template_children = template_node.get("items", [])
    override_children = override_node.get("items") if override_node else None
    merged_children = _merge_organization_items(template_children, override_children)
    if merged_children:
        merged["items"] = merged_children
    elif "items" in merged:
        merged.pop("items", None)
    return merged


def _merge_organization_items(
    template_items: List[Dict[str, Any]],
    override_items: Optional[Iterable[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    template_items = [copy.deepcopy(item) for item in template_items or []]
    overrides = list(override_items or [])
    if not template_items and not overrides:
        return []

    override_map: Dict[str, Dict[str, Any]] = {}
    extras: List[Dict[str, Any]] = []
    for item in overrides:
        key = _organization_key(item)
        if key:
            override_map[key] = item
        else:
            extras.append(item)

    merged: List[Dict[str, Any]] = []
    for item in template_items:
        key = _organization_key(item)
        override = override_map.get(key) if key else None
        merged.append(_merge_organization_node(item, override))

    merged.extend(copy.deepcopy(extra) for extra in extras)
    return merged


def _merge_organizations(
    template_items: List[Dict[str, Any]],
    override_items: Optional[Iterable[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    return _merge_organization_items(template_items, override_items)


def _merge_elements(
    template_elements: List[Dict[str, Any]],
    override_elements: Optional[Iterable[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    template_elements = [copy.deepcopy(element) for element in template_elements or []]
    overrides = list(override_elements or [])
    if not template_elements and not overrides:
        return []

    override_map: Dict[str, Dict[str, Any]] = {}
    extras: List[Dict[str, Any]] = []
    for element in overrides:
        clean = _strip_template_keys(element) or {}
        key = clean.get("id")
        if key:
            override_map[str(key)] = clean
        else:
            extras.append(clean)

    merged: List[Dict[str, Any]] = []
    for element in template_elements:
        key = element.get("id")
        override = override_map.get(str(key)) if key else None
        if override:
            for field in ("name", "documentation", "properties", "type"):
                if field in override:
                    element[field] = override[field]
        merged.append(element)

    merged.extend(copy.deepcopy(extra) for extra in extras)
    return merged


def _merge_relations(
    template_relations: List[Dict[str, Any]],
    override_relations: Optional[Iterable[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    template_relations = [copy.deepcopy(relation) for relation in template_relations or []]
    overrides = list(override_relations or [])
    if not template_relations and not overrides:
        return []

    override_map: Dict[str, Dict[str, Any]] = {}
    extras: List[Dict[str, Any]] = []
    for relation in overrides:
        clean = _strip_template_keys(relation) or {}
        key = clean.get("id")
        if key:
            override_map[str(key)] = clean
        else:
            extras.append(clean)

    merged: List[Dict[str, Any]] = []
    for relation in template_relations:
        key = relation.get("id")
        override = override_map.get(str(key)) if key else None
        if override:
            for field in ("source", "target", "documentation", "properties", "type"):
                if field in override:
                    relation[field] = override[field]
        merged.append(relation)

    merged.extend(copy.deepcopy(extra) for extra in extras)
    return merged


def _register_element_entry(
    lookup: Dict[str, Dict[str, Any]],
    element: Dict[str, Any],
    source: str,
) -> None:
    identifier = element.get("id") or element.get("identifier")
    if not identifier:
        return
    key = str(identifier)
    entry = lookup.setdefault(key, {"id": key})

    element_type = element.get("type")
    if element_type and "type" not in entry:
        entry["type"] = element_type

    name = _normalize_text(element.get("name"))
    if name:
        if source == "template":
            entry.setdefault("template_name", name)
        else:
            entry["name"] = name

    documentation = _normalize_text(element.get("documentation"))
    if documentation:
        if source == "template":
            entry.setdefault("template_documentation", documentation)
        else:
            entry["documentation"] = documentation

    properties = element.get("properties")
    if properties and source == "template":
        entry.setdefault("template_properties", properties)


def _register_relationship_entry(
    lookup: Dict[str, Dict[str, Any]],
    relation: Dict[str, Any],
    source: str,
) -> None:
    identifier = relation.get("id") or relation.get("identifier")
    if not identifier:
        return
    key = str(identifier)
    entry = lookup.setdefault(key, {"id": key})

    rel_type = relation.get("type")
    if rel_type and "type" not in entry:
        entry["type"] = rel_type

    for attr in ("source", "target"):
        value = relation.get(attr)
        if value:
            entry.setdefault(attr, value)

    documentation = _normalize_text(relation.get("documentation"))
    if documentation:
        if source == "template":
            entry.setdefault("template_documentation", documentation)
        else:
            entry["documentation"] = documentation

    properties = relation.get("properties")
    if properties and source == "template":
        entry.setdefault("template_properties", properties)


def _build_element_lookup(
    template: Dict[str, Any], payload: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for element in template.get("elements", []) or []:
        if isinstance(element, dict):
            _register_element_entry(lookup, element, "template")
    for element in payload.get("elements", []) or []:
        if isinstance(element, dict):
            _register_element_entry(lookup, element, "datamodel")
    return lookup


def _build_relationship_lookup(
    template: Dict[str, Any], payload: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for relation in template.get("relations", []) or []:
        if isinstance(relation, dict):
            _register_relationship_entry(lookup, relation, "template")
    for relation in payload.get("relations", []) or []:
        if isinstance(relation, dict):
            _register_relationship_entry(lookup, relation, "datamodel")
    return lookup


def _node_children(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(node, dict):
        return []

    children = node.get("nodes")
    if isinstance(children, list):
        return children

    legacy_children = node.get("children")
    if isinstance(legacy_children, list):
        node["nodes"] = legacy_children
        node.pop("children", None)
        return legacy_children

    return []


def _standardize_view_tree(tree: Dict[str, Any]) -> None:
    if not isinstance(tree, dict):
        return

    for child in list(_node_children(tree)):
        if isinstance(child, dict):
            _standardize_view_tree(child)


def _flatten_view_nodes(nodes: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    flattened: Dict[str, Dict[str, Any]] = {}

    def _walk(items: Iterable[Dict[str, Any]]) -> None:
        for node in items or []:
            if not isinstance(node, dict):
                continue
            key = _view_node_key(node)
            if key:
                flattened[key] = node
            child_nodes = _node_children(node)
            if child_nodes:
                _walk(child_nodes)

    _walk(nodes or [])
    return flattened


def _flatten_view_connections(
    connections: Iterable[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    flattened: Dict[str, Dict[str, Any]] = {}
    for connection in connections or []:
        if not isinstance(connection, dict):
            continue
        identifier = connection.get("id") or connection.get("identifier")
        if identifier:
            flattened[str(identifier)] = connection
    return flattened


def _prune_view_to_datamodel(
    view_payload: Dict[str, Any],
    datamodel_node_map: Dict[str, Dict[str, Any]] | None,
    datamodel_connection_map: Dict[str, Dict[str, Any]] | None,
) -> None:
    """Remove nós e conexões que existem apenas na visão do template."""

    datamodel_node_map = datamodel_node_map or {}
    datamodel_connection_map = datamodel_connection_map or {}

    relevant_node_keys = {
        str(key)
        for key in datamodel_node_map.keys()
        if key is not None and str(key)
    }

    if relevant_node_keys:

        def _prune_children(nodes: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
            kept: List[Dict[str, Any]] = []
            for child in nodes or []:
                if not isinstance(child, dict):
                    continue
                if _prune_node(child):
                    kept.append(child)
            return kept

        def _prune_node(node: Dict[str, Any]) -> bool:
            key = _view_node_key(node)
            child_nodes = _node_children(node)
            kept_children = _prune_children(child_nodes)
            if kept_children:
                node["nodes"] = kept_children
            else:
                node.pop("nodes", None)

            keep_self = key is not None and str(key) in relevant_node_keys
            return keep_self or bool(kept_children)

        pruned_root_children = _prune_children(view_payload.get("nodes") or [])
        if pruned_root_children:
            view_payload["nodes"] = pruned_root_children
        else:
            view_payload.pop("nodes", None)

    if datamodel_connection_map:
        relevant_connection_keys = {
            str(key)
            for key in datamodel_connection_map.keys()
            if key is not None and str(key)
        }
        if relevant_connection_keys:
            filtered_connections: List[Dict[str, Any]] = []
            for connection in view_payload.get("connections") or []:
                if not isinstance(connection, dict):
                    continue
                identifier = connection.get("id") or connection.get("identifier")
                if identifier and str(identifier) in relevant_connection_keys:
                    filtered_connections.append(connection)
            if filtered_connections:
                view_payload["connections"] = filtered_connections
            else:
                view_payload.pop("connections", None)


def _merge_node_documentation(
    node: Dict[str, Any],
    blueprint_node: Optional[Dict[str, Any]],
) -> Tuple[Optional[str], Optional[str]]:
    node_doc = _normalize_text(node.get("documentation"))
    blueprint_doc = _normalize_text(
        blueprint_node.get("documentation") if blueprint_node else None
    )
    return node_doc, blueprint_doc


def _unique_alias(base: str, used: set[str]) -> str:
    candidate = base
    index = 1
    while candidate in used:
        candidate = f"{base}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def _gather_node_metadata(
    node: Dict[str, Any],
    element_lookup: Dict[str, Dict[str, Any]],
    blueprint_node: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    refs = node.get("refs") or {}
    element_ref = node.get("elementRef") or refs.get("elementRef")
    relationship_ref = node.get("relationshipRef") or refs.get("relationshipRef")
    view_ref = node.get("viewRef") or refs.get("viewRef")
    identifier = node.get("id") or node.get("identifier")

    element_entry = element_lookup.get(str(element_ref)) if element_ref else None

    label_candidates = [
        _normalize_text(node.get("label")),
        _normalize_text(blueprint_node.get("label")) if blueprint_node else None,
        element_entry.get("name") if element_entry and element_entry.get("name") else None,
        element_entry.get("template_name")
        if element_entry and element_entry.get("template_name")
        else None,
        str(element_ref) if element_ref else None,
        str(identifier) if identifier else None,
    ]
    title = next((candidate for candidate in label_candidates if candidate), "Elemento")

    node_type = node.get("type") or (element_entry.get("type") if element_entry else None)

    node_doc, template_doc = _merge_node_documentation(node, blueprint_node)
    if not node_doc and element_entry:
        node_doc = element_entry.get("documentation")
    if not template_doc and element_entry:
        template_doc = element_entry.get("template_documentation")

    doc_snippet_source = node_doc or template_doc
    doc_snippet = (
        _truncate_text(doc_snippet_source, 120) if doc_snippet_source else None
    )

    label_parts = [_mermaid_escape(title)]
    if node_type:
        label_parts.append(_mermaid_escape(f"Tipo: {node_type}"))
    if doc_snippet:
        label_parts.append(_mermaid_escape(f"Nota: {doc_snippet}"))

    metadata: Dict[str, Any] = {
        "id": identifier,
        "label": "<br/>".join(label_parts),
        "title": title,
        "type": node_type,
        "element_ref": element_ref,
        "relationship_ref": relationship_ref,
        "view_ref": view_ref,
        "documentation": node_doc,
        "template_documentation": template_doc,
    }

    if blueprint_node:
        metadata["template_label"] = _normalize_text(blueprint_node.get("label"))

    if element_entry:
        if element_entry.get("name"):
            metadata["element_name"] = element_entry.get("name")
        if element_entry.get("template_name"):
            metadata["element_name_template"] = element_entry.get("template_name")
        if element_entry.get("type"):
            metadata.setdefault("element_type", element_entry.get("type"))
        if element_entry.get("template_documentation"):
            metadata.setdefault(
                "element_template_documentation",
                element_entry.get("template_documentation"),
            )
        if element_entry.get("template_properties"):
            metadata["template_properties"] = element_entry.get("template_properties")

    return metadata


def _gather_connection_metadata(
    connection: Dict[str, Any],
    relation_lookup: Dict[str, Dict[str, Any]],
    blueprint_connection: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    identifier = connection.get("id") or connection.get("identifier")
    relation_ref = connection.get("relationshipRef")
    relation_entry = relation_lookup.get(str(relation_ref)) if relation_ref else None

    label_candidates = [
        _normalize_text(connection.get("label")),
        _normalize_text(blueprint_connection.get("label"))
        if blueprint_connection
        else None,
    ]
    label_text = next((candidate for candidate in label_candidates if candidate), None)

    relation_type = connection.get("type") or (
        relation_entry.get("type") if relation_entry else None
    )

    documentation = _normalize_text(connection.get("documentation"))
    template_doc = (
        _normalize_text(blueprint_connection.get("documentation"))
        if blueprint_connection
        else None
    )
    if not documentation and relation_entry:
        documentation = relation_entry.get("documentation")
    if not template_doc and relation_entry:
        template_doc = relation_entry.get("template_documentation")

    doc_snippet_source = documentation or template_doc
    doc_snippet = (
        _truncate_text(doc_snippet_source, 120) if doc_snippet_source else None
    )

    label_parts = []
    if relation_type:
        label_parts.append(relation_type)
    if label_text:
        label_parts.append(label_text)
    if doc_snippet:
        label_parts.append(doc_snippet)

    mermaid_label = " - ".join(part for part in label_parts if part)

    metadata: Dict[str, Any] = {
        "id": identifier,
        "label": mermaid_label,
        "relationship_ref": relation_ref,
        "type": relation_type,
        "documentation": documentation,
        "template_documentation": template_doc,
        "source": connection.get("source"),
        "target": connection.get("target"),
    }

    if relation_entry:
        if relation_entry.get("template_properties"):
            metadata["template_properties"] = relation_entry.get(
                "template_properties"
            )

    return metadata


def _detect_view_kind(
    view: Dict[str, Any], view_blueprint: Optional[Dict[str, Any]]
) -> Optional[str]:
    candidates = [
        _normalize_text(view.get("view_kind")),
        _normalize_text(view.get("name")),
    ]
    if view_blueprint:
        candidates.extend(
            [
                _normalize_text(view_blueprint.get("view_kind")),
                _normalize_text(view_blueprint.get("name")),
            ]
        )

    for candidate in candidates:
        if not candidate:
            continue
        normalized = candidate.lower()
        if "context" in normalized or "contexto" in normalized:
            return "context"
        if "container" in normalized:
            return "container"
        if "técn" in normalized or "tecn" in normalized:
            return "technical"
    return None


def _c4_header_for_kind(kind: str) -> str:
    if kind == "context":
        return "C4Context"
    if kind == "container":
        return "C4Container"
    if kind == "technical":
        return "C4Component"
    return "flowchart TD"


def _c4_boundary_macro(kind: str) -> str:
    if kind == "context":
        return "System_Boundary"
    if kind == "container":
        return "Container_Boundary"
    if kind == "technical":
        return "Component_Boundary"
    return "Boundary"


def _c4_element_macro(kind: str, is_external: bool) -> str:
    suffix = "_Ext" if is_external else ""
    if kind == "context":
        return f"System{suffix}"
    if kind == "container":
        return f"Container{suffix}"
    if kind == "technical":
        return f"Component{suffix}"
    return f"Container{suffix}" if suffix else "Container"


def _c4_element_technology(element_type: Optional[str]) -> Optional[str]:
    if not element_type:
        return None
    mapping = {
        "ApplicationComponent": "Aplicação",
        "ApplicationProcess": "Processo",
        "ApplicationEvent": "Evento",
        "DataObject": "Dados",
        "Artifact": "Artefato",
        "Deliverable": "Entregável",
        "WorkPackage": "Pacote",
    }
    return mapping.get(element_type, element_type)


def _c4_description(metadata: Dict[str, Any]) -> Optional[str]:
    documentation = metadata.get("documentation") or metadata.get(
        "template_documentation"
    )
    if documentation:
        return _truncate_text(str(documentation), 200)
    if metadata.get("title") and metadata.get("type"):
        return f"{metadata['title']} ({metadata['type']})"
    return None


def _c4_format_arguments(alias: str, *args: Optional[str]) -> str:
    formatted: List[str] = [alias]
    for arg in args:
        if arg is None:
            continue
        formatted.append(f'"{_mermaid_escape(arg)}"')
    return ", ".join(formatted)


def _c4_format_relation_arguments(
    source_alias: str,
    target_alias: str,
    label: Optional[str],
    technology: Optional[str],
    description: Optional[str],
) -> str:
    parts: List[str] = [source_alias, target_alias]
    if label is not None:
        parts.append(f'"{_mermaid_escape(label)}"')
    if technology is not None:
        parts.append(f'"{_mermaid_escape(technology)}"')
    if description is not None:
        parts.append(f'"{_mermaid_escape(description)}"')
    return ", ".join(parts)


def _should_mark_external(label: Optional[str]) -> bool:
    if not label:
        return False
    lowered = label.lower()
    return any(token in lowered for token in ("extern", "parceir", "cliente"))


def _build_view_mermaid(
    view: Dict[str, Any],
    view_blueprint: Optional[Dict[str, Any]],
    element_lookup: Dict[str, Dict[str, Any]],
    relation_lookup: Dict[str, Dict[str, Any]],
    blueprint_node_map: Dict[str, Dict[str, Any]],
    blueprint_connection_map: Dict[str, Dict[str, Any]],
    datamodel_node_map: Dict[str, Dict[str, Any]] | None,
    datamodel_connection_map: Dict[str, Dict[str, Any]] | None,
    *,
    prefer_c4: bool = True,
) -> Dict[str, Any]:
    used_aliases: set[str] = set()
    alias_map: Dict[str, str] = {}
    defined_nodes: set[str] = set()
    node_details: List[Dict[str, Any]] = []
    connection_details: List[Dict[str, Any]] = []
    anonymous_counter = itertools.count(1)

    view_id = view.get("id") or (view_blueprint.get("id") if view_blueprint else None)
    view_name = _normalize_text(view.get("name")) or (
        _normalize_text(view_blueprint.get("name")) if view_blueprint else None
    )
    if not view_name:
        view_name = str(view_id) if view_id else "Visão"

    view_documentation = _normalize_text(view.get("documentation"))
    template_view_documentation = (
        _normalize_text(view_blueprint.get("documentation"))
        if view_blueprint
        else None
    )
    template_view_comments = (
        _format_comment_lines(template_view_documentation)
        if template_view_documentation
        else None
    )
    view_comments = (
        _format_comment_lines(view_documentation)
        if view_documentation and view_documentation != template_view_documentation
        else None
    )

    view_kind = _detect_view_kind(view, view_blueprint) if prefer_c4 else None
    use_c4 = bool(view_kind)
    view_alias = _unique_alias(
        _sanitize_mermaid_identifier(str(view_id) if view_id else "view"),
        used_aliases,
    )

    if use_c4:
        header = _c4_header_for_kind(view_kind or "")
        lines: List[str] = [header]
        lines.append(f"    title {_mermaid_escape(view_name)}")
    else:
        lines = ["flowchart TD"]
        lines.append(f"{view_alias}[\"{_mermaid_escape(view_name)}\"]")

    datamodel_node_map = datamodel_node_map or {}
    datamodel_connection_map = datamodel_connection_map or {}

    def _ensure_alias_for_key(key: Optional[str]) -> Optional[str]:
        if not key:
            return None
        if key in alias_map:
            return alias_map[key]
        blueprint_node = blueprint_node_map.get(key)
        if not blueprint_node:
            return None
        alias = _unique_alias(_sanitize_mermaid_identifier(str(key)), used_aliases)
        alias_map[key] = alias
        metadata = _gather_node_metadata(blueprint_node, element_lookup, blueprint_node)
        metadata["alias"] = alias
        metadata["source"] = "template"
        template_doc = metadata.get("template_documentation")
        if template_doc:
            metadata["template_comments"] = _format_comment_lines(template_doc)
        node_doc = metadata.get("documentation")
        if node_doc and node_doc != template_doc:
            metadata["comments"] = _format_comment_lines(node_doc)
        node_details.append(metadata)
        if not use_c4 and alias not in defined_nodes:
            lines.append(f"{alias}[\"{metadata['label']}\"]")
            defined_nodes.add(alias)
        return alias

    def _process_node(
        node: Dict[str, Any],
        parent_alias: Optional[str],
        indent: int,
        context: Dict[str, Any],
    ) -> bool:
        key = _view_node_key(node)
        if not key:
            key = f"anon_{next(anonymous_counter)}"
        alias = alias_map.get(key)
        if not alias:
            alias = _unique_alias(_sanitize_mermaid_identifier(str(key)), used_aliases)
            alias_map[key] = alias

        blueprint_node = blueprint_node_map.get(key)
        metadata = _gather_node_metadata(node, element_lookup, blueprint_node)
        metadata["alias"] = alias
        metadata["source"] = (
            "datamodel" if key in datamodel_node_map else "template"
        )
        metadata["child_count"] = len(_node_children(node))
        template_doc = metadata.get("template_documentation")
        if template_doc:
            metadata["template_comments"] = _format_comment_lines(template_doc)
        node_doc = metadata.get("documentation")
        if node_doc and node_doc != template_doc:
            metadata["comments"] = _format_comment_lines(node_doc)
        node_details.append(metadata)

        if use_c4:
            indent_str = "    " * indent
            node_type = (metadata.get("type") or "").lower()
            title = metadata.get("title") or alias
            if node_type == "label":
                comment = metadata.get("title") or metadata.get("template_label")
                if comment:
                    lines.append(
                        f"{indent_str}{_MERMAID_COMMENT_PREFIX} {_mermaid_escape(comment)}"
                    )
                if metadata.get("documentation"):
                    for comment_line in _format_comment_lines(
                        metadata.get("documentation") or ""
                    ):
                        lines.append(
                            f"{indent_str}{_MERMAID_COMMENT_PREFIX} {comment_line}"
                        )
                produced_child = False
                for child in _node_children(node):
                    if isinstance(child, dict):
                        produced_child = (
                            _process_node(child, alias, indent, dict(context))
                            or produced_child
                        )
                return produced_child

            if node_type == "container":
                boundary_macro = _c4_boundary_macro(view_kind or "")
                boundary_label = metadata.get("title") or metadata.get("template_label")
                boundary_label = boundary_label or str(alias)
                lines.append(
                    f"{indent_str}{boundary_macro}({alias}, \"{_mermaid_escape(boundary_label)}\") {{"
                )
                boundary_index = len(lines) - 1
                next_context = dict(context)
                next_context["external"] = context.get("external", False) or _should_mark_external(
                    boundary_label
                )
                produced_child = False
                for child in _node_children(node):
                    if isinstance(child, dict):
                        produced_child = (
                            _process_node(child, alias, indent + 1, next_context)
                            or produced_child
                        )
                if not produced_child:
                    lines[boundary_index] = (
                        f"{indent_str}{_MERMAID_COMMENT_PREFIX} {_mermaid_escape(boundary_label)}"
                    )
                    return False

                lines.append(f"{indent_str}}}")
                return True

            label = metadata.get("title") or metadata.get("template_label") or str(alias)
            is_external = context.get("external", False) or _should_mark_external(label)
            macro = _c4_element_macro(view_kind or "", is_external)
            technology = _c4_element_technology(
                metadata.get("element_type") or metadata.get("type")
            )
            description = _c4_description(metadata)
            if (view_kind or "") == "context":
                args = _c4_format_arguments(alias, label, description or "")
            else:
                args = _c4_format_arguments(
                    alias,
                    label,
                    technology or "",
                    description or "",
                )
            lines.append(f"{indent_str}{macro}({args})")

            for child in _node_children(node):
                if isinstance(child, dict):
                    _process_node(child, alias, indent + 1, dict(context))
            return True

        if alias not in defined_nodes:
            lines.append(f"{alias}[\"{metadata['label']}\"]")
            defined_nodes.add(alias)

        if parent_alias:
            lines.append(f"{parent_alias} --> {alias}")

        for child in _node_children(node):
            if isinstance(child, dict):
                _process_node(child, alias, indent + 1, dict(context))

        return True

    initial_context: Dict[str, Any] = {"external": False}

    for node in _node_children(view):
        if isinstance(node, dict):
            _process_node(node, view_alias if not use_c4 else None, 1, dict(initial_context))

    for connection in view.get("connections") or []:
        if not isinstance(connection, dict):
            continue
        key = connection.get("id") or connection.get("identifier")
        blueprint_connection = (
            blueprint_connection_map.get(str(key)) if key else None
        )
        metadata = _gather_connection_metadata(
            connection,
            relation_lookup,
            blueprint_connection,
        )
        metadata["source"] = (
            "datamodel" if key and key in datamodel_connection_map else "template"
        )
        template_doc = metadata.get("template_documentation")
        if template_doc:
            metadata["template_comments"] = _format_comment_lines(template_doc)
        conn_doc = metadata.get("documentation")
        if conn_doc and conn_doc != template_doc:
            metadata["comments"] = _format_comment_lines(conn_doc)
        connection_details.append(metadata)

        source_alias = _ensure_alias_for_key(connection.get("source"))
        target_alias = _ensure_alias_for_key(connection.get("target"))
        if connection.get("source") in alias_map:
            source_alias = alias_map[connection.get("source")]
        if connection.get("target") in alias_map:
            target_alias = alias_map[connection.get("target")]

        if not source_alias or not target_alias:
            continue

        if use_c4:
            relation_label = (
                metadata.get("label")
                or metadata.get("type")
                or "Relacionamento"
            )
            relation_doc_raw = metadata.get("documentation") or metadata.get(
                "template_documentation"
            )
            relation_doc = (
                _truncate_text(relation_doc_raw, 160)
                if relation_doc_raw
                else None
            )
            relation_type = metadata.get("type") or None
            args = _c4_format_relation_arguments(
                source_alias,
                target_alias,
                relation_label,
                relation_type,
                relation_doc,
            )
            lines.append(f"    Rel({args})")
        else:
            label = metadata.get("label")
            if label:
                lines.append(
                    f"{source_alias} -->|{_mermaid_escape(label)}| {target_alias}"
                )
            else:
                lines.append(f"{source_alias} --> {target_alias}")


    mermaid_source = _finalize_mermaid_lines(lines)
    _validate_mermaid_syntax(mermaid_source)
    image_payload = _build_mermaid_image_payload(
        mermaid_source,
        alias=view_alias,
        title=view_name,
    )

    return {
        "id": view_id,
        "name": view_name,
        "documentation": view_documentation,
        "template_documentation": template_view_documentation,
        "comments": view_comments,
        "template_comments": template_view_comments,
        "mermaid": mermaid_source,
        "image": image_payload,
        "nodes": node_details,
        "connections": connection_details,
    }


def _content_to_text(content: types.Content | str | bytes) -> str:
    """Converte diferentes formatos de payload textual em string."""
    if isinstance(content, str):
        return content
    if isinstance(content, bytes):
        return content.decode("utf-8")
    if isinstance(content, types.Content):
        texts: list[str] = []
        for part in content.parts:
            text_value = getattr(part, "text", None)
            if text_value:
                texts.append(text_value)
        return "\n".join(texts).strip()
    raise TypeError("Payload recebido não é suportado para conversão em texto.")


def save_datamodel(
    datamodel: types.Content | str | bytes,
    filename: str = DEFAULT_DATAMODEL_FILENAME,
) -> Dict[str, Any]:
    """Persiste o datamodel JSON formatado no diretório `outputs/`.

    Args:
        datamodel: conteúdo JSON produzido pelo agente Diagramador.
        filename: nome do arquivo (apenas nome, sem diretório) para armazenar o datamodel.

    Returns:
        Dicionário com o caminho absoluto salvo, quantidade de elementos e relações e
        os identificadores do modelo.
    """

    raw_text = _content_to_text(datamodel)
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("Falha ao converter datamodel para JSON", exc_info=exc)
        raise ValueError("O conteúdo enviado para `save_datamodel` não é um JSON válido.") from exc

    output_dir = _ensure_output_dir()
    target_path = output_dir / filename
    target_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    elements = payload.get("elements") or []
    relations = payload.get("relations") or []

    logger.info(
        "Datamodel salvo", extra={
            "path": str(target_path.resolve()),
            "elements": len(elements),
            "relations": len(relations),
        }
    )

    return {
        "path": str(target_path.resolve()),
        "element_count": len(elements),
        "relationship_count": len(relations),
        "model_identifier": payload.get("model_identifier"),
        "model_name": payload.get("model_name"),
    }


def finalize_datamodel(
    datamodel: types.Content | str | bytes,
    template_path: str,
    session_state: Optional[MutableMapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Aplica os atributos completos do template a um datamodel aprovado pelo usuário."""

    raw_text = _content_to_text(datamodel)
    try:
        base_payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("Datamodel de entrada inválido para finalização", exc_info=exc)
        raise ValueError("O conteúdo recebido não é um JSON válido.") from exc

    template = _resolve_package_path(Path(template_path))
    if not template.exists():
        raise FileNotFoundError(f"Template não encontrado: {template}")

    blueprint = get_cached_blueprint(session_state, template)
    if blueprint is None:
        blueprint = _parse_template_blueprint(template)
        store_blueprint(session_state, template, blueprint)
    final_payload = copy.deepcopy(blueprint)

    if base_payload.get("model_identifier"):
        final_payload["model_identifier"] = base_payload["model_identifier"]
    if "model_name" in base_payload:
        final_payload["model_name"] = base_payload["model_name"]
    if "model_documentation" in base_payload:
        final_payload["model_documentation"] = base_payload["model_documentation"]

    final_payload["elements"] = _merge_elements(
        blueprint.get("elements", []),
        base_payload.get("elements"),
    )
    final_payload["relations"] = _merge_relations(
        blueprint.get("relations", []),
        base_payload.get("relations"),
    )

    merged_orgs = _merge_organizations(
        blueprint.get("organizations", []),
        base_payload.get("organizations"),
    )
    if merged_orgs:
        final_payload["organizations"] = merged_orgs
    else:
        final_payload.pop("organizations", None)

    if blueprint.get("views") or base_payload.get("views"):
        merged_views = _merge_views(
            blueprint.get("views", {}),
            base_payload.get("views"),
        )
        if merged_views and any(merged_views.get("diagrams", [])):
            final_payload["views"] = merged_views
        elif merged_views and merged_views.get("viewpoints"):
            final_payload["views"] = merged_views
        else:
            final_payload.pop("views", None)

    managed_keys = {
        "model_identifier",
        "model_name",
        "model_documentation",
        "elements",
        "relations",
        "organizations",
        "views",
    }
    for key, value in base_payload.items():
        if key not in managed_keys and key not in final_payload:
            final_payload[key] = value

    final_json = json.dumps(final_payload, indent=2, ensure_ascii=False)
    return {
        "datamodel": copy.deepcopy(final_payload),
        "json": final_json,
        "element_count": len(final_payload.get("elements", [])),
        "relationship_count": len(final_payload.get("relations", [])),
        "view_count": len(
            final_payload.get("views", {}).get("diagrams", [])
            if isinstance(final_payload.get("views"), dict)
            else []
        ),
        "template": str(template.resolve()),
    }


def generate_mermaid_preview(
    datamodel: types.Content | str | bytes,
    template_path: str | None = None,
    *,
    view_identifier: str | None = None,
    view_name: str | None = None,
    view_metadata: Optional[Dict[str, Any]] = None,
    session_state: Optional[MutableMapping[str, Any]] = None,
) -> Dict[str, Any]:
    raw_text = _content_to_text(datamodel)
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("Datamodel inválido para pré-visualização Mermaid", exc_info=exc)
        raise ValueError("O conteúdo enviado não é um JSON válido.") from exc

    template: Dict[str, Any] = {}
    template_metadata: Dict[str, Any] = {}
    if template_path:
        template_file = _resolve_package_path(Path(template_path))
        if not template_file.exists():
            raise FileNotFoundError(f"Template não encontrado: {template_file}")
        template = get_cached_blueprint(session_state, template_file) or _parse_template_blueprint(
            template_file
        )
        store_blueprint(session_state, template_file, template)
        template_metadata["path"] = str(template_file.resolve())

    element_lookup = _build_element_lookup(template, payload)
    relation_lookup = _build_relationship_lookup(template, payload)

    datamodel_views = _normalize_view_diagrams(payload.get("views"))
    if not datamodel_views:
        for extra_key in (
            "view",
            "diagram",
            "view_diagram",
            "diagram_view",
            "selected_view_data",
            "selectedViewData",
        ):
            extra_payload = payload.get(extra_key)
            if extra_payload:
                datamodel_views.extend(_normalize_view_diagrams(extra_payload))
        datamodel_views = _deduplicate_views(datamodel_views)
    for view in datamodel_views:
        _standardize_view_tree(view)
    blueprint_views = _normalize_view_diagrams(template.get("views"))
    for view in blueprint_views:
        _standardize_view_tree(view)

    selectors = _extract_view_selectors(payload)

    if view_identifier:
        selectors.setdefault("ids", set()).add(str(view_identifier))
    if view_name:
        normalized_name = _normalize_text(view_name)
        if normalized_name:
            selectors.setdefault("names", set()).add(normalized_name.lower())
    if view_metadata and isinstance(view_metadata, dict):
        meta_identifier = view_metadata.get("identifier") or view_metadata.get("id")
        if meta_identifier:
            selectors.setdefault("ids", set()).add(str(meta_identifier))
        meta_name = (
            _normalize_text(view_metadata.get("name"))
            or _normalize_text(view_metadata.get("View-Name"))
        )
        if meta_name:
            selectors.setdefault("names", set()).add(meta_name.lower())
    filtered_blueprint = _filter_views_by_selectors(blueprint_views, selectors)
    filtered_datamodel = _filter_views_by_selectors(datamodel_views, selectors)
    if selectors.get("ids") or selectors.get("names"):
        if filtered_blueprint or filtered_datamodel:
            blueprint_views = filtered_blueprint or blueprint_views
            datamodel_views = filtered_datamodel
        else:
            raise ValueError(
                "A visão selecionada não foi encontrada no datamodel nem no template informado."
            )

    def _normalized_view_name(value: Any) -> Optional[str]:
        normalized = _normalize_text(value)
        return normalized.lower() if normalized else None

    blueprint_id_map: Dict[str, Dict[str, Any]] = {}
    blueprint_name_map: Dict[str, Dict[str, Any]] = {}
    for candidate in blueprint_views:
        if not isinstance(candidate, dict):
            continue
        candidate_id = candidate.get("id") or candidate.get("identifier")
        if candidate_id is not None:
            blueprint_id_map[str(candidate_id)] = candidate
        name_key = _normalized_view_name(candidate.get("name"))
        if name_key:
            blueprint_name_map[name_key] = candidate

    def _match_template_view(view_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        identifier = view_payload.get("id") or view_payload.get("identifier")
        if identifier is not None:
            matched = blueprint_id_map.get(str(identifier))
            if matched:
                return matched
        name_key = _normalized_view_name(view_payload.get("name"))
        if name_key:
            return blueprint_name_map.get(name_key)
        return None

    results: List[Dict[str, Any]] = []

    def _flatten_nodes_and_connections(view_payload: Dict[str, Any]) -> Tuple[
        Dict[str, Dict[str, Any]],
        Dict[str, Dict[str, Any]],
    ]:
        return (
            _flatten_view_nodes(view_payload.get("nodes") or []),
            _flatten_view_connections(view_payload.get("connections") or []),
        )

    def _render_view_with_fallback(
        view_payload: Dict[str, Any],
        template_view: Optional[Dict[str, Any]],
        blueprint_nodes: Dict[str, Dict[str, Any]],
        blueprint_connections: Dict[str, Dict[str, Any]],
        datamodel_nodes: Dict[str, Dict[str, Any]] | None,
        datamodel_connections: Dict[str, Dict[str, Any]] | None,
    ) -> Dict[str, Any]:
        try:
            return _build_view_mermaid(
                view_payload,
                template_view,
                element_lookup,
                relation_lookup,
                blueprint_nodes,
                blueprint_connections,
                datamodel_nodes,
                datamodel_connections,
            )
        except ValueError as exc:
            view_name = (
                view_payload.get("name")
                or (template_view or {}).get("name")
                or view_payload.get("id")
                or "visão"
            )
            logger.warning(
                "Falha ao validar Mermaid em estilo C4 para a visão '%s'. "
                "Aplicando fallback para diagrama em fluxo padrão.",
                view_name,
                exc_info=exc,
            )
            return _build_view_mermaid(
                view_payload,
                template_view,
                element_lookup,
                relation_lookup,
                blueprint_nodes,
                blueprint_connections,
                datamodel_nodes,
                datamodel_connections,
                prefer_c4=False,
            )

    if datamodel_views:
        for view in datamodel_views:
            if not isinstance(view, dict):
                continue
            datamodel_nodes, datamodel_connections = _flatten_nodes_and_connections(view)
            template_view = _match_template_view(view)
            if template_view:
                merged_view = _merge_view_diagram(template_view, view)
                _prune_view_to_datamodel(
                    merged_view,
                    datamodel_nodes,
                    datamodel_connections,
                )
                if not merged_view.get("nodes") and view.get("nodes"):
                    merged_view = copy.deepcopy(view)
                blueprint_nodes, blueprint_connections = _flatten_nodes_and_connections(
                    template_view
                )
            else:
                merged_view = copy.deepcopy(view)
                blueprint_nodes, blueprint_connections = {}, {}
            results.append(
                _render_view_with_fallback(
                    merged_view,
                    template_view,
                    blueprint_nodes,
                    blueprint_connections,
                    datamodel_nodes,
                    datamodel_connections,
                )
            )
    else:
        for view in blueprint_views:
            if not isinstance(view, dict):
                continue
            blueprint_nodes, blueprint_connections = _flatten_nodes_and_connections(view)
            results.append(
                _render_view_with_fallback(
                    copy.deepcopy(view),
                    view,
                    blueprint_nodes,
                    blueprint_connections,
                    {},
                    {},
                )
            )

    if not results:
        raise ValueError(
            "Não foi possível identificar visões no datamodel ou no template informado."
        )

    stored_views = [copy.deepcopy(view) for view in results]

    preview_id = uuid.uuid4().hex
    stored_payload: Dict[str, Any] = {
        "preview_id": preview_id,
        "model_identifier": payload.get("model_identifier"),
        "model_name": payload.get("model_name"),
        "model_documentation": payload.get("model_documentation"),
        "element_count": len(payload.get("elements") or []),
        "relationship_count": len(payload.get("relations") or []),
        "view_count": len(stored_views),
        "views": stored_views,
    }
    if template_metadata:
        stored_payload["template"] = copy.deepcopy(template_metadata)

    store_preview(session_state, preview_id, stored_payload)
    _store_preview_fallback(preview_id, stored_payload)

    def _summarize_sources(
        items: Optional[Iterable[Dict[str, Any]]]
    ) -> Dict[str, int]:
        summary = {"datamodel": 0, "template": 0}
        if not items:
            summary["total"] = 0
            return summary
        for item in items:
            if not isinstance(item, dict):
                continue
            source = item.get("source")
            if source == "datamodel":
                summary["datamodel"] += 1
            else:
                summary["template"] += 1
        summary["total"] = summary["datamodel"] + summary["template"]
        return summary

    response_views: List[Dict[str, Any]] = []
    for index, view in enumerate(results):
        nodes_summary = _summarize_sources(view.get("nodes"))
        connections_summary = _summarize_sources(view.get("connections"))
        response_views.append(
            {
                "id": view.get("id"),
                "name": view.get("name"),
                "sources": {
                    "nodes": nodes_summary,
                    "connections": connections_summary,
                },
                "index": index,
                "has_mermaid": bool(view.get("mermaid")),
                "has_image": bool(view.get("image")),
            }
        )

    response: Dict[str, Any] = {
        "status": "ok",
        "preview_id": preview_id,
        "model_identifier": payload.get("model_identifier"),
        "model_name": payload.get("model_name"),
        "model_documentation": payload.get("model_documentation"),
        "element_count": len(payload.get("elements") or []),
        "relationship_count": len(payload.get("relations") or []),
        "view_count": len(response_views),
        "views": response_views,
    }

    if template_metadata:
        response["template"] = template_metadata

    return response


def get_mermaid_preview(
    preview_id: str,
    *,
    include_image: bool = False,
    session_state: Optional[MutableMapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Recupera um preview Mermaid armazenado previamente."""

    if not preview_id:
        raise ValueError("Identificador de preview não informado.")

    preview = get_cached_preview(session_state, preview_id)
    if preview is None:
        preview = _get_preview_fallback(preview_id)
    if preview is None:
        raise ValueError("Preview Mermaid não encontrado para o identificador informado.")

    result = copy.deepcopy(preview)
    if not include_image:
        for view in result.get("views", []):
            if isinstance(view, dict):
                view.pop("image", None)
    return result


def generate_archimate_diagram(
    model_json_path: str,
    output_filename: str = DEFAULT_DIAGRAM_FILENAME,
    template_path: str | None = None,
    validate: bool = True,
    xsd_dir: str | None = None,
) -> Dict[str, Any]:
    """Gera o XML ArchiMate utilizando o template padrão e valida com os XSDs oficiais."""

    model_path = Path(model_json_path)
    if not model_path.is_absolute():
        model_path = Path.cwd() / model_path

    if not model_path.exists():
        raise FileNotFoundError(
            f"Arquivo de datamodel não encontrado: {model_path}"
        )

    template = Path(template_path) if template_path else DEFAULT_TEMPLATE
    template = _resolve_package_path(template)
    if not template.exists():
        raise FileNotFoundError(f"Template ArchiMate não encontrado: {template}")

    output_dir = _ensure_output_dir()
    xml_path = output_dir / output_filename

    logger.info(
        "Gerando diagrama ArchiMate", extra={
            "template": str(template.resolve()),
            "model": str(model_path.resolve()),
            "output": str(xml_path.resolve()),
        }
    )

    xml_exchange.patch_template_with_model(template, model_path, xml_path)

    validation: Dict[str, Any] | None = None
    if validate:
        xsd_dir_path = Path(xsd_dir) if xsd_dir else DEFAULT_XSD_DIR
        xsd_dir_path = _resolve_package_path(xsd_dir_path)
        if not xsd_dir_path.exists():
            raise FileNotFoundError(
                f"Diretório de XSDs não encontrado: {xsd_dir_path}"
            )
        ok, errors = xml_exchange.validate_with_full_xsd(xml_path, xsd_dir_path)
        validation = {"valid": ok, "errors": errors}
        logger.info(
            "Validação XSD executada",
            extra={
                "resultado": "OK" if ok else "FALHOU",
                "erros": len(errors),
                "xsd_dir": str(xsd_dir_path.resolve()),
            },
        )

    return {
        "path": str(xml_path.resolve()),
        "validated": validate,
        "validation_report": validation,
    }


def list_templates(directory: str | None = None) -> Dict[str, Any]:
    """Lista templates ArchiMate disponíveis no diretório informado."""

    templates_dir = _resolve_templates_dir(directory)
    if not templates_dir.exists():
        raise FileNotFoundError(
            f"Diretório de templates não encontrado: {templates_dir}"
        )

    discovered: List[Dict[str, Any]] = []
    for template_path in sorted(templates_dir.rglob("*.xml")):
        try:
            tree = ET.parse(template_path)
            root = tree.getroot()
            ns = {"a": ARCHIMATE_NS}
            name_el = root.find("a:name", ns)
            documentation_el = root.find("a:documentation", ns)
            metadata = {
                "path": str(template_path.resolve()),
                "relative_path": str(template_path.relative_to(templates_dir)),
                "model_identifier": root.get("identifier"),
                "model_name": _text_payload(name_el),
                "documentation": _text_payload(documentation_el),
            }
            discovered.append(metadata)
        except ET.ParseError:
            logger.warning("Template inválido ignorado", extra={"path": str(template_path)})
            continue

    return {
        "directory": str(templates_dir.resolve()),
        "count": len(discovered),
        "templates": discovered,
    }


def describe_template(
    template_path: str,
    session_state: Optional[MutableMapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Retorna a estrutura detalhada de um template ArchiMate."""

    template = _resolve_package_path(Path(template_path))

    if not template.exists():
        raise FileNotFoundError(f"Template não encontrado: {template}")

    blueprint = _parse_template_blueprint(template)
    store_blueprint(session_state, template, blueprint)
    guidance = _build_guidance_from_blueprint(blueprint)
    guidance["model"]["path"] = str(template.resolve())
    return guidance
__all__ = [
    "list_templates",
    "describe_template",
    "generate_mermaid_preview",
    "get_mermaid_preview",
    "finalize_datamodel",
    "save_datamodel",
    "generate_archimate_diagram",
]
