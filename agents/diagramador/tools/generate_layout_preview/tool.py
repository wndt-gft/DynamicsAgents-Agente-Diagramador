"""Tool para gerar pré-visualizações de layout."""

from __future__ import annotations

from typing import Any, MutableMapping

from ..diagramador import (
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
    generate_layout_preview as _generate_layout_preview,
)
from ...utils import coerce_session_state, empty_string_to_none

__all__ = ["SESSION_ARTIFACT_LAYOUT_PREVIEW", "generate_layout_preview"]


def generate_layout_preview(
    datamodel: str | None = None,
    template_path: str | None = None,
    view_filter: str | None = None,
    session_state: str | MutableMapping[str, Any] | None = None,
):
    coerced_state = coerce_session_state(session_state)
    datamodel_payload: Any | None = datamodel
    if isinstance(datamodel, str) and not datamodel.strip():
        datamodel_payload = None

    template_payload: Any | None = empty_string_to_none(template_path)
    filter_payload: Any | None = empty_string_to_none(view_filter)

    try:
        return _generate_layout_preview(
            datamodel_payload,
            template_path=template_payload,
            session_state=coerced_state,
            view_filter=filter_payload,
        )
    except ValueError as exc:
        if datamodel_payload is None or coerced_state is None:
            raise
        try:
            return _generate_layout_preview(
                None,
                template_path=template_payload,
                session_state=coerced_state,
                view_filter=filter_payload,
            )
        except Exception:
            raise exc
