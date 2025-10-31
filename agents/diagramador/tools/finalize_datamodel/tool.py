"""Tool para consolidar o datamodel gerado pelo agente."""

from __future__ import annotations

import logging

from ..diagramador import (
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    finalize_datamodel as _finalize_datamodel,
)
from ..diagramador.session import get_session_bucket
from ...utils import coerce_session_state

__all__ = ["SESSION_ARTIFACT_FINAL_DATAMODEL", "finalize_datamodel"]

logger = logging.getLogger(__name__)


def finalize_datamodel(
    datamodel: str,
    template_path: str,
    session_state: str = "",
):
    coerced_state = coerce_session_state(session_state)
    if coerced_state is None:
        logger.debug(
            "finalize_datamodel: nenhum session_state recebido; utilizando cache em memória."
        )
        coerced_state = {}
        get_session_bucket(coerced_state)
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
