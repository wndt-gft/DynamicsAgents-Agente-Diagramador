"""Funções auxiliares para lidar com estado de sessão e parâmetros."""

from __future__ import annotations

import json
import logging
from collections.abc import MutableMapping
from typing import Any

from ..tools.diagramador.session import (
    _FALLBACK_SESSION_STATE,  # type: ignore[attr-defined]
    get_session_bucket,
)

logger = logging.getLogger(__name__)


def coerce_session_state(session_state: Any) -> MutableMapping[str, Any] | None:
    """Normaliza ``session_state`` recebido via ADK ou chamadas externas."""

    if session_state is None:
        return None

    if isinstance(session_state, MutableMapping):
        return session_state

    if isinstance(session_state, str):
        payload = session_state.strip()
        if not payload:
            return None
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Falha ao decodificar session_state fornecido como string.")
            return None
        if isinstance(decoded, MutableMapping):
            return decoded
        logger.warning(
            "session_state string decodificada não representa um mapeamento: %s",
            type(decoded).__name__,
        )
        return None

    logger.warning(
        "Tipo de session_state não suportado recebido (%s); será ignorado.",
        type(session_state).__name__,
    )
    return None


def resolve_tool_session_state(
    session_state: Any,
    tool_context: Any,
) -> MutableMapping[str, Any] | None:
    """Resolve o estado de sessão a partir dos argumentos ou do ``tool_context``.

    Prioriza o estado explícito recebido; caso ausente tenta utilizar o contexto
    do ADK, que expõe ``session_state`` para tools.
    """

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "resolve_tool_session_state: raw session_state type=%s; tool_context=%s",
            type(session_state).__name__,
            type(tool_context).__name__ if tool_context is not None else None,
        )

    state = coerce_session_state(session_state)
    if state is not None:
        return state

    if tool_context is None:
        return None

    candidate = getattr(tool_context, "session_state", None)
    if isinstance(candidate, MutableMapping):
        return candidate

    if candidate is not None:
        logger.debug(
            "resolve_tool_session_state: session_state no tool_context não é mapeamento (%s).",
            type(candidate).__name__,
        )
    return None


def get_fallback_session_state() -> MutableMapping[str, Any]:
    """Retorna o estado de sessão global utilizado como fallback."""

    get_session_bucket(None)
    return _FALLBACK_SESSION_STATE  # type: ignore[return-value]


def empty_string_to_none(value: Any) -> Any | None:
    """Converte strings vazias em ``None`` mantendo outros valores inalterados."""

    if value is None:
        return None

    if isinstance(value, str):
        if not value.strip():
            return None
        return value

    return value


def normalize_bool_flag(value: Any) -> bool | None:
    """Interpreta ``value`` como booleano quando possível."""

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().casefold()
        if not normalized or normalized in {"none", "null", "default"}:
            return None
        if normalized in {"true", "1", "yes", "sim"}:
            return True
        if normalized in {"false", "0", "no", "nao", "não"}:
            return False

    return None


__all__ = ["coerce_session_state", "empty_string_to_none", "normalize_bool_flag"]
__all__ += ["resolve_tool_session_state", "get_fallback_session_state"]
