"""Tool para gerar diagramas ArchiMate em XML."""

from __future__ import annotations

from typing import MutableMapping

from ..diagramador import (
    DEFAULT_DIAGRAM_FILENAME,
    SESSION_ARTIFACT_ARCHIMATE_XML,
    generate_archimate_diagram as _generate_archimate_diagram,
)
from ...utils import coerce_session_state, empty_string_to_none, normalize_bool_flag

__all__ = ["SESSION_ARTIFACT_ARCHIMATE_XML", "generate_archimate_diagram"]


def generate_archimate_diagram(
    model_json_path: str | None,
    output_filename: str | None,
    template_path: str | None,
    validate: str | bool | None,
    xsd_dir: str | None,
    session_state: str | MutableMapping[str, object] | None,
):
    target_output = empty_string_to_none(output_filename) or DEFAULT_DIAGRAM_FILENAME
    coerced_state = coerce_session_state(session_state)
    validate_flag = normalize_bool_flag(validate)
    if validate_flag is None:
        validate_flag = True
    return _generate_archimate_diagram(
        empty_string_to_none(model_json_path),
        output_filename=target_output,
        template_path=empty_string_to_none(template_path),
        validate=validate_flag,
        xsd_dir=empty_string_to_none(xsd_dir),
        session_state=coerced_state,
    )
