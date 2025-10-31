"""Tool responsável por listar templates disponíveis."""

from __future__ import annotations

import logging

from ..diagramador import (
    SESSION_ARTIFACT_TEMPLATE_LISTING,
    list_templates as _list_templates,
)
from ..diagramador.session import get_session_bucket
from ...utils import coerce_session_state, empty_string_to_none

__all__ = ["SESSION_ARTIFACT_TEMPLATE_LISTING", "list_templates"]

logger = logging.getLogger(__name__)


def list_templates(
    directory: str = "",
    session_state: str = "",
):
    """Wrapper que normaliza parâmetros antes de chamar a implementação base."""

    coerced_state = coerce_session_state(session_state)
    if coerced_state is None:
        logger.debug(
            "list_templates: nenhum session_state recebido; utilizando cache em memória."
        )
        coerced_state = {}
        get_session_bucket(coerced_state)
    normalized_directory = empty_string_to_none(directory)
    logger.info(
        "list_templates: varrendo templates em '%s'.",
        normalized_directory or "<default>",
    )
    return _list_templates(normalized_directory, session_state=coerced_state)
