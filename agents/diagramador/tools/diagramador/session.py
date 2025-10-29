"""Utilitários para uso do estado de sessão no agente Diagramador."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, Iterable, MutableMapping, Optional

SESSION_STATE_ROOT = "diagramador"
BLUEPRINT_CACHE_KEY = "template_blueprints"
ARTIFACTS_CACHE_KEY = "artifacts"
VIEW_FOCUS_KEY = "view_focus"

__all__ = [
    "SESSION_STATE_ROOT",
    "BLUEPRINT_CACHE_KEY",
    "ARTIFACTS_CACHE_KEY",
    "get_session_bucket",
    "get_cached_blueprint",
    "store_blueprint",
    "get_cached_artifact",
    "store_artifact",
    "get_view_focus",
    "set_view_focus",
]


def get_session_bucket(session_state: Optional[MutableMapping[str, Any]]) -> Dict[str, Any]:
    """Obtém (ou cria) o bucket raiz do agente dentro do estado de sessão."""

    if session_state is None:
        return {}
    if SESSION_STATE_ROOT not in session_state:
        session_state[SESSION_STATE_ROOT] = {}
    bucket = session_state[SESSION_STATE_ROOT]
    if not isinstance(bucket, MutableMapping):
        bucket = {}
        session_state[SESSION_STATE_ROOT] = bucket
    return bucket  # type: ignore[return-value]


def _normalize_template_path(template_path: str | Path) -> str:
    path = Path(template_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return str(path.resolve())


def get_cached_blueprint(
    session_state: Optional[MutableMapping[str, Any]], template_path: str | Path
) -> Optional[Dict[str, Any]]:
    """Recupera o blueprint de template armazenado no estado de sessão."""

    bucket = get_session_bucket(session_state)
    cache = bucket.get(BLUEPRINT_CACHE_KEY)
    if not isinstance(cache, MutableMapping):
        return None
    normalized = _normalize_template_path(template_path)
    blueprint = cache.get(normalized)
    return copy.deepcopy(blueprint) if isinstance(blueprint, dict) else None


def store_blueprint(
    session_state: Optional[MutableMapping[str, Any]],
    template_path: str | Path,
    blueprint: Dict[str, Any],
) -> None:
    """Armazena uma cópia do blueprint de template no estado de sessão."""

    if session_state is None:
        return
    bucket = get_session_bucket(session_state)
    cache = bucket.setdefault(BLUEPRINT_CACHE_KEY, {})
    if not isinstance(cache, MutableMapping):
        cache = {}
        bucket[BLUEPRINT_CACHE_KEY] = cache
    normalized = _normalize_template_path(template_path)
    cache[normalized] = copy.deepcopy(blueprint)


def store_artifact(
    session_state: Optional[MutableMapping[str, Any]],
    key: str,
    payload: Any,
) -> None:
    """Persist a deep copy of an artifact inside the session bucket."""

    if session_state is None:
        return

    bucket = get_session_bucket(session_state)
    artifacts = bucket.setdefault(ARTIFACTS_CACHE_KEY, {})
    if not isinstance(artifacts, MutableMapping):
        artifacts = {}
        bucket[ARTIFACTS_CACHE_KEY] = artifacts

    artifacts[key] = copy.deepcopy(payload)


def get_cached_artifact(
    session_state: Optional[MutableMapping[str, Any]], key: str
) -> Any:
    """Retrieve a deep copy of an artifact stored in the session bucket."""

    if session_state is None:
        return None

    bucket = get_session_bucket(session_state)
    artifacts = bucket.get(ARTIFACTS_CACHE_KEY)
    if not isinstance(artifacts, MutableMapping):
        return None

    payload = artifacts.get(key)
    return copy.deepcopy(payload)


def set_view_focus(
    session_state: Optional[MutableMapping[str, Any]],
    tokens: Iterable[str],
) -> None:
    """Persist normalized view filter tokens into the session bucket."""

    if session_state is None:
        return

    bucket = get_session_bucket(session_state)
    normalized: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        text = str(token).strip()
        if not text:
            continue
        lowered = text.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(lowered)

    if normalized:
        bucket[VIEW_FOCUS_KEY] = normalized
    else:
        bucket.pop(VIEW_FOCUS_KEY, None)


def get_view_focus(
    session_state: Optional[MutableMapping[str, Any]],
) -> list[str]:
    """Return the stored view focus tokens (in lowercase) from the session bucket."""

    if session_state is None:
        return []

    bucket = get_session_bucket(session_state)
    payload = bucket.get(VIEW_FOCUS_KEY)

    if isinstance(payload, list):
        return [str(item).strip().casefold() for item in payload if str(item).strip()]

    if isinstance(payload, str):
        stripped = payload.strip()
        return [stripped.casefold()] if stripped else []

    return []
