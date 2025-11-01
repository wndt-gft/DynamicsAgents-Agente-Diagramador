"""Tool para gerar pré-visualizações de layout."""

from __future__ import annotations

from typing import Any

from ..diagramador import (
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
    generate_layout_preview as _generate_layout_preview,
)
from ...utils import (
    empty_string_to_none,
    get_fallback_session_state,
    resolve_tool_session_state,
)
from ...utils.logging_config import get_logger

__all__ = ["SESSION_ARTIFACT_LAYOUT_PREVIEW", "generate_layout_preview"]

logger = get_logger(__name__)


def generate_layout_preview(
    datamodel: str = "",
    template_path: str = "",
    view_filter: str = "",
    session_state: str = "",
    tool_context: Any | None = None,
    **kwargs,
):
    if "tool_context" in kwargs and tool_context is None:
        tool_context = kwargs["tool_context"]
    if "session_state" in kwargs and not session_state:
        session_state = kwargs["session_state"]

    coerced_state = resolve_tool_session_state(session_state, tool_context)
    if coerced_state is None:
        logger.debug(
            "generate_layout_preview: nenhuma session_state compartilhada; utilizando cache isolado."
        )
        coerced_state = get_fallback_session_state()
    else:
        logger.debug(
            "generate_layout_preview: utilizando session_state (id=%s).",
            hex(id(coerced_state)),
        )

    datamodel_payload: Any | None = datamodel
    if isinstance(datamodel, str):
        if not datamodel.strip():
            datamodel_payload = None
        else:
            logger.debug(
                "generate_layout_preview: datamodel textual recebido (%d caracteres).",
                len(datamodel),
            )

    template_payload: Any | None = empty_string_to_none(template_path)
    filter_payload: Any | None = empty_string_to_none(view_filter)

    logger.info(
        "generate_layout_preview: template='%s', filtro='%s'.",
        template_payload or "<default>",
        filter_payload or "<todas>",
    )

    try:
        return _generate_layout_preview(
            datamodel_payload,
            template_path=template_payload,
            session_state=coerced_state,
            view_filter=filter_payload,
        )
    except ValueError as exc:
        logger.exception("generate_layout_preview falhou com datamodel fornecido.", exc_info=exc)
        raise
