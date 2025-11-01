"""Tool que persiste o datamodel em disco."""

from __future__ import annotations

from typing import Any

from ..diagramador import (
    DEFAULT_DATAMODEL_FILENAME,
    SESSION_ARTIFACT_SAVED_DATAMODEL,
    save_datamodel as _save_datamodel,
)
from ...utils import (
    empty_string_to_none,
    get_fallback_session_state,
    resolve_tool_session_state,
)
from ...utils.logging_config import get_logger

__all__ = ["SESSION_ARTIFACT_SAVED_DATAMODEL", "save_datamodel"]

logger = get_logger(__name__)


def save_datamodel(
    datamodel: str = "",
    filename: str = "",
    session_state: str = "",
    tool_context: object | None = None,
    **kwargs,
):
    if "tool_context" in kwargs and tool_context is None:
        tool_context = kwargs["tool_context"]
    if "session_state" in kwargs and not session_state:
        session_state = kwargs["session_state"]

    target = empty_string_to_none(filename) or DEFAULT_DATAMODEL_FILENAME
    payload: Any | None = datamodel
    if isinstance(datamodel, str):
        if not datamodel.strip():
            payload = None
        else:
            logger.debug("save_datamodel: datamodel textual recebido (%d chars).", len(datamodel))

    coerced_state = resolve_tool_session_state(session_state, tool_context)
    if coerced_state is None:
        logger.debug(
            "save_datamodel: nenhuma session_state compartilhada; utilizando cache isolado."
        )
        coerced_state = get_fallback_session_state()
    else:
        logger.debug(
            "save_datamodel: utilizando session_state (id=%s).",
            hex(id(coerced_state)),
        )

    logger.info("save_datamodel: persistindo datamodel em '%s'.", target)
    return _save_datamodel(payload, target, session_state=coerced_state)
