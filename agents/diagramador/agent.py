"""Ponto de entrada do agente Diagramador."""

from __future__ import annotations

import json
import logging
import warnings
from collections.abc import MutableMapping
from typing import Any

from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool

from .prompt import ORCHESTRATOR_PROMPT
from .tools.diagramador import (
    DEFAULT_DATAMODEL_FILENAME,
    DEFAULT_DIAGRAM_FILENAME,
    DEFAULT_MODEL,
    describe_template as _describe_template,
    finalize_datamodel as _finalize_datamodel,
    generate_archimate_diagram as _generate_archimate_diagram,
    generate_layout_preview as _generate_layout_preview,
    load_layout_preview as _load_layout_preview,
    list_templates as _list_templates,
    save_datamodel as _save_datamodel,
)

warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")


diagramador_description = (
    "Agente orquestrador responsável por interpretar histórias de usuário, "
    "gerar datamodels no padrão ArchiMate e exportar diagramas XML validados."
)


logger = logging.getLogger(__name__)


def _coerce_session_state(session_state: Any) -> MutableMapping[str, Any] | None:
    """Normaliza o estado de sessão recebido pela ADK."""

    if session_state is None:
        return None

    if isinstance(session_state, MutableMapping):
        return session_state

    if isinstance(session_state, str):
        payload = session_state.strip()
        if not payload:
            return None
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Falha ao decodificar session_state fornecido como string.")
            return None
        if isinstance(decoded, MutableMapping):
            return decoded
        logger.warning(
            "session_state string decodificada não representa um mapeamento: %s",
            type(decoded).__name__,
        )
        return None

    logger.warning(
        "Tipo de session_state não suportado recebido (%s); será ignorado.",
        type(session_state).__name__,
    )
    return None


def _make_tool(function, *, name: str | None = None):
    tool = FunctionTool(function)
    tool_name = name or getattr(function, "__tool_name__", None)
    if getattr(tool, "name", None) in (None, ""):
        tool.name = tool_name or function.__name__
    elif tool_name:
        tool.name = tool_name
    return tool


def _empty_string_to_none(value: Any) -> Any | None:
    """Converte strings vazias em ``None`` mantendo outros valores inalterados."""

    if value is None:
        return None

    if isinstance(value, str):
        if not value.strip():
            return None
        return value

    return value


def _normalize_bool_flag(value: Any) -> bool | None:
    """Interpreta strings vindas da orquestração como sinalizadores booleanos."""

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().casefold()
        if not normalized or normalized in {"none", "null", "default"}:
            return None
        if normalized in {"true", "1", "yes", "sim"}:
            return True
        if normalized in {"false", "0", "no", "nao", "não"}:
            return False

    return None


def list_templates(directory: str, session_state: str):
    """Wrapper to keep the public signature simple for automatic calling."""

    coerced_state = _coerce_session_state(session_state)
    normalized_directory: Any | None = _empty_string_to_none(directory)
    return _list_templates(normalized_directory, session_state=coerced_state)


def describe_template(
    template_path: str,
    view_filter: str,
    session_state: str,
):
    coerced_state = _coerce_session_state(session_state)
    filter_payload: Any | None = _empty_string_to_none(view_filter)
    return _describe_template(
        template_path,
        view_filter=filter_payload,
        session_state=coerced_state,
    )


def generate_layout_preview(
    datamodel: str,
    template_path: str,
    view_filter: str,
    session_state: str,
):
    coerced_state = _coerce_session_state(session_state)
    datamodel_payload: Any | None = datamodel
    if isinstance(datamodel, str) and not datamodel.strip():
        datamodel_payload = None

    template_payload: Any | None = _empty_string_to_none(template_path)
    filter_payload: Any | None = _empty_string_to_none(view_filter)

    return _generate_layout_preview(
        datamodel_payload,
        template_path=template_payload,
        session_state=coerced_state,
        view_filter=filter_payload,
    )


def load_layout_preview(
    view_filter: str,
    session_state: str,
):
    coerced_state = _coerce_session_state(session_state)
    filter_payload: Any | None = _empty_string_to_none(view_filter)
    return _load_layout_preview(
        view_filter=filter_payload,
        session_state=coerced_state,
    )


def finalize_datamodel(
    datamodel: str,
    template_path: str,
    session_state: str,
):
    coerced_state = _coerce_session_state(session_state)
    return _finalize_datamodel(
        datamodel,
        template_path,
        session_state=coerced_state,
    )


def save_datamodel(
    datamodel: str,
    filename: str,
    session_state: str,
):
    target = _empty_string_to_none(filename) or DEFAULT_DATAMODEL_FILENAME
    payload: Any | None = datamodel
    if isinstance(datamodel, str) and not datamodel.strip():
        payload = None
    coerced_state = _coerce_session_state(session_state)
    return _save_datamodel(payload, target, session_state=coerced_state)


def generate_archimate_diagram(
    model_json_path: str,
    output_filename: str,
    template_path: str,
    validate: str,
    xsd_dir: str,
    session_state: str,
):
    target_output = _empty_string_to_none(output_filename) or DEFAULT_DIAGRAM_FILENAME
    coerced_state = _coerce_session_state(session_state)
    validate_flag = _normalize_bool_flag(validate)
    if validate_flag is None:
        validate_flag = True
    return _generate_archimate_diagram(
        _empty_string_to_none(model_json_path),
        output_filename=target_output,
        template_path=_empty_string_to_none(template_path),
        validate=validate_flag,
        xsd_dir=_empty_string_to_none(xsd_dir),
        session_state=coerced_state,
    )


diagramador_agent = Agent(
    model=DEFAULT_MODEL,
    name="diagramador",
    description=diagramador_description,
    instruction=ORCHESTRATOR_PROMPT,
    tools=[
        _make_tool(list_templates, name="list_templates"),
        _make_tool(describe_template, name="describe_template"),
        _make_tool(generate_layout_preview, name="generate_layout_preview"),
        _make_tool(load_layout_preview, name="load_layout_preview"),
        _make_tool(finalize_datamodel, name="finalize_datamodel"),
        _make_tool(save_datamodel, name="save_datamodel"),
        _make_tool(
            generate_archimate_diagram,
            name="generate_archimate_diagram",
        ),
    ],
)


def get_root_agent() -> Agent:
    """Return the Diagramador agent instance.

    Provided for compatibility with integrations that expect a callable
    accessor while also exposing ``root_agent`` as a module-level variable for
    the Google ADK loader.
    """

    return diagramador_agent


root_agent: Agent = diagramador_agent


__all__ = ["diagramador_agent", "get_root_agent", "root_agent"]
