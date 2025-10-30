"""Tool que expõe a descrição detalhada de um template ArchiMate."""

from __future__ import annotations

from typing import Any, MutableMapping

from ..diagramador import (
    SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
    describe_template as _describe_template,
)
from ...utils import coerce_session_state, empty_string_to_none

__all__ = ["SESSION_ARTIFACT_TEMPLATE_GUIDANCE", "describe_template"]


def describe_template(
    template_path: str | None,
    view_filter: str | None,
    session_state: str | MutableMapping[str, Any] | None,
):
    coerced_state = coerce_session_state(session_state)
    filter_payload: Any | None = empty_string_to_none(view_filter)
    return _describe_template(
        empty_string_to_none(template_path),
        view_filter=filter_payload,
        session_state=coerced_state,
    )
