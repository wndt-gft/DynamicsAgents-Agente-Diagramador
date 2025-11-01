"""Callback pós-resposta responsável por substituir placeholders de sessão."""

from __future__ import annotations

import base64
import html
import logging
import re
from collections.abc import Iterable as IterableABC, Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any, Iterable

from ..tools.diagramador.session import get_session_bucket
from ..utils import get_fallback_session_state
from ..utils.logging_config import get_logger

PLACEHOLDER_RE = re.compile(r"\{\{\s*(?:session\.)?state\.([A-Za-z0-9_.-]+)\s*\}\}")
BRACKET_RE = re.compile(r"\[\[\s*(?:session\.)?state\.([A-Za-z0-9_.-]+)\s*\]\]")
PLACEHOLDER_ANY_RE = re.compile(
    r"(\{\{\s*(?:session\.)?state\.[A-Za-z0-9_.-]+\s*\}\})|"
    r"(\[\[\s*(?:session\.)?state\.[A-Za-z0-9_.-]+\s*\]\])"
)

__all__ = ["after_model_response_callback"]

logger = get_logger(__name__)

def _extract_session_state(payload: Any) -> MutableMapping[str, Any] | None:
    queue: list[Any] = [payload]
    visited: set[int] = set()
    candidate_attrs = (
        "session_state",
        "state",
        "data",
        "context",
        "invocation_context",
    )

    while queue:
        current = queue.pop(0)
        marker = id(current)
        if marker in visited:
            continue
        visited.add(marker)

        if isinstance(current, MutableMapping):
            return current

        for attr in candidate_attrs:
            try:
                value = getattr(current, attr)
            except AttributeError:
                continue
            if value is not None:
                queue.append(value)

def _file_to_data_uri(path: str | None, mime: str) -> str | None:
    if not path:
        return None
    if path.startswith("file://"):
        path = path[7:]
    try:
        payload = Path(path).read_bytes()
    except Exception:
        return None
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _build_inline_svg_markup(
    svg_data_uri: str | None,
    *,
    alt: str | None,
    title: str | None,
) -> str:
    if not svg_data_uri:
        return ""
    alt_text = alt or "Pré-visualização"
    title_text = title or alt_text
    alt_attr = html.escape(alt_text, quote=True)
    title_attr = html.escape(title_text, quote=True)
    return f'<img src="{svg_data_uri}" alt="{alt_attr}" title="{title_attr}" width="100%" />'


