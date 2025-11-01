"""Geração de pré-visualizações de layout para as visões ArchiMate."""

from __future__ import annotations

import base64
import copy
import html
import json
import random
import re
import unicodedata
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from datetime import datetime
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
    get_session_bucket,
    store_artifact,
)
from .templates import (
    TemplateMetadata,
    ViewMetadata,
    load_template_blueprint,
    load_template_metadata,
    resolve_template_path,
)
from ...utils.logging_config import get_logger

__all__ = ["generate_layout_preview"]

logger = get_logger(__name__)

_CODE_FENCE_RE = re.compile(
    r"^\s*(?:```|~~~)(?:json)?\s*(?P<body>.*?)(?:```|~~~)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_PLACEHOLDER_RE = re.compile(r"\s*[-–]?\s*\{[^}]+\}")
_WHITESPACE_RE = re.compile(r"\s+")
_PLACEHOLDER_TOKEN_RE = re.compile(r"\{\{[^{}]+\}\}|\[\[[^\[\]]+\]\]")


def _resolve_template_path(template_path: str | None) -> Path:
    return resolve_template_path(template_path)


def _slugify_filename_component(value: str | None) -> str:
    if not value:
        return "item"
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", ascii_value.lower())
    cleaned = cleaned.strip("_")
    return cleaned or "item"


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


def _find_placeholders(
    value: Any,
    *,
    root: str,
    limit: int = 5,
) -> list[str]:
    findings: list[str] = []

    def walk(current: Any, path: str) -> None:
        if len(findings) >= limit:
            return
        if isinstance(current, str):
            match = _PLACEHOLDER_TOKEN_RE.search(current)
            if match:
                snippet = current.strip()
                if len(snippet) > 80:
                    snippet = f"{snippet[:77]}..."
                findings.append(f"{path}: {snippet}")
            return
        if isinstance(current, Mapping):
            for key, item in current.items():
                walk(item, f"{path}.{key}" if path else str(key))
                if len(findings) >= limit:
                    break
            return
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            for index, item in enumerate(current):
                walk(item, f"{path}[{index}]")
                if len(findings) >= limit:
                    break

    walk(value, root)
    return findings


def _replace_placeholder_tokens(value: str, replacements: Mapping[str, str]) -> str:
    def _replacement(match: re.Match[str]) -> str:
        token = match.group(0)
        normalized = token.strip("{}[] ").strip()
        normalized_lower = normalized.casefold()
        return (
            replacements.get(token)
            or replacements.get(normalized)
            or replacements.get(normalized_lower)
            or token
        )

    return _PLACEHOLDER_TOKEN_RE.sub(_replacement, value)


def _resolve_model_name(datamodel: Mapping[str, Any]) -> str | None:
    model_name = datamodel.get("model_name")
    if isinstance(model_name, Mapping):
        candidate = (
            model_name.get("text")
            or model_name.get("value")
            or model_name.get("name")
            or model_name.get("label")
        )
        if isinstance(candidate, str):
            return candidate.strip() or None
    elif isinstance(model_name, str):
        normalized = model_name.strip()
        if normalized:
            return normalized
    return None


def _sanitize_datamodel(payload: Mapping[str, Any], *, context: str = "datamodel") -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("O datamodel fornecido deve ser um objeto JSON com chaves e valores.")

    elements = payload.get("elements")
    if not isinstance(elements, Sequence) or not elements:
        raise ValueError(
            "O datamodel precisa conter a lista de elementos mapeados a partir da história do usuário."
        )

    model_name = _resolve_model_name(payload)
    if not model_name:
        raise ValueError(
            "Defina 'model_name' com o nome canônico da solução antes de gerar a pré-visualização."
        )
    if _PLACEHOLDER_TOKEN_RE.search(model_name):
        raise ValueError(
            "Substitua o placeholder do nome da solução no datamodel por um valor final coerente com a narrativa."
        )

    placeholder_hits = _find_placeholders(payload, root=context)
    if placeholder_hits:
        details = "; ".join(placeholder_hits[:3])
        if len(placeholder_hits) > 3:
            details = f"{details}..."
        raise ValueError(
            "O datamodel ainda contém placeholders do template que devem ser preenchidos com os dados do usuário "
            f"antes de gerar o preview: {details}"
        )

    return copy.deepcopy(dict(payload))


