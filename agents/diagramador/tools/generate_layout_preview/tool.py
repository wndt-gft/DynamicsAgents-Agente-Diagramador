"""Tool para gerar pré-visualizações de layout."""

from __future__ import annotations

import logging
from typing import Any

from ..diagramador import (
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
    generate_layout_preview as _generate_layout_preview,
)
from ..diagramador.session import get_session_bucket
from ...utils import coerce_session_state, empty_string_to_none

__all__ = ["SESSION_ARTIFACT_LAYOUT_PREVIEW", "generate_layout_preview"]

logger = logging.getLogger(__name__)


def generate_layout_preview(
    datamodel: str = "",
    template_path: str = "",
    view_filter: str = "",
    session_state: str = "",
):
    coerced_state = coerce_session_state(session_state)
    if coerced_state is None:
        logger.debug(
            "generate_layout_preview: nenhum session_state recebido; utilizando cache em memória."
        )
        coerced_state = {}
        get_session_bucket(coerced_state)

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
        if datamodel_payload is None:
            logger.exception("generate_layout_preview falhou sem datamodel.", exc_info=exc)
            raise
        logger.debug(
            "generate_layout_preview: tentativa de fallback sem datamodel após erro: %s",
            exc,
        )
        return _generate_layout_preview(
            None,
            template_path=template_payload,
            session_state=coerced_state,
            view_filter=filter_payload,
        )
