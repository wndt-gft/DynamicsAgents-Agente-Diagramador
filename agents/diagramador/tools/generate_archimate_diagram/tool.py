"""Tool para gerar diagramas ArchiMate em XML."""

from __future__ import annotations

from ..diagramador import (
    DEFAULT_DIAGRAM_FILENAME,
    SESSION_ARTIFACT_ARCHIMATE_XML,
    generate_archimate_diagram as _generate_archimate_diagram,
)
from ...utils import (
    empty_string_to_none,
    get_fallback_session_state,
    normalize_bool_flag,
    resolve_tool_session_state,
)
from ...utils.logging_config import get_logger

__all__ = ["SESSION_ARTIFACT_ARCHIMATE_XML", "generate_archimate_diagram"]

logger = get_logger(__name__)


def generate_archimate_diagram(
    model_json_path: str = "",
    output_filename: str = "",
    template_path: str = "",
    validate: str = "",
    xsd_dir: str = "",
    session_state: str = "",
    tool_context: object | None = None,
    **kwargs,
):
    if "tool_context" in kwargs and tool_context is None:
        tool_context = kwargs["tool_context"]
    if "session_state" in kwargs and not session_state:
        session_state = kwargs["session_state"]

    target_output = empty_string_to_none(output_filename) or DEFAULT_DIAGRAM_FILENAME
    coerced_state = resolve_tool_session_state(session_state, tool_context)
    if coerced_state is None:
        logger.debug(
            "generate_archimate_diagram: nenhuma session_state compartilhada; utilizando cache isolado."
        )
        coerced_state = get_fallback_session_state()
    else:
        logger.debug(
            "generate_archimate_diagram: utilizando session_state (id=%s).",
            hex(id(coerced_state)),
        )

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
