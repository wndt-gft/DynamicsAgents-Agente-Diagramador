"""Agente Diagramador responsável por gerar datamodels e diagramas ArchiMate."""

from __future__ import annotations

"""Operações principais do agente Diagramador."""

import base64
import copy
import html
import itertools
import json
import logging
import mimetypes
import re
import textwrap
import unicodedata
import warnings
from pathlib import Path
from collections.abc import Iterable, MutableMapping, Sequence
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from google.genai import types

from ..archimate_exchange import xml_exchange

from .constants import (
    ARCHIMATE_NS,
    DEFAULT_DATAMODEL_FILENAME,
    DEFAULT_DIAGRAM_FILENAME,
    DEFAULT_TEMPLATE,
    DEFAULT_TEMPLATES_DIR,
    DEFAULT_XSD_DIR,
    OUTPUT_DIR,
    XML_LANG_ATTR,
    XSI_ATTR,
)
from .rendering import render_view_layout
from .session import (
    get_cached_artifact,
    get_cached_blueprint,
    get_session_bucket,
    get_view_focus,
    set_view_focus,
    store_artifact,
    store_blueprint,
)

warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")

logger = logging.getLogger(__name__)


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


SESSION_ARTIFACT_TEMPLATE_LISTING = "template_listing"
SESSION_ARTIFACT_TEMPLATE_GUIDANCE = "template_guidance"
SESSION_ARTIFACT_FINAL_DATAMODEL = "final_datamodel"
SESSION_ARTIFACT_LAYOUT_PREVIEW = "layout_preview"
SESSION_ARTIFACT_SAVED_DATAMODEL = "saved_datamodel"
SESSION_ARTIFACT_ARCHIMATE_XML = "archimate_xml"


def _error_response(message: str, *, code: str | None = None) -> Dict[str, Any]:
    """Padroniza respostas de erro para tools."""

    payload: Dict[str, Any] = {"status": "error", "message": message}
    if code:
        payload["code"] = code
    return payload


def _placeholder_token(value: str, fallback: str = "preview") -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value).strip())
    token = token.strip("-")
    return token or fallback


def _state_var_token(value: str, fallback: str = "preview") -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip())
    token = token.strip("_")
    return token or fallback


_CONTROL_CHAR_CLEAN_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
_INVALID_ESCAPE_RE = re.compile(r"(?<!\\)\\([^\"\\/bfnrtu])")
_MISSING_COMMA_RE = re.compile(r'([}\]])(\s*)(?=[{\[\"])', re.MULTILINE)
_MISSING_COMMA_BETWEEN_PAIRS_RE = re.compile(
    r'([}\]"0-9])(?P<ws>\s*)(?="[^"\\]+"\s*:)',
    re.MULTILINE,
)
_MISSING_COMMA_GENERIC_RE = re.compile(
    r'([}\]"0-9])(?P<ws>\s*)(?=[{\["0-9-])',
    re.MULTILINE,
)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
_TOKEN_SPLIT_RE = re.compile(r"[\s\-–—:/|]+")


