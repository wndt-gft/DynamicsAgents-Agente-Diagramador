"""Tool que expõe a descrição detalhada de um template ArchiMate."""

from __future__ import annotations

from ..diagramador import (
    SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
    describe_template as _describe_template,
)
from ..diagramador.session import get_session_bucket
from ...utils import (
    empty_string_to_none,
    get_fallback_session_state,
    resolve_tool_session_state,
)
from ...utils.logging_config import get_logger

__all__ = ["SESSION_ARTIFACT_TEMPLATE_GUIDANCE", "describe_template"]

logger = get_logger(__name__)


def describe_template(
    template_path: str = "",
    view_filter: str = "",
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
            "describe_template: nenhuma session_state compartilhada; utilizando cache isolado."
        )
        coerced_state = get_fallback_session_state()
    else:
        logger.debug(
            "describe_template: utilizando session_state (id=%s).",
            hex(id(coerced_state)),
        )
    filter_payload = empty_string_to_none(view_filter)
    resolved_template = empty_string_to_none(template_path)
    logger.info(
        "describe_template: template='%s', filtro='%s'.",
        resolved_template or "<default>",
        filter_payload or "<todas>",
    )
    return _describe_template(
        resolved_template,
        view_filter=filter_payload,
        session_state=coerced_state,
    )
