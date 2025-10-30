"""Tool para consolidar o datamodel gerado pelo agente."""

from __future__ import annotations

from typing import MutableMapping

from ..diagramador import (
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    finalize_datamodel as _finalize_datamodel,
)
from ...utils import coerce_session_state

__all__ = ["SESSION_ARTIFACT_FINAL_DATAMODEL", "finalize_datamodel"]


def finalize_datamodel(
    datamodel: str,
    template_path: str,
    session_state: str | MutableMapping[str, object] | None,
):
    coerced_state = coerce_session_state(session_state)
    return _finalize_datamodel(
        datamodel,
        template_path,
        session_state=coerced_state,
    )