def _normalize_view_key(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = _WHITESPACE_RE.sub(" ", value.strip()).casefold()
    return normalized or None


def _resolve_description(
    datamodel_view: Mapping[str, Any] | None,
    datamodel: Mapping[str, Any] | None,
    default: str | None,
) -> str | None:
    candidates: list[str | None] = []
    if isinstance(datamodel_view, Mapping):
        candidates.extend(
            [
                datamodel_view.get("description"),
                datamodel_view.get("documentation"),
                datamodel_view.get("label"),
            ]
        )
    if isinstance(datamodel, Mapping):
        candidates.extend(
            [
                datamodel.get("description"),
                datamodel.get("documentation"),
            ]
        )
    candidates.append(default)
    for item in candidates:
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def _apply_layout_customization(
    layout: Mapping[str, Any],
    *,
    model_name: str | None,
    view_name: str | None,
    view_description: str | None,
    element_lookup: Mapping[str, Mapping[str, Any]],
    relationship_lookup: Mapping[str, Mapping[str, Any]],
) -> None:
    if not view_description and view_name:
        view_description = view_name

    replacements: dict[str, str] = {}
    if model_name:
        replacements["[[Nome da Solução Do Usuário]]"] = model_name
        replacements["nome da solução do usuário"] = model_name
    if view_name:
        replacements["{{Título}}"] = view_name
        replacements["titulo"] = view_name
    if view_description:
        replacements["{{Descrição}}"] = view_description
        replacements["descrição"] = view_description

    def update_text_fields(payload: dict[str, Any], fields: Iterable[str]) -> None:
        for field in fields:
            text = payload.get(field)
            if not isinstance(text, str):
                continue
            new_text = _replace_placeholder_tokens(text, replacements) if replacements else text
            if new_text != text:
                payload[field] = new_text

    # Update nodes
    nodes = layout.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            element_ref = node.get("elementRef") or node.get("element_ref")
            lookup = element_lookup.get(str(element_ref)) if element_ref else None
            if lookup:
                element_name = lookup.get("name")
                if element_name:
                    label = node.get("label")
                    if not isinstance(label, str) or _PLACEHOLDER_TOKEN_RE.search(label):
                        node["label"] = str(element_name)
                    title = node.get("title")
                    if not isinstance(title, str) or _PLACEHOLDER_TOKEN_RE.search(title):
                        node["title"] = str(element_name)
                element_doc = lookup.get("documentation")
                if element_doc:
                    doc = node.get("documentation")
                    if not isinstance(doc, str) or _PLACEHOLDER_TOKEN_RE.search(doc):
                        node["documentation"] = str(element_doc)
            update_text_fields(node, ("label", "title", "documentation"))

            # Recurse for nested nodes (groups / containers)
            inner_nodes = node.get("nodes")
            if isinstance(inner_nodes, list):
                inner_layout = {"nodes": inner_nodes, "connections": []}
                _apply_layout_customization(
                    inner_layout,
                    model_name=model_name,
                    view_name=view_name,
                    view_description=view_description,
                    element_lookup=element_lookup,
                    relationship_lookup=relationship_lookup,
                )

    # Update connections
    connections = layout.get("connections")
    if isinstance(connections, list):
        for connection in connections:
            if not isinstance(connection, dict):
                continue
            relationship_ref = connection.get("relationshipRef") or connection.get("relationship_ref")
            relation_info = (
                relationship_lookup.get(str(relationship_ref)) if relationship_ref else None
            )
            if relation_info:
                relation_name = relation_info.get("name")
                if relation_name:
                    label = connection.get("label")
                    if not isinstance(label, str) or _PLACEHOLDER_TOKEN_RE.search(label):
                        connection["label"] = str(relation_name)
                relation_doc = relation_info.get("documentation")
                if relation_doc:
                    doc = connection.get("documentation")
                    if not isinstance(doc, str) or _PLACEHOLDER_TOKEN_RE.search(doc):
                        connection["documentation"] = str(relation_doc)
            update_text_fields(connection, ("label", "documentation"))


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
        return _sanitize_datamodel(datamodel)
    if isinstance(datamodel, str):
        stripped = _strip_code_fences(datamodel)
        if not stripped.strip():
            raise ValueError(
                "Forneça um datamodel em JSON com os elementos da narrativa para gerar o preview."
            )
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:  # pragma: no cover - feedback explícito
            raise ValueError("O conteúdo enviado não é um JSON válido.") from exc
        if not isinstance(parsed, Mapping):
            raise ValueError("O datamodel fornecido deve ser um objeto JSON.")
        return _sanitize_datamodel(parsed)

    if session_state is not None:
        artifact = get_cached_artifact(session_state, SESSION_ARTIFACT_FINAL_DATAMODEL)
        if isinstance(artifact, Mapping):
            cached = artifact.get("datamodel")
            if isinstance(cached, Mapping):
                return _sanitize_datamodel(cached, context="session.datamodel")
            cached_json = artifact.get("json")
            if isinstance(cached_json, str):
                try:
                    parsed = json.loads(cached_json)
                except json.JSONDecodeError:
                    logger.debug(
                        "Datamodel armazenado na sessão está inválido.",
                        exc_info=True,
                    )
                else:
                    if isinstance(parsed, Mapping):
                        return _sanitize_datamodel(parsed, context="session.datamodel")

    raise ValueError(
        "Não há datamodel consolidado disponível. Finalize o datamodel com os elementos da história antes de gerar a pré-visualização."
    )


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
        documentation = element.get("documentation") or element.get("description")
        if name:
            target["name"] = name
        if elem_type:
            target["type"] = elem_type
        if documentation:
            target["documentation"] = documentation

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
        documentation = relation.get("documentation") or relation.get("description")
        if documentation:
            target["documentation"] = documentation

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
    *,
    model_name: str | None,
    datamodel: Mapping[str, Any] | None,
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

    view_name = (
        base_view.get("name")
        or (datamodel_view.get("name") if isinstance(datamodel_view, Mapping) else None)
        or metadata.name
    )
    name = str(view_name)

    view_description = _resolve_description(datamodel_view, datamodel, metadata.documentation)

    _apply_layout_customization(
        layout,
        model_name=model_name,
        view_name=name,
        view_description=view_description,
        element_lookup=element_lookup,
        relationship_lookup=relationship_lookup,
    )

    return {
        "identifier": metadata.identifier,
        "name": name,
        "layout": layout,
        "raw": base_view,
    }


def _build_replacements(
    render_payload: Mapping[str, Any],
    *,
    template_label: str,
    layout_label: str,
    view_label: str,
) -> dict[str, Any]:
    label = "Abrir diagrama em SVG"
    svg_data_uri = render_payload.get("svg_data_uri") or ""
    if not svg_data_uri:
        local_path = render_payload.get("local_path")
        if isinstance(local_path, str):
            try:
                encoded = base64.b64encode(Path(local_path).read_bytes()).decode("ascii")
            except OSError:
                encoded = ""
            if encoded:
                svg_data_uri = f"data:image/svg+xml;base64,{encoded}"

    alt_text = f"{template_label} - {layout_label} - {view_label}"
    alt_attr = html.escape(alt_text, quote=True)

    inline_value = ""
    if svg_data_uri:
        inline_value = (
            f'<img src="{svg_data_uri}" alt="{alt_attr}" title="{alt_attr}" width="100%" />'
        )
    elif render_payload.get("inline_markdown"):
        inline_value = str(render_payload.get("inline_markdown") or "")

    download_url = (
        str(render_payload.get("download_uri") or "")
        or str(render_payload.get("uri") or "")
        or str(render_payload.get("inline_uri") or "")
    )
    if not download_url:
        local_path = render_payload.get("local_path")
        if isinstance(local_path, str):
            download_url = Path(local_path).resolve().as_uri()

    download_markdown = str(render_payload.get("download_markdown") or "")
    if download_url:
        download_markdown = f"[{label}]({download_url})"

    replacements = {
        "layout_preview.inline": inline_value,
        "layout_preview.view_name": view_label,
        "layout_preview.layout_name": layout_label,
        "layout_preview.template_name": template_label,
        "layout_preview.download.url": download_url,
        "layout_preview.download.label": label,
        "layout_preview.download.markdown": download_markdown,
        "layout_preview.download": download_markdown,
        "layout_preview.svg": svg_data_uri,
        "layout_preview.svg.url": svg_data_uri,
        "layout_preview.svg.markdown": download_markdown,
        "layout_preview.image.alt": alt_text,
        "layout_preview.image.title": alt_text,
    }

    return replacements


def _index_datamodel_views(
    datamodel: Mapping[str, Any] | None,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    if not isinstance(datamodel, Mapping):
        return {}, {}

    views = datamodel.get("views")
    diagrams: Sequence[Any] | None
    if isinstance(views, Mapping):
        diagrams = views.get("diagrams")  # type: ignore[assignment]
    else:
        diagrams = views

    id_lookup: dict[str, Mapping[str, Any]] = {}
    name_lookup: dict[str, Mapping[str, Any]] = {}
    if isinstance(diagrams, Sequence):
        for view in diagrams:
            if not isinstance(view, Mapping):
                continue
            identifier = view.get("id") or view.get("identifier")
            if identifier:
                id_lookup[str(identifier)] = view
            name = view.get("name") or view.get("title")
            normalized = _normalize_view_key(name if isinstance(name, str) else None)
            if normalized and normalized not in name_lookup:
                name_lookup[normalized] = view
    return id_lookup, name_lookup


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

    datamodel_views_by_id, datamodel_views_by_name = _index_datamodel_views(datamodel_payload)
    element_lookup = _build_element_lookup(blueprint, datamodel_payload)
    relationship_lookup = _build_relationship_lookup(blueprint, datamodel_payload)
    model_name = _resolve_model_name(datamodel_payload) if datamodel_payload else None

    view_payloads: list[dict[str, Any]] = []
    for meta in available_views:
        blueprint_view = _match_blueprint_view(blueprint, meta.identifier)
        datamodel_view = datamodel_views_by_id.get(meta.identifier)
        if datamodel_view is None:
            normalized_name = _normalize_view_key(meta.name)
            if normalized_name:
                datamodel_view = datamodel_views_by_name.get(normalized_name)
        if datamodel_view is None and datamodel_views_by_id:
            # Fallback: utiliza a única visão disponível no datamodel quando não há correspondência explícita.
            if len(datamodel_views_by_id) == 1:
                datamodel_view = next(iter(datamodel_views_by_id.values()))
        view_payloads.append(
            _build_view_payload(
                meta,
                blueprint_view,
                datamodel_view,
                element_lookup,
                relationship_lookup,
                model_name=model_name,
                datamodel=datamodel_payload,
            )
        )

    primary_view = view_payloads[0]

    if not primary_view["layout"]["nodes"]:
        raise ValueError("A visão selecionada não possui elementos para renderização.")

    layout_placeholder_hits = _find_placeholders(primary_view["layout"], root="layout")
    if layout_placeholder_hits:
        details = "; ".join(layout_placeholder_hits[:3])
        if len(layout_placeholder_hits) > 3:
            details = f"{details}..."
        raise ValueError(
            "A visão selecionada ainda contém placeholders do template. "
            "Atualize as labels, containers e relacionamentos com o conteúdo da história do usuário antes de gerar o preview: "
            f"{details}"
        )

    node_count = len(primary_view["layout"]["nodes"])
    conn_count = len(primary_view["layout"].get("connections", []))
    logger.info(
        "generate_layout_preview: visão '%s' renderizada (%d nós / %d conexões).",
        primary_view["name"],
        node_count,
        conn_count,
    )

    timestamp = datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")
    run_dir = OUTPUT_DIR / f"{timestamp}-{random.randint(0, 999999):06d}"
    run_dir.mkdir(parents=True, exist_ok=True)

    layout_label = Path(target_template).stem
    template_label = metadata.model_name or metadata.model_identifier or layout_label
    view_label = primary_view["name"]
    alias_label = f"{template_label}-{layout_label}-{view_label}"

    template_slug = _slugify_filename_component(template_label)
    layout_slug = _slugify_filename_component(layout_label)
    view_slug = _slugify_filename_component(view_label)
    preview_slug = f"preview_{template_slug}_{layout_slug}_{view_slug}"
    datamodel_filename = f"preview_datamodel_{template_slug}_{layout_slug}_{view_slug}.json"

    render_payload = render_view_layout(
        primary_view["name"],
        alias_label,
        layout=primary_view["layout"],
        output_dir=run_dir,
        output_slug=preview_slug,
    )
    if not isinstance(render_payload, Mapping):
        raise ValueError("Não foi possível renderizar a pré-visualização solicitada.")

    replacements = _build_replacements(
        render_payload,
        template_label=template_label,
        layout_label=layout_label,
        view_label=view_label,
    )
    placeholders = {
        "inline": "{{session.state.layout_preview.inline}}",
        "download_markdown": "{{session.state.layout_preview.download.markdown}}",
        "download_link": "[[session.state.layout_preview.download.url]]",
        "svg_data_uri": "[[session.state.layout_preview.svg]]",
        "image_alt": "[[session.state.layout_preview.image.alt]]",
        "image_title": "[[session.state.layout_preview.image.title]]",
    }

    svg_local_path = render_payload.get("local_path")
    datamodel_file_path: Path | None = None
    datamodel_snapshot: dict[str, Any] | None = None
    if isinstance(datamodel_payload, Mapping):
        datamodel_snapshot = datamodel_payload
    elif isinstance(blueprint, Mapping):
        datamodel_snapshot = copy.deepcopy(blueprint)
    if datamodel_snapshot is not None:
        datamodel_file_path = run_dir / datamodel_filename
        datamodel_file_path.write_text(
            json.dumps(datamodel_snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    artifact = {
        "template": str(target_template),
        "view": {
            "identifier": primary_view["identifier"],
            "name": primary_view["name"],
            "layout": primary_view["layout"],
            "alias": alias_label,
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
        "output_directory": str(run_dir),
        "links": {
            "layout_svg": {
                "label": replacements.get("layout_preview.download.label"),
                "url": replacements.get("layout_preview.download.url"),
                "format": "svg",
                "path": svg_local_path,
                "data_uri": replacements.get("layout_preview.svg"),
                "filename": f"{preview_slug}.svg",
                "alt": replacements.get("layout_preview.image.alt"),
                "title": replacements.get("layout_preview.image.title"),
            }
        },
        "placeholders": placeholders,
    }

    if datamodel_snapshot is not None:
        artifact["datamodel_snapshot"] = datamodel_snapshot
    if datamodel_file_path is not None:
        artifact.setdefault("links", {})["datamodel_json"] = {
            "label": "Datamodel utilizado",
            "format": "json",
            "path": str(datamodel_file_path.resolve()),
            "filename": datamodel_file_path.name,
        }

    session_snapshot = {
        "template_name": template_label,
        "layout_name": layout_label,
        "view_name": replacements.get("layout_preview.view_name"),
        "inline": replacements.get("layout_preview.inline"),
        "download": {
            "label": replacements.get("layout_preview.download.label"),
            "markdown": replacements.get("layout_preview.download.markdown"),
            "url": replacements.get("layout_preview.download.url"),
        },
        "svg": replacements.get("layout_preview.svg"),
        "image": {
            "alt": replacements.get("layout_preview.image.alt"),
            "title": replacements.get("layout_preview.image.title"),
            "path": svg_local_path,
        },
        "files": {
            "svg": str(Path(svg_local_path).resolve()) if isinstance(svg_local_path, str) else None,
            "datamodel": str(datamodel_file_path.resolve()) if datamodel_file_path else None,
        },
    }
    artifact["session_snapshot"] = session_snapshot

    if session_state is not None:
        store_artifact(session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW, artifact)
        bucket = get_session_bucket(session_state)
        bucket["layout_preview"] = session_snapshot
        logger.debug(
            "generate_layout_preview: artefato '%s' armazenado no estado de sessão.",
            SESSION_ARTIFACT_LAYOUT_PREVIEW,
        )
        logger.info("generate_layout_preview: arquivos disponíveis em '%s'.", run_dir)
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_LAYOUT_PREVIEW,
            "view_name": primary_view["name"],
            "placeholders": placeholders,
        }

    logger.debug(
        "generate_layout_preview: retornando artefato sem sessão explícita (modo fallback)."
    )
    logger.info("generate_layout_preview: arquivos disponíveis em '%s'.", run_dir)
    return artifact