def _collect_replacements(
    bucket: Mapping[str, Any], session_state: Mapping[str, Any]
) -> dict[str, str]:
    artifacts = bucket.get("artifacts")
    replacements: dict[str, str] = {}
    if not isinstance(artifacts, Mapping):
        artifacts = {}

    for artifact in artifacts.values():
        if not isinstance(artifact, Mapping):
            continue
        mapping = artifact.get("replacements")
        if not isinstance(mapping, Mapping):
            continue
        for placeholder, value in mapping.items():
            if value is None:
                continue
            replacements[str(placeholder)] = str(value)

    snapshot = bucket.get("layout_preview")
    if isinstance(snapshot, Mapping):
        download_payload = snapshot.get("download")
        image_payload = snapshot.get("image")
        files_payload = snapshot.get("files")

        svg_value = snapshot.get("svg")
        svg_data_uri: str | None
        if isinstance(svg_value, Mapping):
            svg_data_uri = svg_value.get("data_uri") or svg_value.get("url")
        elif isinstance(svg_value, str):
            svg_data_uri = svg_value
        else:
            svg_data_uri = None
        if not svg_data_uri and isinstance(files_payload, Mapping):
            svg_path = files_payload.get("svg")
            if isinstance(svg_path, str):
                svg_data_uri = _file_to_data_uri(svg_path, "image/svg+xml")

        inline_value = snapshot.get("inline") if isinstance(snapshot.get("inline"), str) else ""
        if not inline_value:
            alt = image_payload.get("alt") if isinstance(image_payload, Mapping) else None
            title = image_payload.get("title") if isinstance(image_payload, Mapping) else None
            inline_value = _build_inline_svg_markup(svg_data_uri, alt=alt, title=title)

        mapping = {
            "layout_preview.inline": inline_value,
            "layout_preview.view_name": snapshot.get("view_name"),
            "layout_preview.layout_name": snapshot.get("layout_name"),
            "layout_preview.template_name": snapshot.get("template_name"),
            "layout_preview.download.markdown": download_payload.get("markdown")
            if isinstance(download_payload, Mapping)
            else None,
            "layout_preview.download.url": download_payload.get("url")
            if isinstance(download_payload, Mapping)
            else None,
            "layout_preview.download.label": download_payload.get("label")
            if isinstance(download_payload, Mapping)
            else None,
            "layout_preview.svg": svg_data_uri,
            "layout_preview.image.alt": image_payload.get("alt")
            if isinstance(image_payload, Mapping)
            else None,
            "layout_preview.image.title": image_payload.get("title")
            if isinstance(image_payload, Mapping)
            else None,
        }
        for placeholder, value in mapping.items():
            if value is None:
                continue
            replacements.setdefault(placeholder, str(value))

    # allow explicit session mappings (e.g. session.state.layout_preview.svg in state root)
    session_preview = session_state.get("layout_preview")
    if isinstance(session_preview, Mapping):
        download_payload = session_preview.get("download")
        image_payload = session_preview.get("image")
        files_payload = session_preview.get("files")

        svg_value = session_preview.get("svg")
        svg_data_uri: str | None
        if isinstance(svg_value, Mapping):
            svg_data_uri = svg_value.get("data_uri") or svg_value.get("url")
        elif isinstance(svg_value, str):
            svg_data_uri = svg_value
        else:
            svg_data_uri = None
        if not svg_data_uri and isinstance(files_payload, Mapping):
            svg_path = files_payload.get("svg")
            if isinstance(svg_path, str):
                svg_data_uri = _file_to_data_uri(svg_path, "image/svg+xml")

        inline_value = session_preview.get("inline") if isinstance(session_preview.get("inline"), str) else ""
        if not inline_value:
            alt = image_payload.get("alt") if isinstance(image_payload, Mapping) else None
            title = image_payload.get("title") if isinstance(image_payload, Mapping) else None
            inline_value = _build_inline_svg_markup(svg_data_uri, alt=alt, title=title)

        fallback_mapping = {
            "layout_preview.inline": inline_value,
            "layout_preview.view_name": session_preview.get("view_name"),
            "layout_preview.layout_name": session_preview.get("layout_name"),
            "layout_preview.template_name": session_preview.get("template_name"),
            "layout_preview.download.markdown": download_payload.get("markdown")
            if isinstance(download_payload, Mapping)
            else None,
            "layout_preview.download.url": download_payload.get("url")
            if isinstance(download_payload, Mapping)
            else None,
            "layout_preview.download.label": download_payload.get("label")
            if isinstance(download_payload, Mapping)
            else None,
            "layout_preview.svg": svg_data_uri,
            "layout_preview.image.alt": image_payload.get("alt")
            if isinstance(image_payload, Mapping)
            else None,
            "layout_preview.image.title": image_payload.get("title")
            if isinstance(image_payload, Mapping)
            else None,
        }
        for placeholder, value in fallback_mapping.items():
            if value is None:
                continue
            replacements.setdefault(placeholder, str(value))

    if not replacements.get("layout_preview.inline"):
        replacements["layout_preview.inline"] = ""

    return replacements


def _fetch_by_path(root: Mapping[str, Any], token: str) -> str | None:
    parts = [part for part in token.split(".") if part]
    current: Any = root
    for part in parts:
        if isinstance(current, Mapping):
            if part in current:
                current = current[part]
                continue
            return None
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            try:
                index = int(part)
            except (TypeError, ValueError):
                return None
            if 0 <= index < len(current):  # type: ignore[arg-type]
                current = current[index]  # type: ignore[index]
                continue
            return None
        return None

    if isinstance(current, (str, int, float, bool)):
        return str(current)
    return None


def _apply(
    text: str,
    replacements: Mapping[str, str],
    state_root: Mapping[str, Any],
    agent_root: Mapping[str, Any],
) -> str:
    def _replace(match: re.Match[str]) -> str:
        token = match.group(1)
        replacement = replacements.get(token)
        if replacement is None:
            replacement = (
                _fetch_by_path(agent_root, token)
                or _fetch_by_path(state_root, token)
            )
        return replacement if replacement is not None else match.group(0)

    text = PLACEHOLDER_RE.sub(_replace, text)
    text = BRACKET_RE.sub(_replace, text)
    return text


def _get_attr_or_key(payload: Any, key: str) -> Any:
    if isinstance(payload, Mapping):
        return payload.get(key)
    return getattr(payload, key, None)


def _set_attr_or_key(payload: Any, key: str, value: Any) -> None:
    if isinstance(payload, MutableMapping):
        payload[key] = value
        return
    if hasattr(payload, key):
        try:
            setattr(payload, key, value)
        except Exception:
            pass


