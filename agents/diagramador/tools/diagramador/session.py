"""Utilitários para uso do estado de sessão no agente Diagramador."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, MutableMapping, Optional

SESSION_STATE_ROOT = "diagramador"
BLUEPRINT_CACHE_KEY = "template_blueprints"
PREVIEW_CACHE_KEY = "mermaid_previews"

__all__ = [
    "SESSION_STATE_ROOT",
    "BLUEPRINT_CACHE_KEY",
    "get_session_bucket",
    "get_cached_blueprint",
    "store_blueprint",
    "PREVIEW_CACHE_KEY",
    "store_preview",
    "get_cached_preview",
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
