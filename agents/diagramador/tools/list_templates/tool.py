"""Tool responsável por listar templates disponíveis."""

from __future__ import annotations

from ..diagramador import (
    SESSION_ARTIFACT_TEMPLATE_LISTING,
    list_templates as _list_templates,
)
from ..diagramador.session import get_session_bucket
from ...utils import (
    empty_string_to_none,
    get_fallback_session_state,
    resolve_tool_session_state,
)
from ...utils.logging_config import get_logger

__all__ = ["SESSION_ARTIFACT_TEMPLATE_LISTING", "list_templates"]

logger = get_logger(__name__)


def list_templates(
    directory: str = "",
    session_state: str = "",
    tool_context: object | None = None,
    **kwargs,
):
    """Wrapper que normaliza parâmetros antes de chamar a implementação base."""

    if "tool_context" in kwargs and tool_context is None:
        tool_context = kwargs["tool_context"]
    if "session_state" in kwargs and not session_state:
        session_state = kwargs["session_state"]

    coerced_state = resolve_tool_session_state(session_state, tool_context)
    if coerced_state is None:
        logger.debug(
            "list_templates: nenhuma session_state compartilhada; utilizando cache isolado."
        )
        coerced_state = get_fallback_session_state()
    else:
        logger.debug(
            "list_templates: trabalhando com session_state mutável (id=%s).",
            hex(id(coerced_state)),
        )

    normalized_directory = empty_string_to_none(directory)
    logger.info(
        "list_templates: varrendo templates em '%s'.",
        normalized_directory or "<default>",
    )
    return _list_templates(normalized_directory, session_state=coerced_state)
