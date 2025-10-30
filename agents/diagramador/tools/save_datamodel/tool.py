"""Tool que persiste o datamodel em disco."""

from __future__ import annotations

from typing import Any, MutableMapping

from ..diagramador import (
    DEFAULT_DATAMODEL_FILENAME,
    SESSION_ARTIFACT_SAVED_DATAMODEL,
    save_datamodel as _save_datamodel,
)
from ...utils import coerce_session_state, empty_string_to_none

__all__ = ["SESSION_ARTIFACT_SAVED_DATAMODEL", "save_datamodel"]


def save_datamodel(
    datamodel: str | None = None,
    filename: str | None = None,
    session_state: str | MutableMapping[str, Any] | None = None,
):
    target = empty_string_to_none(filename) or DEFAULT_DATAMODEL_FILENAME
    payload: Any | None = datamodel
    if isinstance(datamodel, str) and not datamodel.strip():
        payload = None
    coerced_state = coerce_session_state(session_state)
    return _save_datamodel(payload, target, session_state=coerced_state)
