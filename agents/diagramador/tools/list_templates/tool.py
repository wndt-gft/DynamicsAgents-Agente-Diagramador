"""Tool responsável por listar templates disponíveis."""

from __future__ import annotations

from ..diagramador import (
    SESSION_ARTIFACT_TEMPLATE_LISTING,
    list_templates as _list_templates,
)
from ...utils import coerce_session_state, empty_string_to_none

__all__ = ["SESSION_ARTIFACT_TEMPLATE_LISTING", "list_templates"]


def list_templates(
    directory: str = "",
    session_state: str = "",
):
    """Wrapper que normaliza parâmetros antes de chamar a implementação base."""

    coerced_state = coerce_session_state(session_state)
    normalized_directory = empty_string_to_none(directory)
    return _list_templates(normalized_directory, session_state=coerced_state)
