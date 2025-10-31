"""Callback pós-resposta responsável por substituir placeholders de sessão."""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from typing import Any, Iterable

from ..tools.diagramador import (
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
    SESSION_STATE_ROOT,
)

PLACEHOLDER_RE = re.compile(r"\{\{\s*(?:session\.)?state\.([A-Za-z0-9_.-]+)\s*\}\}")
BRACKET_RE = re.compile(r"\[\[\s*(?:session\.)?state\.([A-Za-z0-9_.-]+)\s*\]\]")

__all__ = ["after_model_response_callback"]


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

    return None


def _collect_replacements(bucket: Mapping[str, Any]) -> dict[str, str]:
    artifacts = bucket.get("artifacts")
    replacements: dict[str, str] = {}
    if not isinstance(artifacts, Mapping):
        return replacements

    for artifact_key in (SESSION_ARTIFACT_LAYOUT_PREVIEW,):
        artifact = artifacts.get(artifact_key)
        if not isinstance(artifact, Mapping):
            continue
        mapping = artifact.get("replacements")
        if not isinstance(mapping, Mapping):
            continue
        for placeholder, value in mapping.items():
            if value is None:
                continue
            replacements[str(placeholder)] = str(value)

    return replacements


def _apply(text: str, replacements: Mapping[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        token = match.group(1)
        return replacements.get(token, match.group(0))

    text = PLACEHOLDER_RE.sub(_replace, text)
    text = BRACKET_RE.sub(_replace, text)
    return text


def _iter_text_parts(llm_response: Mapping[str, Any]) -> Iterable[MutableMapping[str, Any]]:
    for candidate in llm_response.get("candidates", []):
        if not isinstance(candidate, Mapping):
            continue
        content = candidate.get("content")
        if not isinstance(content, Mapping):
            continue
        for part in content.get("parts", []):
            if isinstance(part, MutableMapping) and isinstance(part.get("text"), str):
                yield part


def after_model_response_callback(*, callback_context: Any, llm_response: Any) -> None:
    state = _extract_session_state(callback_context)
    if state is None:
        return

    bucket = state.get(SESSION_STATE_ROOT)
    if not isinstance(bucket, Mapping):
        return

    replacements = _collect_replacements(bucket)
    if not replacements:
        return

    for part in _iter_text_parts(llm_response if isinstance(llm_response, Mapping) else {}):
        original = part.get("text")
        if isinstance(original, str):
            part["text"] = _apply(original, replacements)