def _iter_text_parts(llm_response: Any) -> Iterable[Any]:
    def _as_sequence(value: Any) -> Sequence[Any]:
        if isinstance(value, Sequence):
            return value
        if isinstance(value, IterableABC):
            return list(value)
        return []

    candidates = _get_attr_or_key(llm_response, "candidates")
    for candidate in _as_sequence(candidates):
        content = _get_attr_or_key(candidate, "content")
        parts = _get_attr_or_key(content, "parts")
        for part in _as_sequence(parts):
            text = _get_attr_or_key(part, "text")
            if isinstance(text, str):
                yield part


def after_model_response_callback(*, callback_context: Any, llm_response: Any) -> None:
    state = _extract_session_state(callback_context)
    if state is None:
        state = get_fallback_session_state()
        logger.debug(
            "after_model_response_callback: utilizando fallback session_state (id=%s).",
            hex(id(state)),
        )
    if logger.isEnabledFor(logging.DEBUG):
        try:
            context_attrs = list(vars(callback_context).keys())
        except Exception:  # pragma: no cover - debug limitado
            context_attrs = []
        logger.debug(
            "after_model_response_callback: context=%s attrs=%s",
            type(callback_context).__name__,
            context_attrs,
        )
        logger.debug(
            "after_model_response_callback: llm_response type=%s keys=%s",
            type(llm_response).__name__,
            list(llm_response.keys()) if isinstance(llm_response, Mapping) else None,
        )
    bucket = get_session_bucket(state)

    replacements = _collect_replacements(bucket, state)
    if not replacements:
        logger.warning(
            "after_model_response_callback: nenhum placeholder encontrado; verifique se generate_layout_preview foi executado."
        )
        return
    logger.debug(
        "after_model_response_callback: %d placeholders disponíveis para substituição.",
        len(replacements),
    )
    if logger.isEnabledFor(logging.DEBUG):
        sample = {k: replacements[k] for k in sorted(replacements) if k.startswith("layout_preview.")}
        logger.debug("after_model_response_callback: amostras de placeholders %s", sample)

    def _recursively_apply(payload: Any, visited: set[int]) -> None:
        marker = id(payload)
        if marker in visited:
            return
        if isinstance(payload, MutableMapping):
            visited.add(marker)
            for key, value in list(payload.items()):
                if isinstance(value, str) and PLACEHOLDER_ANY_RE.search(value):
                    payload[key] = _apply(value, replacements, state, bucket)
                else:
                    _recursively_apply(value, visited)
        elif isinstance(payload, list):
            visited.add(marker)
            for index, value in enumerate(payload):
                if isinstance(value, str) and PLACEHOLDER_ANY_RE.search(value):
                    payload[index] = _apply(value, replacements, state, bucket)
                else:
                    _recursively_apply(value, visited)
        elif hasattr(payload, "__dict__"):
            visited.add(marker)
            for key, value in list(vars(payload).items()):
                if isinstance(value, str) and PLACEHOLDER_ANY_RE.search(value):
                    try:
                        setattr(payload, key, _apply(value, replacements, state, bucket))
                    except Exception:
                        pass
                else:
                    _recursively_apply(value, visited)

    for part in _iter_text_parts(llm_response):
        original = _get_attr_or_key(part, "text")
        if isinstance(original, str) and PLACEHOLDER_ANY_RE.search(original):
            _set_attr_or_key(part, "text", _apply(original, replacements, state, bucket))
            logger.debug("after_model_response_callback: placeholder substituído em parte de candidato.")

    _recursively_apply(llm_response, set())

    texts = _collect_part_texts(llm_response)
    if texts:
        aggregate = "\n".join(texts)
        if PLACEHOLDER_ANY_RE.search(aggregate):
            logger.warning("after_model_response_callback: placeholders remanescentes após substituição.")
        _set_aggregate_text(llm_response, aggregate)
        logger.info(
            "after_model_response_callback: texto agregado atualizado (%d linhas).",
            len(texts),
        )


def _collect_part_texts(llm_response: Any) -> list[str]:
    texts: list[str] = []
    for part in _iter_text_parts(llm_response):
        text = _get_attr_or_key(part, "text")
        if isinstance(text, str):
            texts.append(text)
    return texts


def _set_aggregate_text(llm_response: Any, text: str) -> None:
    if not isinstance(text, str) or not text:
        return
    if isinstance(llm_response, MutableMapping):
        llm_response["text"] = text
        result = llm_response.get("result")
        if isinstance(result, MutableMapping):
            result["output_text"] = text
        elif hasattr(result, "__dict__"):
            try:
                setattr(result, "output_text", text)
            except Exception:
                pass
    elif hasattr(llm_response, "__dict__"):
        try:
            setattr(llm_response, "text", text)
        except Exception:
            pass