_CODE_FENCE_RE = re.compile(
    r"^\s*(?:```|~~~)(?:json)?\s*(?P<body>.*?)(?:```|~~~)\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _strip_code_fences(text: str) -> str:
    """Remove cercas de bloco (```/~~~) frequentemente usadas pelo modelo."""

    match = _CODE_FENCE_RE.match(text)
    if match:
        return match.group("body").strip()
    return text


def _guess_mime_type(path: Path | None, fallback: str | None = None) -> str:
    if path is not None:
        mime_type, _ = mimetypes.guess_type(str(path), strict=False)
        if mime_type:
            return mime_type
        suffix = path.suffix.lower()
        if suffix == ".svg":
            return "image/svg+xml"
        if suffix == ".png":
            return "image/png"
    if fallback:
        return fallback
    return "application/octet-stream"


def _ensure_data_uri(path_text: str | None, *, mime_hint: str | None = None) -> Optional[str]:
    if not isinstance(path_text, str) or not path_text.strip():
        return None
    if path_text.strip().startswith("data:"):
        return path_text.strip()
    candidate = Path(path_text.strip())
    try:
        if not candidate.exists():
            return None
        payload = candidate.read_bytes()
    except OSError:
        return None
    mime_type = _guess_mime_type(candidate, fallback=mime_hint)
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _build_image_html(data_uri: Optional[str], alt_text: Optional[str]) -> Optional[str]:
    if not data_uri:
        return None
    safe_alt = html.escape(alt_text or "Pré-visualização", quote=True)
    return f'<img src="{data_uri}" alt="{safe_alt}">'


def _build_link_html(data_uri: Optional[str], label: Optional[str] = None) -> Optional[str]:
    if not data_uri:
        return None
    safe_label = html.escape(label or "Abrir diagrama em SVG", quote=False)
    return f'<a href="{data_uri}" target="_blank" rel="noopener">{safe_label}</a>'


def _normalized_template_path(path: Path) -> str:
    if path.is_absolute():
        return str(path.resolve())
    return str((Path.cwd() / path).resolve())


def _template_view_lookup(
    session_state: Optional[MutableMapping[str, Any]], template_path: Path
) -> Dict[str, Dict[str, Any]]:
    """Gera um mapa id->metadados da visão conforme ``list_templates``."""

    listing = get_cached_artifact(session_state, SESSION_ARTIFACT_TEMPLATE_LISTING)
    if not isinstance(listing, MutableMapping):
        return {}

    normalized_template = _normalized_template_path(template_path)
    templates = listing.get("templates")
    if not isinstance(templates, Sequence):
        return {}

    view_names: Dict[str, Dict[str, Any]] = {}

    for entry in templates:
        if not isinstance(entry, MutableMapping):
            continue
        path_text = entry.get("path") or entry.get("absolute_path")
        if not isinstance(path_text, str) or not path_text.strip():
            continue
        try:
            candidate = Path(path_text)
        except Exception:
            continue
        if _normalized_template_path(candidate) != normalized_template:
            continue
        views = entry.get("views")
        if not isinstance(views, Sequence):
            continue
        for index, view in enumerate(views):
            if not isinstance(view, MutableMapping):
                continue
            identifier = view.get("identifier") or view.get("id")
            name = view.get("name")
            if not isinstance(identifier, str) or not identifier.strip():
                continue
            normalized_identifier = identifier.strip()
            entry_payload: Dict[str, Any] = {}
            if isinstance(name, str) and name.strip():
                entry_payload["name"] = name.strip()
            entry_payload["index"] = index
            documentation = view.get("documentation")
            if isinstance(documentation, str) and documentation.strip():
                entry_payload["documentation"] = documentation.strip()
            view_names[normalized_identifier] = entry_payload
    return view_names


def _view_lookup_details(entry: Any) -> tuple[Optional[str], Optional[int]]:
    if isinstance(entry, MutableMapping):
        name = entry.get("name")
        index = entry.get("index")
        return (
            name.strip() if isinstance(name, str) and name.strip() else None,
            int(index) if isinstance(index, int) else None,
        )
    if isinstance(entry, str) and entry.strip():
        return (entry.strip(), None)
    return (None, None)


def _populate_preview_assets(
    view_payload: MutableMapping[str, Any], preview: MutableMapping[str, Any]
) -> None:
    """Garante que o preview contenha data URIs e HTML prontos para substituição."""

    view_name = str(view_payload.get("name") or view_payload.get("id") or "Visão")

    svg_path = preview.get("local_path")
    svg_data_uri = _ensure_data_uri(svg_path, mime_hint="image/svg+xml")
    if not svg_data_uri:
        svg_data_uri = _ensure_data_uri(preview.get("download_path"), mime_hint="image/svg+xml")
    if not svg_data_uri:
        svg_data_uri = preview.get("download_uri") if isinstance(preview.get("download_uri"), str) else None
        if isinstance(svg_data_uri, str) and svg_data_uri.startswith("data:"):
            svg_data_uri = svg_data_uri
        else:
            svg_data_uri = None

    png_payload = preview.get("png")
    png_data_uri: Optional[str] = None
    if isinstance(png_payload, MutableMapping):
        png_data_uri = _ensure_data_uri(png_payload.get("local_path"), mime_hint="image/png")
        if not png_data_uri:
            png_uri = png_payload.get("uri")
            if isinstance(png_uri, str) and png_uri.strip().startswith("data:"):
                png_data_uri = png_uri.strip()
        if png_data_uri:
            png_payload.setdefault("data_uri", png_data_uri)

    if not png_data_uri:
        inline_uri = preview.get("inline_uri")
        if isinstance(inline_uri, str) and inline_uri.strip().startswith("data:image/png"):
            png_data_uri = inline_uri.strip()

    if not png_data_uri and svg_data_uri:
        png_data_uri = svg_data_uri

    if svg_data_uri:
        preview.setdefault("download_data_uri", svg_data_uri)
        preview.setdefault("download_html", _build_link_html(svg_data_uri, "Abrir diagrama em SVG"))

    if png_data_uri:
        preview.setdefault("inline_data_uri", png_data_uri)
        preview.setdefault("inline_html", _build_image_html(png_data_uri, view_name))

    if isinstance(png_payload, MutableMapping) and png_data_uri:
        png_payload.setdefault("inline_data_uri", png_data_uri)
        png_payload.setdefault("inline_html", _build_image_html(png_data_uri, view_name))
        if svg_data_uri:
            png_payload.setdefault("download_data_uri", svg_data_uri)
            png_payload.setdefault("download_html", _build_link_html(svg_data_uri, "Abrir diagrama em SVG"))

    if svg_data_uri and not preview.get("download_uri"):
        preview["download_uri"] = svg_data_uri

def _safe_json_loads(raw_text: str) -> Any:
    """Parse JSON tolerating minor formatting issues produced by the LLM."""

    if not isinstance(raw_text, str):
        raise TypeError("Esperado texto JSON para parsing.")

    stripped = _strip_code_fences(raw_text.strip())
    if not stripped:
        raise ValueError("Conteúdo JSON vazio.")

    last_error: json.JSONDecodeError | None = None

    def _attempt_load(payload: str, *, strict: bool = True) -> Any | None:
        nonlocal last_error
        try:
            return json.loads(payload, strict=strict)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            last_error = exc
            return None

    # First attempt with the original payload for proper errors if already valid.
    loaded = _attempt_load(stripped)
    if loaded is not None:
        return loaded

    # Remove ASCII control characters that aren't valid in JSON.
    sanitized = _CONTROL_CHAR_CLEAN_RE.sub("", stripped)
    if sanitized != stripped:
        loaded = _attempt_load(sanitized)
        if loaded is not None:
            return loaded
    else:
        sanitized = stripped

    # Repair invalid escape sequences like Windows paths ("\folder\file").
    def _fix_invalid_escape(match: re.Match[str]) -> str:
        tail = match.group(1)
        if tail is None:
            return "\\\\"
        return "\\\\" + tail

    repaired = _INVALID_ESCAPE_RE.sub(_fix_invalid_escape, sanitized)
    if repaired != sanitized:
        loaded = _attempt_load(repaired)
        if loaded is not None:
            return loaded
    else:
        repaired = sanitized

    # Remove trailing commas that o modelo pode inserir antes de chaves/colchetes.
    relaxed = _TRAILING_COMMA_RE.sub(r"\1", repaired)
    if relaxed != repaired:
        loaded = _attempt_load(relaxed, strict=False)
        if loaded is not None:
            return loaded
    else:
        relaxed = repaired

    # Corrige casos comuns de vírgula ausente entre blocos ``}{`` ou ``]{``.
    patched = _MISSING_COMMA_RE.sub(r"\1,\2", relaxed)
    if patched != relaxed:
        loaded = _attempt_load(patched, strict=False)
        if loaded is not None:
            return loaded
    else:
        patched = relaxed

    advanced = _MISSING_COMMA_BETWEEN_PAIRS_RE.sub(r"\1,\g<ws>", patched)
    if advanced != patched:
        loaded = _attempt_load(advanced, strict=False)
        if loaded is not None:
            return loaded
    else:
        advanced = patched

    generic = _MISSING_COMMA_GENERIC_RE.sub(r"\1,\g<ws>", advanced)
    if generic != advanced:
        loaded = _attempt_load(generic, strict=False)
        if loaded is not None:
            return loaded
    else:
        generic = advanced

    # Tentativa final com verificação flexível; se falhar, propaga o último erro.
    loaded = _attempt_load(generic, strict=False)
    if loaded is not None:
        return loaded

    assert last_error is not None
    raise last_error

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


def _escape_label_text(value: str) -> str:
    """Normaliza rótulos multiline para consumo em metadados e pré-visualizações."""

    sanitized = value.replace("\\", "\\\\").replace("\r", "\n")
    sanitized = sanitized.replace("\"", "\\\"")
    sanitized = sanitized.replace("\n", "<br/>")
    return sanitized


def _sanitize_identifier(identifier: str, fallback: str = "node") -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in identifier)
    cleaned = cleaned.strip("_")
    if not cleaned:
        cleaned = fallback
    if cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return cleaned


def _resolve_templates_dir(directory: str | None = None) -> Path:
    """Resolves the directory that stores template XML files."""

    base = Path(directory) if directory else DEFAULT_TEMPLATES_DIR
    return _resolve_package_path(base)


_BREAK_TAG_PATTERN = re.compile(r"<\s*/?\s*br\s*/?\s*>", re.IGNORECASE)
_INLINE_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
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


def _escape_label_text(value: str) -> str:
    sanitized = value.replace("\\", "\\\\").replace("\r", "\n")
    sanitized = sanitized.replace("\"", "\\\"")
    sanitized = sanitized.replace("\n", "<br/>")
    return sanitized


def _sanitize_identifier(identifier: str, fallback: str = "node") -> str:
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
    overrides = list(override_nodes or [])
    if not template_nodes and not overrides:
        return []

    override_map: Dict[str, Dict[str, Any]] = {}
    extras: List[Dict[str, Any]] = []
    for node in overrides:
        clean = _strip_template_keys(node) or {}
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

    merged.extend(copy.deepcopy(extra) for extra in extras)
    return merged


