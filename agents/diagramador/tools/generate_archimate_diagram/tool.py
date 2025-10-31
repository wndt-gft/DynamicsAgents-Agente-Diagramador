"""Tool para gerar diagramas ArchiMate em XML."""

from __future__ import annotations

import logging

from ..diagramador import (
    DEFAULT_DIAGRAM_FILENAME,
    SESSION_ARTIFACT_ARCHIMATE_XML,
    generate_archimate_diagram as _generate_archimate_diagram,
)
from ..diagramador.session import get_session_bucket
from ...utils import coerce_session_state, empty_string_to_none, normalize_bool_flag

__all__ = ["SESSION_ARTIFACT_ARCHIMATE_XML", "generate_archimate_diagram"]

logger = logging.getLogger(__name__)


def generate_archimate_diagram(
    model_json_path: str = "",
    output_filename: str = "",
    template_path: str = "",
    validate: str = "",
    xsd_dir: str = "",
    session_state: str = "",
):
    target_output = empty_string_to_none(output_filename) or DEFAULT_DIAGRAM_FILENAME
    coerced_state = coerce_session_state(session_state)
    if coerced_state is None:
        logger.debug(
            "generate_archimate_diagram: nenhum session_state recebido; utilizando cache em memória."
        )
        coerced_state = {}
        get_session_bucket(coerced_state)

    validate_flag = normalize_bool_flag(validate)
    if validate_flag is None:
        validate_flag = True

    logger.info(
        "generate_archimate_diagram: template='%s', datamodel='%s', validar=%s, saída='%s'.",
        template_path or "<default>",
        model_json_path or "<session>",
        validate_flag,
        target_output,
    )

    return _generate_archimate_diagram(
        empty_string_to_none(model_json_path),
        output_filename=target_output,
        template_path=empty_string_to_none(template_path),
        validate=validate_flag,
        xsd_dir=empty_string_to_none(xsd_dir),
        session_state=coerced_state,
    )
