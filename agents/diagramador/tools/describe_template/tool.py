"""Tool que expõe a descrição detalhada de um template ArchiMate."""

from __future__ import annotations

import logging

from ..diagramador import (
    SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
    describe_template as _describe_template,
)
from ..diagramador.session import get_session_bucket
from ...utils import coerce_session_state, empty_string_to_none

__all__ = ["SESSION_ARTIFACT_TEMPLATE_GUIDANCE", "describe_template"]

logger = logging.getLogger(__name__)


def describe_template(
    template_path: str = "",
    view_filter: str = "",
    session_state: str = "",
):
    coerced_state = coerce_session_state(session_state)
    if coerced_state is None:
        logger.debug(
            "describe_template: nenhum session_state recebido; utilizando cache em memória."
        )
        coerced_state = {}
        get_session_bucket(coerced_state)
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