def _merge_view_node(template_node: Dict[str, Any], override_node: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = copy.deepcopy(template_node)
    clean_override = copy.deepcopy(override_node) if override_node else None
    if clean_override:
        _apply_textual_override(merged, clean_override, "label", ("label", "label_hint"))
        _apply_textual_override(merged, clean_override, "documentation", ("documentation", "documentation_hint"))

    template_children = template_node.get("nodes", [])
    override_children = clean_override.get("nodes") if clean_override else None
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


def _normalize_view_diagrams(views_payload: Any) -> List[Dict[str, Any]]:
    if views_payload is None:
        return []
    if isinstance(views_payload, dict):
        diagrams = views_payload.get("diagrams")
        return diagrams if isinstance(diagrams, list) else []
    if isinstance(views_payload, list):
        return views_payload
    return []


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


def _flatten_view_nodes(nodes: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    flattened: Dict[str, Dict[str, Any]] = {}

    def _walk(items: Iterable[Dict[str, Any]]) -> None:
        for node in items or []:
            if not isinstance(node, dict):
                continue
            key = _view_node_key(node)
            if key:
                flattened[key] = node
            child_nodes = node.get("nodes")
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


def _merge_node_documentation(
    node: Dict[str, Any],
    blueprint_node: Optional[Dict[str, Any]],
) -> Tuple[Optional[str], Optional[str]]:
    node_doc = _normalize_text(node.get("documentation"))
    blueprint_doc = _normalize_text(
        blueprint_node.get("documentation") if blueprint_node else None
    )
    return node_doc, blueprint_doc


def _merge_styles(
    base: Optional[Dict[str, Any]],
    override: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not base and not override:
        return None

    merged: Dict[str, Any] = {}

    if isinstance(base, dict):
        for key, value in base.items():
            merged[key] = copy.deepcopy(value)

    if isinstance(override, dict):
        for key, value in override.items():
            if isinstance(value, dict):
                existing = merged.get(key)
                nested_base = existing if isinstance(existing, dict) else None
                nested_merged = _merge_styles(nested_base, value)
                if nested_merged is not None:
                    merged[key] = nested_merged
            elif value is not None:
                merged[key] = value

    return merged or None


def _resolve_bounds(
    node: Optional[Dict[str, Any]],
    blueprint_node: Optional[Dict[str, Any]],
) -> Optional[Dict[str, float]]:
    candidates: List[Dict[str, Any]] = []
    if isinstance(node, dict):
        candidates.append(node)
    if isinstance(blueprint_node, dict):
        candidates.append(blueprint_node)

    for candidate in candidates:
        bounds = candidate.get("bounds")
        if not isinstance(bounds, dict):
            continue
        try:
            x = float(bounds["x"])
            y = float(bounds["y"])
            w = float(bounds["w"])
            h = float(bounds["h"])
        except (KeyError, TypeError, ValueError):
            continue
        return {"x": x, "y": y, "w": w, "h": h}

    return None


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

    label_parts = [_escape_label_text(title)]
    if node_type:
        label_parts.append(_escape_label_text(f"Tipo: {node_type}"))
    if doc_snippet:
        label_parts.append(_escape_label_text(f"Nota: {doc_snippet}"))

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

    relation_label = " - ".join(part for part in label_parts if part)

    metadata: Dict[str, Any] = {
        "id": identifier,
        "label": relation_label,
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


def _build_view_preview(
    view: Dict[str, Any],
    view_blueprint: Optional[Dict[str, Any]],
    element_lookup: Dict[str, Dict[str, Any]],
    relation_lookup: Dict[str, Dict[str, Any]],
    blueprint_node_map: Dict[str, Dict[str, Any]],
    blueprint_connection_map: Dict[str, Dict[str, Any]],
    datamodel_node_map: Dict[str, Dict[str, Any]] | None,
    datamodel_connection_map: Dict[str, Dict[str, Any]] | None,
) -> Dict[str, Any]:
    used_aliases: set[str] = set()
    alias_map: Dict[str, str] = {}
    node_details: List[Dict[str, Any]] = []
    connection_details: List[Dict[str, Any]] = []
    layout_nodes: Dict[str, Dict[str, Any]] = {}
    layout_connections: Dict[str, Dict[str, Any]] = {}
    anonymous_counter = itertools.count(1)

    view_id = view.get("id") or (view_blueprint.get("id") if view_blueprint else None)
    view_alias = _unique_alias(
        _sanitize_identifier(str(view_id) if view_id else "view"),
        used_aliases,
    )

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

    datamodel_node_map = datamodel_node_map or {}
    datamodel_connection_map = datamodel_connection_map or {}

    def _register_layout_node(
        metadata: Dict[str, Any],
        *,
        node_data: Optional[Dict[str, Any]],
        blueprint_node: Optional[Dict[str, Any]],
    ) -> None:
        bounds = _resolve_bounds(node_data, blueprint_node)
        if bounds:
            metadata["bounds"] = bounds
        style = _merge_styles(
            blueprint_node.get("style") if isinstance(blueprint_node, dict) else None,
            node_data.get("style") if isinstance(node_data, dict) else None,
        )
        if style:
            metadata["style"] = style
        node_key = metadata.get("key")
        if not node_key and isinstance(node_data, dict):
            node_key = _view_node_key(node_data)
        if not node_key and isinstance(blueprint_node, dict):
            node_key = _view_node_key(blueprint_node)
        if node_key:
            metadata.setdefault("key", node_key)
        alias = metadata.get("alias")
        entry_key = metadata.get("id") or metadata.get("key") or alias
        entry = {
            "id": metadata.get("id") or metadata.get("key") or alias,
            "alias": alias,
            "key": metadata.get("key"),
            "title": metadata.get("title"),
            "label": metadata.get("label"),
            "type": metadata.get("type"),
            "element_type": metadata.get("element_type"),
            "element_name": metadata.get("element_name"),
            "bounds": bounds,
            "style": style,
            "element_ref": metadata.get("element_ref"),
            "relationship_ref": metadata.get("relationship_ref"),
            "view_ref": metadata.get("view_ref"),
            "source": metadata.get("source"),
            "documentation": metadata.get("documentation"),
            "template_documentation": metadata.get("template_documentation"),
        }
        if entry_key:
            layout_nodes[str(entry_key)] = entry
        elif alias:
            layout_nodes[str(alias)] = entry

    def _ensure_alias_for_key(key: Optional[str]) -> Optional[str]:
        if not key:
            return None
        if key in alias_map:
            return alias_map[key]
        blueprint_node = blueprint_node_map.get(key)
        if not blueprint_node:
            return None
        alias = _unique_alias(_sanitize_identifier(str(key)), used_aliases)
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
        _register_layout_node(metadata, node_data=None, blueprint_node=blueprint_node)
        return alias

    def _process_node(node: Dict[str, Any], parent_alias: Optional[str]) -> None:
        key = _view_node_key(node)
        if not key:
            key = f"anon_{next(anonymous_counter)}"
        alias = alias_map.get(key)
        if not alias:
            alias = _unique_alias(_sanitize_identifier(str(key)), used_aliases)
            alias_map[key] = alias

        blueprint_node = blueprint_node_map.get(key)
        metadata = _gather_node_metadata(node, element_lookup, blueprint_node)
        metadata["alias"] = alias
        metadata["source"] = (
            "datamodel" if key in datamodel_node_map else "template"
        )
        metadata["child_count"] = len(node.get("nodes") or [])
        template_doc = metadata.get("template_documentation")
        if template_doc:
            metadata["template_comments"] = _format_comment_lines(template_doc)
        node_doc = metadata.get("documentation")
        if node_doc and node_doc != template_doc:
            metadata["comments"] = _format_comment_lines(node_doc)
        node_details.append(metadata)
        _register_layout_node(metadata, node_data=node, blueprint_node=blueprint_node)

        for child in node.get("nodes") or []:
            if isinstance(child, dict):
                _process_node(child, alias)

    for node in view.get("nodes") or []:
        if isinstance(node, dict):
            _process_node(node, view_alias)

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

        connection_style = _merge_styles(
            blueprint_connection.get("style") if isinstance(blueprint_connection, dict) else None,
            connection.get("style") if isinstance(connection.get("style"), dict) else None,
        )
        if connection_style:
            metadata["style"] = connection_style
        points = connection.get("points") or (
            blueprint_connection.get("points") if isinstance(blueprint_connection, dict) else None
        )
        if points:
            metadata["points"] = points
        layout_key = metadata.get("id") or key or f"conn_{len(layout_connections) + 1}"
        layout_connections[str(layout_key)] = {
            "id": metadata.get("id") or key,
            "label": metadata.get("label"),
            "relationship_ref": metadata.get("relationship_ref"),
            "source": connection.get("source") or metadata.get("source"),
            "target": connection.get("target") or metadata.get("target"),
            "source_alias": source_alias,
            "target_alias": target_alias,
            "style": metadata.get("style"),
            "points": metadata.get("points"),
            "documentation": metadata.get("documentation"),
            "template_documentation": metadata.get("template_documentation"),
        }

    return {
        "id": view_id,
        "name": view_name,
        "documentation": view_documentation,
        "template_documentation": template_view_documentation,
        "comments": view_comments,
        "template_comments": template_view_comments,
        "alias": view_alias,
        "nodes": node_details,
        "connections": connection_details,
        "layout": {
            "nodes": list(layout_nodes.values()),
            "connections": list(layout_connections.values()),
        },
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
    datamodel: types.Content | str | bytes | None,
    filename: str = DEFAULT_DATAMODEL_FILENAME,
    session_state: MutableMapping | None = None,
) -> Dict[str, Any]:
    """Persiste o datamodel JSON formatado no diretório `outputs/`.

    Args:
        datamodel: conteúdo JSON produzido pelo agente Diagramador.
        filename: nome do arquivo (apenas nome, sem diretório) para armazenar o datamodel.

    Returns:
        Dicionário com o caminho absoluto salvo, quantidade de elementos e relações e
        os identificadores do modelo.
    """

    raw_text: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None

    if datamodel is not None:
        raw_text = _content_to_text(datamodel)
        try:
            payload = _safe_json_loads(raw_text)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.error("Falha ao converter datamodel para JSON", exc_info=exc)
            raise ValueError(
                "O conteúdo enviado para `save_datamodel` não é um JSON válido."
            ) from exc
    elif session_state is not None:
        cached = get_cached_artifact(session_state, SESSION_ARTIFACT_FINAL_DATAMODEL)
        if isinstance(cached, MutableMapping):
            source_payload = cached.get("source")
            if isinstance(source_payload, MutableMapping):
                payload = copy.deepcopy(source_payload)
                source_json = cached.get("source_json")
                raw_text = source_json if isinstance(source_json, str) else None
                if raw_text is None:
                    raw_text = json.dumps(payload, indent=2, ensure_ascii=False)
            else:
                payload = copy.deepcopy(cached.get("datamodel"))
                if payload is None and cached.get("json"):
                    try:
                        payload = _safe_json_loads(str(cached["json"]))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        payload = None
                if payload is not None:
                    raw_text = json.dumps(payload, indent=2, ensure_ascii=False)

    if payload is None or raw_text is None:
        raise ValueError(
            "Não foi possível localizar um datamodel válido para salvar; informe o conteúdo ou utilize `finalize_datamodel` antes."
        )

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

    artifact = {
        "path": str(target_path.resolve()),
        "element_count": len(elements),
        "relationship_count": len(relations),
        "model_identifier": payload.get("model_identifier"),
        "model_name": payload.get("model_name"),
    }

    if session_state is not None:
        store_artifact(
            session_state,
            SESSION_ARTIFACT_SAVED_DATAMODEL,
            artifact,
        )
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_SAVED_DATAMODEL,
            "path": artifact["path"],
        }

    return artifact


def finalize_datamodel(
    datamodel: types.Content | str | bytes,
    template_path: str,
    session_state: MutableMapping | None = None,
) -> Dict[str, Any]:
    """Aplica os atributos completos do template a um datamodel aprovado pelo usuário."""

    raw_text = _content_to_text(datamodel)
    try:
        base_payload = _safe_json_loads(raw_text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
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
    artifact = {
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
        "source": copy.deepcopy(base_payload),
        "source_json": raw_text,
    }

    if session_state is not None:
        generate_layout_preview(
            final_json,
            str(template),
            session_state=session_state,
        )
        store_artifact(
            session_state,
            SESSION_ARTIFACT_FINAL_DATAMODEL,
            artifact,
        )
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_FINAL_DATAMODEL,
            "element_count": artifact["element_count"],
            "relationship_count": artifact["relationship_count"],
            "view_count": artifact["view_count"],
        }

    return artifact


def _normalize_view_filter(view_filter: object) -> set[str]:
    """Normaliza diferentes formatos de filtro de visão para um conjunto comparável."""

    if not view_filter:
        return set()

    normalized: set[str] = set()

    def _register(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, (str, bytes)):
            text = value.decode("utf-8") if isinstance(value, bytes) else value
        else:
            text = str(value)
        text = text.strip()
        if not text:
            return
        normalized.add(text.casefold())

    if isinstance(view_filter, (str, bytes)):
        raw_text = view_filter.decode("utf-8") if isinstance(view_filter, bytes) else view_filter
        stripped = raw_text.strip()
        if not stripped:
            return set()
        try:
            parsed = json.loads(stripped)
        except (TypeError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, (list, tuple, set)):
            for item in parsed:
                if isinstance(item, MutableMapping):
                    for key in ("id", "identifier", "name", "alias"):
                        _register(item.get(key))
                else:
                    _register(item)
            return normalized
        if isinstance(parsed, MutableMapping):
            for key in ("id", "identifier", "name", "alias"):
                _register(parsed.get(key))
            if normalized:
                return normalized
        for token in re.split(r"[\s,;\n]+", stripped):
            _register(token)
        return normalized

    if isinstance(view_filter, Iterable) and not isinstance(view_filter, (str, bytes, MutableMapping)):
        for item in view_filter:
            if isinstance(item, MutableMapping):
                for key in ("id", "identifier", "name", "alias"):
                    _register(item.get(key))
            else:
                _register(item)
        return normalized

    if isinstance(view_filter, MutableMapping):
        for key in ("id", "identifier", "name", "alias"):
            _register(view_filter.get(key))
    else:
        _register(view_filter)

    return normalized


def _view_token_candidates(source: Optional[Dict[str, Any]]) -> set[str]:
    tokens: set[str] = set()
    if not isinstance(source, dict):
        return tokens
    for key in ("id", "identifier", "name", "alias"):
        value = source.get(key)
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                normalized = unicodedata.normalize("NFKC", candidate)

                def _register(token_value: str) -> None:
                    trimmed = token_value.strip()
                    if not trimmed:
                        return
                    tokens.add(trimmed.casefold())
                    ascii_variant = unicodedata.normalize("NFD", trimmed)
                    ascii_variant = "".join(
                        ch for ch in ascii_variant if not unicodedata.combining(ch)
                    )
                    ascii_variant = unicodedata.normalize("NFC", ascii_variant).strip()
                    if ascii_variant:
                        tokens.add(ascii_variant.casefold())

                _register(normalized)
                for fragment in _TOKEN_SPLIT_RE.split(normalized):
                    if fragment and len(fragment) >= 2:
                        _register(fragment)
    return tokens


def _session_view_filter(session_state: MutableMapping | None) -> set[str]:
    return {token for token in get_view_focus(session_state) if token}


def _view_matches_filter(
    view: Optional[Dict[str, Any]],
    blueprint_view: Optional[Dict[str, Any]],
    view_filter: set[str],
) -> bool:
    if not view_filter:
        return True

    tokens = _view_token_candidates(view)
    tokens.update(_view_token_candidates(blueprint_view))
    return bool(tokens & view_filter)


def _view_summary_matches_filter(
    summary: MutableMapping[str, Any] | None,
    view_filter: set[str],
) -> bool:
    if not view_filter:
        return True

    if not isinstance(summary, MutableMapping):
        return False

    candidates: Dict[str, Any] = {}
    for key in ("id", "identifier"):
        if key not in candidates:
            candidates[key] = summary.get("view_id")
    if "name" not in candidates:
        candidates["name"] = summary.get("view_name")

    tokens = _view_token_candidates(candidates)
    return bool(tokens & view_filter)


def _build_preview_variant(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, MutableMapping):
        return None

    variant: Dict[str, Any] = {}
    format_hint = payload.get("format")
    if isinstance(format_hint, str):
        variant["format"] = format_hint

    inline_markdown = payload.get("inline_markdown")
    if isinstance(inline_markdown, str) and inline_markdown.strip():
        variant["inline_markdown"] = inline_markdown

    inline_uri = payload.get("inline_uri")
    if isinstance(inline_uri, str) and inline_uri.strip():
        variant["inline_uri"] = inline_uri.strip()

    inline_data_uri = payload.get("inline_data_uri")
    if isinstance(inline_data_uri, str) and inline_data_uri.strip():
        variant["inline_data_uri"] = inline_data_uri.strip()

    inline_html = payload.get("inline_html")
    if isinstance(inline_html, str) and inline_html.strip():
        variant["inline_html"] = inline_html.strip()

    download_uri = payload.get("download_uri")
    if isinstance(download_uri, str) and download_uri.strip():
        variant["download_uri"] = download_uri
        download_markdown = payload.get("download_markdown")
        if not isinstance(download_markdown, str) or not download_markdown.strip():
            label = payload.get("format")
            label_text = str(label).upper() if label else "PREVIEW"
            download_markdown = f"[Baixar {label_text}]({download_uri})"
        variant["download_markdown"] = download_markdown

    download_data_uri = payload.get("download_data_uri")
    if isinstance(download_data_uri, str) and download_data_uri.strip():
        variant["download_data_uri"] = download_data_uri.strip()

    download_html = payload.get("download_html")
    if isinstance(download_html, str) and download_html.strip():
        variant["download_html"] = download_html.strip()

    local_path = payload.get("local_path")
    if isinstance(local_path, str) and local_path.strip():
        variant["local_path"] = local_path.strip()

    artifact_payload = payload.get("artifact")
    if isinstance(artifact_payload, MutableMapping):
        variant["artifact"] = dict(artifact_payload)

    placeholder_source: Optional[str] = None
    if isinstance(local_path, str) and local_path.strip():
        placeholder_source = Path(local_path).name
    elif isinstance(artifact_payload, MutableMapping):
        candidate_name = artifact_payload.get("filename") or artifact_payload.get("name")
        if isinstance(candidate_name, str) and candidate_name.strip():
            placeholder_source = candidate_name

    if placeholder_source:
        token_base = _placeholder_token(placeholder_source, fallback="preview").lower()
        state_var_base = _state_var_token(f"diagramador_{token_base}", fallback="diagramador_preview")
        legacy_placeholders = {
            "link": f"{{diagramador:{token_base}:link}}",
            "image": f"{{diagramador:{token_base}:img}}",
            "img": f"{{diagramador:{token_base}:img}}",
            "path": f"{{diagramador:{token_base}:path}}",
            "uri": f"{{diagramador:{token_base}:uri}}",
            "url": f"{{diagramador:{token_base}:uri}}",
            "markdown_link": f"{{diagramador:{token_base}:markdown_link}}",
            "relative_path": f"{{diagramador:{token_base}:relative_path}}",
            "filename": f"{{diagramador:{token_base}:filename}}",
        }
        state_placeholders = {
            "link": f"{{state.{state_var_base}_link}}",
            "image": f"{{state.{state_var_base}_image}}",
            "img": f"{{state.{state_var_base}_img}}",
            "path": f"{{state.{state_var_base}_path}}",
            "uri": f"{{state.{state_var_base}_uri}}",
            "url": f"{{state.{state_var_base}_url}}",
            "markdown_link": f"{{state.{state_var_base}_markdown_link}}",
            "relative_path": f"{{state.{state_var_base}_relative_path}}",
            "filename": f"{{state.{state_var_base}_filename}}",
        }
        bare_placeholders = {
            "link": f"{{{state_var_base}_link}}",
            "image": f"{{{state_var_base}_image}}",
            "img": f"{{{state_var_base}_img}}",
            "path": f"{{{state_var_base}_path}}",
            "uri": f"{{{state_var_base}_uri}}",
            "url": f"{{{state_var_base}_url}}",
            "markdown_link": f"{{{state_var_base}_markdown_link}}",
            "relative_path": f"{{{state_var_base}_relative_path}}",
            "filename": f"{{{state_var_base}_filename}}",
        }

        combined: Dict[str, Any] = {}
        combined.update({key: value for key, value in state_placeholders.items()})
        combined.update({f"legacy_{key}": value for key, value in legacy_placeholders.items()})
        combined.update({f"bare_{key}": value for key, value in bare_placeholders.items()})

        existing = variant.get("placeholders")
        if isinstance(existing, MutableMapping):
            merged = dict(existing)
            merged.update(combined)
            variant["placeholders"] = merged
        else:
            variant["placeholders"] = combined

        variant["placeholder_token"] = token_base
        variant["state_placeholder_prefix"] = state_var_base

        if variant.get("inline_markdown") or variant.get("inline_uri"):
            variant.setdefault("inline_placeholder", state_placeholders["image"])
            variant.setdefault("inline_placeholder_legacy", legacy_placeholders["image"])
        if variant.get("download_markdown") or variant.get("download_uri"):
            variant.setdefault("download_placeholder", state_placeholders["link"])
            variant.setdefault("download_placeholder_legacy", legacy_placeholders["link"])

    if not variant.get("inline_markdown") and not variant.get("download_uri"):
        return None

    return variant


def _preview_heading(summary: Dict[str, Any]) -> str:
    name = summary.get("view_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    identifier = summary.get("view_id")
    if isinstance(identifier, str) and identifier.strip():
        return identifier.strip()
    return "Visão"


def _preview_summary_markdown(summary: Dict[str, Any]) -> Optional[str]:
    inline = summary.get("inline_markdown")
    download_md = summary.get("download_markdown")
    download_uri = summary.get("download_uri")

    if not inline and not download_md and not download_uri:
        return None

    blocks: List[str] = []

    heading = _preview_heading(summary)
    if heading:
        blocks.append(f"### {heading}")

    if isinstance(inline, str) and inline.strip():
        blocks.append(inline.strip())

    if isinstance(download_md, str) and download_md.strip():
        blocks.append(download_md.strip())
    elif isinstance(download_uri, str) and download_uri.strip():
        blocks.append(f"[Baixar pré-visualização]({download_uri.strip()})")

    return "\n\n".join(blocks)


def _summarize_layout_previews(
    views: Sequence[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    summaries: List[Dict[str, Any]] = []
    artifacts: List[Dict[str, Any]] = []
    seen_artifacts: set[tuple[Any, Any, Any]] = set()

    for view_payload in views:
        if not isinstance(view_payload, MutableMapping):
            continue
        preview_payload = view_payload.get("layout_preview")
        if not isinstance(preview_payload, MutableMapping):
            continue

        variants: List[Dict[str, Any]] = []
        png_variant: Dict[str, Any] | None = None
        svg_variant: Dict[str, Any] | None = None
        for candidate in (preview_payload, preview_payload.get("png")):
            variant = _build_preview_variant(candidate)
            if not variant:
                continue
            artifact_payload = variant.get("artifact")
            if isinstance(artifact_payload, MutableMapping):
                key = (
                    artifact_payload.get("filename"),
                    artifact_payload.get("mime_type"),
                    artifact_payload.get("encoding"),
                )
                if key not in seen_artifacts:
                    seen_artifacts.add(key)
                    artifacts.append(dict(artifact_payload))
            variants.append(variant)
            format_hint = str(variant.get("format") or "").lower()
            if format_hint == "png" and png_variant is None:
                png_variant = variant
            if format_hint == "svg" and svg_variant is None:
                svg_variant = variant

        if not variants:
            continue

        summary: Dict[str, Any] = {
            "view_id": view_payload.get("id") or view_payload.get("identifier"),
            "view_name": view_payload.get("name"),
            "variants": variants,
        }

        list_view_name = view_payload.get("list_view_name")
        if isinstance(list_view_name, str) and list_view_name.strip():
            summary.setdefault("view_name", list_view_name.strip())
            summary["list_view_name"] = list_view_name.strip()

        placeholder_candidates = []
        for variant in variants:
            placeholders_payload = variant.get("placeholders")
            if isinstance(placeholders_payload, MutableMapping):
                placeholder_candidates.append(placeholders_payload)
        if placeholder_candidates:
            merged_placeholders: Dict[str, Any] = {}
            for mapping in placeholder_candidates:
                merged_placeholders.update(mapping)
            summary["placeholders"] = merged_placeholders

        primary_inline = png_variant or variants[0]
        if "inline_markdown" in primary_inline:
            summary["inline_markdown"] = primary_inline["inline_markdown"]
        if "inline_uri" in primary_inline:
            summary["inline_uri"] = primary_inline["inline_uri"]
        if "inline_data_uri" in primary_inline:
            summary["inline_data_uri"] = primary_inline["inline_data_uri"]
        if "inline_html" in primary_inline:
            summary["inline_html"] = primary_inline["inline_html"]
        if "local_path" in primary_inline:
            summary["inline_path"] = primary_inline["local_path"]
        if "inline_placeholder" in primary_inline:
            summary["inline_placeholder"] = primary_inline["inline_placeholder"]
        if "inline_placeholder_legacy" in primary_inline:
            summary["inline_placeholder_legacy"] = primary_inline["inline_placeholder_legacy"]

        primary_download = svg_variant or variants[0]
        if "download_markdown" in primary_download:
            summary["download_markdown"] = primary_download["download_markdown"]
        if "download_uri" in primary_download:
            summary["download_uri"] = primary_download["download_uri"]
        if "download_data_uri" in primary_download:
            summary["download_data_uri"] = primary_download["download_data_uri"]
        if "download_html" in primary_download:
            summary["download_html"] = primary_download["download_html"]
        if "local_path" in primary_download:
            summary["download_path"] = primary_download["local_path"]
        if "download_placeholder" in primary_download:
            summary["download_placeholder"] = primary_download["download_placeholder"]
        if "download_placeholder_legacy" in primary_download:
            summary["download_placeholder_legacy"] = primary_download["download_placeholder_legacy"]

        placeholder_token = primary_inline.get("placeholder_token") or primary_download.get("placeholder_token")
        if isinstance(placeholder_token, str) and placeholder_token.strip():
            summary["placeholder_token"] = placeholder_token.strip()
        state_prefix = primary_inline.get("state_placeholder_prefix") or primary_download.get(
            "state_placeholder_prefix"
        )
        if isinstance(state_prefix, str) and state_prefix.strip():
            summary["state_placeholder_prefix"] = state_prefix.strip()

        summaries.append(summary)

    return summaries, artifacts


def _aggregate_preview_messages(
    summaries: Sequence[Dict[str, Any]]
) -> List[str]:
    messages: List[str] = []
    for summary in summaries:
        if not isinstance(summary, MutableMapping):
            continue
        markdown = _preview_summary_markdown(summary)
        if markdown:
            messages.append(markdown)
    return messages


def generate_layout_preview(
    datamodel: types.Content | str | bytes | None,
    template_path: str | None = None,
    session_state: MutableMapping | None = None,
    view_filter: str | Sequence | None = None,
) -> Dict[str, Any]:
    payload: Optional[Dict[str, Any]] = None

    if datamodel is not None:
        raw_text = _content_to_text(datamodel)
        try:
            payload = _safe_json_loads(raw_text)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.error(
                "Datamodel inválido para pré-visualização de layout",
                exc_info=exc,
            )
            raise ValueError("O conteúdo enviado não é um JSON válido.") from exc
    else:
        cached = get_cached_artifact(session_state, SESSION_ARTIFACT_FINAL_DATAMODEL)
        if isinstance(cached, MutableMapping):
            payload = copy.deepcopy(cached.get("datamodel"))
            if payload is None and cached.get("json"):
                try:
                    payload = _safe_json_loads(str(cached["json"]))
                except (TypeError, ValueError, json.JSONDecodeError):
                    payload = None

    if not isinstance(payload, MutableMapping):
        raise ValueError(
            "Datamodel ausente para geração de prévia; forneça o conteúdo ou finalize o datamodel antes."
        )

    template: Dict[str, Any] = {}
    template_metadata: Dict[str, Any] = {}
    view_lookup: Dict[str, str] = {}
    if template_path:
        template_file = _resolve_package_path(Path(template_path))
        if not template_file.exists():
            raise FileNotFoundError(f"Template não encontrado: {template_file}")
        template = get_cached_blueprint(session_state, template_file) or _parse_template_blueprint(
            template_file
        )
        store_blueprint(session_state, template_file, template)
        template_metadata["path"] = str(template_file.resolve())
        view_lookup = _template_view_lookup(session_state, template_file)

    element_lookup = _build_element_lookup(template, payload)
    relation_lookup = _build_relationship_lookup(template, payload)

    datamodel_views = _normalize_view_diagrams(payload.get("views"))
    blueprint_views = _normalize_view_diagrams(template.get("views"))
    explicit_filter = view_filter is not None
    filter_tokens = _normalize_view_filter(view_filter)
    if explicit_filter:
        set_view_focus(session_state, sorted(filter_tokens))
    elif session_state is not None and not filter_tokens:
        filter_tokens = _session_view_filter(session_state)

    datamodel_view_map: Dict[str, Dict[str, Any]] = {}
    datamodel_node_maps: Dict[str, Dict[str, Any]] = {}
    datamodel_connection_maps: Dict[str, Dict[str, Any]] = {}
    for view in datamodel_views:
        if not isinstance(view, dict):
            continue
        if filter_tokens and not _view_matches_filter(view, None, filter_tokens):
            continue
        view_id = view.get("id")
        if view_id:
            datamodel_view_map[str(view_id)] = view
            datamodel_node_maps[str(view_id)] = _flatten_view_nodes(view.get("nodes") or [])
            datamodel_connection_maps[str(view_id)] = _flatten_view_connections(
                view.get("connections") or []
            )

    results: List[Dict[str, Any]] = []
    processed_ids: set[str] = set()
    layout_output_dir: Path | None = None

    restrict_to_datamodel_views = not filter_tokens and bool(datamodel_view_map)

    def _attach_layout_preview(view_payload: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal layout_output_dir
        layout_info = view_payload.get("layout")
        if not layout_info:
            return view_payload
        if layout_output_dir is None:
            layout_output_dir = _ensure_output_dir()
        preview = render_view_layout(
            view_name=str(view_payload.get("name") or view_payload.get("id") or "Visão"),
            view_alias=str(view_payload.get("alias") or view_payload.get("id") or "view"),
            layout=layout_info,
            output_dir=layout_output_dir,
        )
        if preview:
            if isinstance(preview, MutableMapping):
                _populate_preview_assets(view_payload, preview)
            view_payload["layout_preview"] = preview
        return view_payload

    for view in blueprint_views:
        if not isinstance(view, dict):
            continue
        if filter_tokens and not _view_matches_filter(view, view, filter_tokens):
            continue
        view_id = view.get("id")
        view_key = str(view_id) if view_id else f"template_{len(results) + 1}"
        if restrict_to_datamodel_views and view_id and str(view_id) not in datamodel_view_map:
            continue
        override_view = datamodel_view_map.get(str(view_id)) if view_id else None
        merged_view = (
            _merge_view_diagram(view, override_view) if override_view else copy.deepcopy(view)
        )
        blueprint_nodes = _flatten_view_nodes(view.get("nodes") or [])
        blueprint_connections = _flatten_view_connections(view.get("connections") or [])
        datamodel_nodes = datamodel_node_maps.get(str(view_id), {}) if view_id else {}
        datamodel_connections = (
            datamodel_connection_maps.get(str(view_id), {}) if view_id else {}
        )
        view_payload = _build_view_preview(
            merged_view,
            view,
            element_lookup,
            relation_lookup,
            blueprint_nodes,
            blueprint_connections,
            datamodel_nodes,
            datamodel_connections,
        )
        if view_lookup and view_id:
            lookup_entry = view_lookup.get(str(view_id))
            hint_name, hint_index = _view_lookup_details(lookup_entry)
            if hint_name:
                view_payload.setdefault("list_view_name", hint_name)
                view_payload.setdefault("name", hint_name)
            if hint_index is not None:
                view_payload.setdefault("list_view_index", hint_index)
        results.append(_attach_layout_preview(view_payload))
        if view_id:
            processed_ids.add(str(view_id))
        processed_ids.add(view_key)

    for view in datamodel_views:
        if not isinstance(view, dict):
            continue
        if filter_tokens and not _view_matches_filter(view, None, filter_tokens):
            continue
        view_id = view.get("id")
        if view_id and str(view_id) in processed_ids:
            continue
        datamodel_nodes = _flatten_view_nodes(view.get("nodes") or [])
        datamodel_connections = _flatten_view_connections(view.get("connections") or [])
        view_payload = _build_view_preview(
            view,
            None,
            element_lookup,
            relation_lookup,
            {},
            {},
            datamodel_nodes,
            datamodel_connections,
        )
        if view_lookup and view_id:
            lookup_entry = view_lookup.get(str(view_id))
            hint_name, hint_index = _view_lookup_details(lookup_entry)
            if hint_name:
                view_payload.setdefault("list_view_name", hint_name)
                view_payload.setdefault("name", hint_name)
            if hint_index is not None:
                view_payload.setdefault("list_view_index", hint_index)
        results.append(_attach_layout_preview(view_payload))
        if view_id:
            processed_ids.add(str(view_id))

    if not results:
        raise ValueError(
            "Não foi possível identificar visões no datamodel ou no template informado."
        )

    response: Dict[str, Any] = {
        "model_identifier": payload.get("model_identifier"),
        "model_name": payload.get("model_name"),
        "model_documentation": payload.get("model_documentation"),
        "element_count": len(payload.get("elements") or []),
        "relationship_count": len(payload.get("relations") or []),
        "view_count": len(results),
        "views": results,
    }

    preview_summaries, preview_artifacts = _summarize_layout_previews(results)

    preview_messages = _aggregate_preview_messages(preview_summaries)

    if preview_summaries:
        response["preview_summaries"] = preview_summaries

    if preview_artifacts:
        response["artifacts"] = preview_artifacts

    if preview_messages:
        response["preview_messages"] = preview_messages
        response["message"] = "\n\n".join(preview_messages)

    if preview_summaries:
        primary = preview_summaries[0]
        primary_inline = primary.get("inline_markdown")
        primary_download = primary.get("download_markdown")
        primary_download_uri = primary.get("download_uri")
        primary_summary_markdown = _preview_summary_markdown(primary)

        if isinstance(primary_inline, str) and primary_inline.strip():
            response["inline_markdown"] = primary_inline
        if isinstance(primary_download, str) and primary_download.strip():
            response["download_markdown"] = primary_download
        elif isinstance(primary_download_uri, str) and primary_download_uri.strip():
            response["download_markdown"] = (
                primary.get("download_markdown")
                or f"[Baixar pré-visualização]({primary_download_uri})"
            )

        response["primary_preview"] = {
            "view_id": primary.get("view_id"),
            "view_name": primary.get("view_name"),
            "inline_markdown": response.get("inline_markdown"),
            "download_markdown": response.get("download_markdown"),
            "download_uri": primary_download_uri,
        }

        inline_placeholder = primary.get("inline_placeholder")
        download_placeholder = primary.get("download_placeholder")
        if isinstance(inline_placeholder, str) and inline_placeholder.strip():
            response["inline_placeholder"] = inline_placeholder
            response["primary_preview"]["inline_placeholder"] = inline_placeholder
        legacy_inline_placeholder = primary.get("inline_placeholder_legacy")
        if isinstance(legacy_inline_placeholder, str) and legacy_inline_placeholder.strip():
            response["inline_placeholder_legacy"] = legacy_inline_placeholder
            response["primary_preview"]["inline_placeholder_legacy"] = legacy_inline_placeholder
        if isinstance(download_placeholder, str) and download_placeholder.strip():
            response["download_placeholder"] = download_placeholder
            response["primary_preview"]["download_placeholder"] = download_placeholder
        legacy_download_placeholder = primary.get("download_placeholder_legacy")
        if isinstance(legacy_download_placeholder, str) and legacy_download_placeholder.strip():
            response["download_placeholder_legacy"] = legacy_download_placeholder
            response["primary_preview"]["download_placeholder_legacy"] = legacy_download_placeholder

        placeholder_token = primary.get("placeholder_token")
        if isinstance(placeholder_token, str) and placeholder_token.strip():
            response["placeholder_token"] = placeholder_token.strip()
            response["primary_preview"]["placeholder_token"] = placeholder_token.strip()
        state_prefix = primary.get("state_placeholder_prefix")
        if isinstance(state_prefix, str) and state_prefix.strip():
            response["state_placeholder_prefix"] = state_prefix.strip()
            response["primary_preview"]["state_placeholder_prefix"] = state_prefix.strip()

        placeholders_payload = primary.get("placeholders")
        if isinstance(placeholders_payload, MutableMapping):
            response["placeholders"] = dict(placeholders_payload)
            response["primary_preview"]["placeholders"] = dict(placeholders_payload)

        if primary_summary_markdown:
            response.setdefault("preview_messages", preview_messages)
            if not response.get("message"):
                response["message"] = primary_summary_markdown
            response["primary_message"] = primary_summary_markdown

    if template_metadata:
        response["template"] = template_metadata

    store_artifact(
        session_state,
        SESSION_ARTIFACT_LAYOUT_PREVIEW,
        response,
    )
    bucket = get_session_bucket(session_state)
    if isinstance(bucket, MutableMapping):
        bucket["layout_preview"] = copy.deepcopy(response)

    status_payload: Dict[str, Any] = {
        "status": "ok",
        "artifact": SESSION_ARTIFACT_LAYOUT_PREVIEW,
        "view_count": len(results),
    }

    if preview_messages:
        status_payload["message"] = "Pré-visualização armazenada com sucesso."

    return status_payload


def generate_archimate_diagram(
    model_json_path: str | None,
    output_filename: str = DEFAULT_DIAGRAM_FILENAME,
    template_path: str | None = None,
    validate: bool = True,
    xsd_dir: str | None = None,
    session_state: MutableMapping | None = None,
) -> Dict[str, Any]:
    """Gera o XML ArchiMate utilizando o template padrão e valida com os XSDs oficiais."""

    resolved_model_path = model_json_path
    if not resolved_model_path and session_state is not None:
        cached = get_cached_artifact(session_state, SESSION_ARTIFACT_SAVED_DATAMODEL)
        if isinstance(cached, MutableMapping):
            cached_path = cached.get("path")
            if isinstance(cached_path, str) and cached_path.strip():
                resolved_model_path = cached_path

    if not resolved_model_path:
        raise ValueError(
            "Caminho do datamodel não informado; salve o datamodel antes de gerar o XML ou forneça o caminho explicitamente."
        )

    model_path = Path(resolved_model_path)
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

    response = {
        "path": str(xml_path.resolve()),
        "validated": validate,
        "validation_report": validation,
    }

    if session_state is not None:
        store_artifact(
            session_state,
            SESSION_ARTIFACT_ARCHIMATE_XML,
            response,
        )
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_ARCHIMATE_XML,
            "path": response["path"],
            "validated": response.get("validated", False),
        }

    return response


def list_templates(
    directory: str | None = None,
    session_state: MutableMapping | None = None,
) -> Dict[str, Any]:
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
            views_metadata: List[Dict[str, Any]] = []
            for view in root.findall("a:views/a:diagrams/a:view", ns):
                view_entry: Dict[str, Any] = {}
                view_id = view.get("identifier")
                if view_id:
                    view_entry["identifier"] = view_id
                view_name = _text_payload(view.find("a:name", ns))
                name_text = _payload_text(view_name)
                if name_text:
                    view_entry["name"] = name_text
                doc_text = _payload_text(
                    _text_payload(view.find("a:documentation", ns))
                )
                if doc_text:
                    view_entry["documentation"] = doc_text
                viewpoint_ref = view.get("viewpoint") or view.get("viewpointRef")
                if viewpoint_ref:
                    view_entry["viewpoint"] = viewpoint_ref
                if view_entry:
                    views_metadata.append(view_entry)
            if views_metadata:
                metadata["views"] = views_metadata
            discovered.append(metadata)
        except ET.ParseError:
            logger.warning("Template inválido ignorado", extra={"path": str(template_path)})
            continue

    payload = {
        "directory": str(templates_dir.resolve()),
        "count": len(discovered),
        "templates": discovered,
    }

    if session_state is not None:
        store_artifact(
            session_state,
            SESSION_ARTIFACT_TEMPLATE_LISTING,
            payload,
        )
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_TEMPLATE_LISTING,
            "count": len(discovered),
        }

    return payload


def describe_template(
    template_path: str,
    view_filter: str | Sequence | None = None,
    session_state: MutableMapping | None = None,
) -> Dict[str, Any]:
    """Retorna a estrutura detalhada de um template ArchiMate."""

    template = _resolve_package_path(Path(template_path))

    if not template.exists():
        raise FileNotFoundError(f"Template não encontrado: {template}")

    explicit_filter = view_filter is not None
    filter_tokens = _normalize_view_filter(view_filter)
    if not filter_tokens:
        if explicit_filter and session_state is not None:
            set_view_focus(session_state, [])
        if session_state is not None:
            filter_tokens = _session_view_filter(session_state)

    blueprint = _parse_template_blueprint(template)
    view_lookup = _template_view_lookup(session_state, template)

    if view_lookup:
        views_section = blueprint.get("views")
        if isinstance(views_section, MutableMapping):
            diagrams = views_section.get("diagrams")
            if isinstance(diagrams, Sequence):
                for diagram in diagrams:
                    if not isinstance(diagram, MutableMapping):
                        continue
                    identifier = diagram.get("id") or diagram.get("identifier")
                    if isinstance(identifier, str) and identifier.strip():
                        lookup_entry = view_lookup.get(identifier.strip())
                        hint_name, hint_index = _view_lookup_details(lookup_entry)
                        if hint_name:
                            diagram["list_view_name"] = hint_name
                            if not diagram.get("name"):
                                diagram["name"] = hint_name
                        if hint_index is not None:
                            diagram["list_view_index"] = hint_index

    store_blueprint(session_state, template, blueprint)

    matching_identifiers: set[str] = set()
    matching_tokens: set[str] = set()
    if filter_tokens:
        for diagram in blueprint.get("views", {}).get("diagrams", []):
            if not isinstance(diagram, dict):
                continue
            candidates = _view_token_candidates(diagram)
            if candidates & filter_tokens:
                identifier = diagram.get("id") or diagram.get("identifier")
                if isinstance(identifier, str):
                    identifier_text = identifier.strip()
                    if identifier_text:
                        matching_identifiers.add(identifier_text)
                matching_tokens.update(candidates)
        if not matching_identifiers and not matching_tokens:
            raise ValueError(
                "Nenhuma visão do template corresponde ao filtro informado."
            )
        set_view_focus(session_state, sorted(filter_tokens))

    guidance = _build_guidance_from_blueprint(blueprint)
    guidance["model"]["path"] = str(template.resolve())

    if filter_tokens:
        views_section = guidance.get("views")
        if isinstance(views_section, dict):
            diagrams = views_section.get("diagrams")
            if isinstance(diagrams, list):
                filtered_diagrams: List[Dict[str, Any]] = []
                for diagram in diagrams:
                    tokens = _view_token_candidates(diagram)
                    identifier = diagram.get("identifier")
                    include = False
                    if isinstance(identifier, str):
                        identifier_text = identifier.strip()
                        if identifier_text and identifier_text in matching_identifiers:
                            include = True
                    if not include and tokens & (matching_tokens or filter_tokens):
                        include = True
                    if include:
                        if view_lookup:
                            lookup_entry = view_lookup.get(
                                str(diagram.get("identifier") or "").strip()
                            )
                            hint_name, hint_index = _view_lookup_details(lookup_entry)
                            if hint_name:
                                diagram.setdefault("list_view_name", hint_name)
                                diagram.setdefault("name", hint_name)
                            if hint_index is not None:
                                diagram.setdefault("list_view_index", hint_index)
                        filtered_diagrams.append(diagram)
                if not filtered_diagrams:
                    raise ValueError(
                        "Nenhuma visão simplificada corresponde ao filtro informado."
                    )
                views_section["diagrams"] = filtered_diagrams

    if session_state is not None:
        store_artifact(
            session_state,
            SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
            guidance,
        )
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
            "view_count": len(
                guidance.get("views", {}).get("diagrams", [])
                if isinstance(guidance.get("views"), dict)
                else []
            ),
        }

    return guidance
__all__ = [
    "SESSION_ARTIFACT_TEMPLATE_LISTING",
    "SESSION_ARTIFACT_TEMPLATE_GUIDANCE",
    "SESSION_ARTIFACT_FINAL_DATAMODEL",
    "SESSION_ARTIFACT_LAYOUT_PREVIEW",
    "SESSION_ARTIFACT_SAVED_DATAMODEL",
    "SESSION_ARTIFACT_ARCHIMATE_XML",
    "list_templates",
    "describe_template",
    "generate_layout_preview",
    "finalize_datamodel",
    "save_datamodel",
    "generate_archimate_diagram",
]
