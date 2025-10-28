"""Utilitários para uso do estado de sessão no agente Diagramador."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, MutableMapping, Optional

SESSION_STATE_ROOT = "diagramador"
BLUEPRINT_CACHE_KEY = "template_blueprints"
PREVIEW_CACHE_KEY = "mermaid_previews"
DATAMODEL_CACHE_KEY = "datamodel_snapshots"

__all__ = [
    "SESSION_STATE_ROOT",
    "BLUEPRINT_CACHE_KEY",
    "get_session_bucket",
    "get_cached_blueprint",
    "store_blueprint",
    "PREVIEW_CACHE_KEY",
    "DATAMODEL_CACHE_KEY",
    "store_preview",
    "get_cached_preview",
    "store_datamodel_snapshot",
    "get_cached_datamodel_snapshot",
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


def store_preview(
    session_state: Optional[MutableMapping[str, Any]],
    preview_id: str,
    payload: Dict[str, Any],
) -> None:
    """Armazena o resultado bruto de um preview Mermaid no estado da sessão."""

    if session_state is None:
        return

    bucket = get_session_bucket(session_state)
    cache = bucket.setdefault(PREVIEW_CACHE_KEY, {})
    if not isinstance(cache, MutableMapping):
        cache = {}
        bucket[PREVIEW_CACHE_KEY] = cache

    cache[preview_id] = copy.deepcopy(payload)


def get_cached_preview(
    session_state: Optional[MutableMapping[str, Any]], preview_id: str
) -> Optional[Dict[str, Any]]:
    """Recupera um preview Mermaid previamente armazenado no estado da sessão."""

    if not preview_id:
        return None

    bucket = get_session_bucket(session_state)
    cache = bucket.get(PREVIEW_CACHE_KEY)
    if not isinstance(cache, MutableMapping):
        return None

    preview = cache.get(preview_id)
    return copy.deepcopy(preview) if isinstance(preview, dict) else None


def store_datamodel_snapshot(
    session_state: Optional[MutableMapping[str, Any]],
    key: str,
    payload: Dict[str, Any],
) -> None:
    """Persiste uma cópia do datamodel associado a um identificador lógico."""

    if session_state is None or not key:
        return

    bucket = get_session_bucket(session_state)
    cache = bucket.setdefault(DATAMODEL_CACHE_KEY, {})
    if not isinstance(cache, MutableMapping):
        cache = {}
        bucket[DATAMODEL_CACHE_KEY] = cache

    cache[key] = copy.deepcopy(payload)


def get_cached_datamodel_snapshot(
    session_state: Optional[MutableMapping[str, Any]], key: str
) -> Optional[Dict[str, Any]]:
    """Recupera um datamodel previamente armazenado no estado da sessão."""

    if not key:
        return None

    bucket = get_session_bucket(session_state)
    cache = bucket.get(DATAMODEL_CACHE_KEY)
    if not isinstance(cache, MutableMapping):
        return None

    payload = cache.get(key)
    return copy.deepcopy(payload) if isinstance(payload, dict) else None
