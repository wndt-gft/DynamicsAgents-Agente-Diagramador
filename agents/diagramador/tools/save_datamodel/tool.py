"""Tool que persiste o datamodel em disco."""

from __future__ import annotations

import logging
from typing import Any

from ..diagramador import (
    DEFAULT_DATAMODEL_FILENAME,
    SESSION_ARTIFACT_SAVED_DATAMODEL,
    save_datamodel as _save_datamodel,
)
from ..diagramador.session import get_session_bucket
from ...utils import coerce_session_state, empty_string_to_none

__all__ = ["SESSION_ARTIFACT_SAVED_DATAMODEL", "save_datamodel"]

logger = logging.getLogger(__name__)


def save_datamodel(
    datamodel: str = "",
    filename: str = "",
    session_state: str = "",
):
    target = empty_string_to_none(filename) or DEFAULT_DATAMODEL_FILENAME
    payload: Any | None = datamodel
    if isinstance(datamodel, str):
        if not datamodel.strip():
            payload = None
        else:
            logger.debug("save_datamodel: datamodel textual recebido (%d chars).", len(datamodel))

    coerced_state = coerce_session_state(session_state)
    if coerced_state is None:
        logger.debug(
            "save_datamodel: nenhum session_state recebido; utilizando cache em memória."
        )
        coerced_state = {}
        get_session_bucket(coerced_state)

    logger.info("save_datamodel: persistindo datamodel em '%s'.", target)
    return _save_datamodel(payload, target, session_state=coerced_state)
