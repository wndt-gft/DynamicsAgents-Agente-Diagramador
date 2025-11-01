"""Tool para consolidar o datamodel gerado pelo agente."""

from __future__ import annotations

from ..diagramador import (
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    finalize_datamodel as _finalize_datamodel,
)
from ...utils import get_fallback_session_state, resolve_tool_session_state
from ...utils.logging_config import get_logger

__all__ = ["SESSION_ARTIFACT_FINAL_DATAMODEL", "finalize_datamodel"]

logger = get_logger(__name__)


def finalize_datamodel(
    datamodel: str,
    template_path: str,
    session_state: str = "",
    tool_context: object | None = None,
    **kwargs,
):
    if "tool_context" in kwargs and tool_context is None:
        tool_context = kwargs["tool_context"]
    if "session_state" in kwargs and not session_state:
        session_state = kwargs["session_state"]

    coerced_state = resolve_tool_session_state(session_state, tool_context)
    if coerced_state is None:
        logger.debug(
            "finalize_datamodel: nenhuma session_state compartilhada; utilizando cache isolado."
        )
        coerced_state = get_fallback_session_state()
    else:
        logger.debug(
            "finalize_datamodel: utilizando session_state (id=%s).",
            hex(id(coerced_state)),
        )
    logger.info(
        "finalize_datamodel: consolidando datamodel (len=%d) para template '%s'.",
        len(datamodel or ""),
        template_path or "<default>",
    )
    return _finalize_datamodel(
        datamodel,
        template_path,
        session_state=coerced_state,
    )
