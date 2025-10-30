"""Funções auxiliares para lidar com estado de sessão e parâmetros."""

from __future__ import annotations

import json
import logging
from collections.abc import MutableMapping
from typing import Any

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
