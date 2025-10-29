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
    list_templates as _list_templates,
    save_datamodel as _save_datamodel,
)

warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")


diagramador_description = (
    "Agente orquestrador responsável por interpretar histórias de usuário, "
    "gerar datamodels no padrão ArchiMate e exportar diagramas XML validados."
)


logger = logging.getLogger(__name__)


def _coerce_session_state(
    session_state: Any,
) -> tuple[MutableMapping[str, Any] | None, bool]:
    """Normalize session state payloads for tool execution.

    Returns a tuple with the coerced mapping (or ``None``) and a flag indicating
    whether the state should be serialized back in the tool response.
    """

    if session_state is None:
        # Cria um bucket vazio para garantir que as tools possam armazenar
        # resultados no estado de sessão mesmo quando o chamador não forneceu
        # explicitamente um dicionário. Isso mantém as respostas concisas,
        # pois os dados volumosos serão persistidos no estado e não retornados
        # diretamente ao LLM.
        return {}, True

    if isinstance(session_state, MutableMapping):
        return session_state, False

    if isinstance(session_state, str):
        payload = session_state.strip()
        if not payload:
            return {}, True
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Falha ao decodificar session_state fornecido como string.")
            return {}, True
        if isinstance(decoded, MutableMapping):
            return decoded, True
        logger.warning(
            "session_state string decodificada não representa um mapeamento: %s",
            type(decoded).__name__,
        )
        return {}, True

    logger.warning(
        "Tipo de session_state não suportado recebido (%s); será ignorado.",
        type(session_state).__name__,
    )
    return None, True


def _attach_session_state(
    result: Any,
    session_state: MutableMapping[str, Any] | None,
    should_serialize: bool,
) -> Any:
    """Embed the (possibly updated) session state in the tool response."""

    if not should_serialize or session_state is None:
        return result

    try:
        serialized = json.dumps(session_state)
    except TypeError:
        logger.warning(
            "Não foi possível serializar o session_state para retorno; ignorando."
        )
        return result

    if isinstance(result, dict):
        result = dict(result)
        result.setdefault("session_state", serialized)

    return result


def _make_tool(function, *, name: str | None = None):
    tool = FunctionTool(function)
    tool_name = name or getattr(function, "__tool_name__", None)
    if getattr(tool, "name", None) in (None, ""):
        tool.name = tool_name or function.__name__
    elif tool_name:
        tool.name = tool_name
    return tool


def list_templates(directory: str = "", session_state: str = ""):
    """Wrapper to keep the public signature simple for automatic calling."""

    coerced_state, should_serialize = _coerce_session_state(session_state)
    result = _list_templates(directory or None, session_state=coerced_state)
    return _attach_session_state(result, coerced_state, should_serialize)


def describe_template(
    template_path: str,
    view_filter: str = "",
    session_state: str = "",
):
    coerced_state, should_serialize = _coerce_session_state(session_state)
    filter_payload = view_filter or None
    result = _describe_template(
        template_path,
        view_filter=filter_payload,
        session_state=coerced_state,
    )
    return _attach_session_state(result, coerced_state, should_serialize)


def generate_layout_preview(
    datamodel: str = "",
    template_path: str = "",
    *,
    view_filter: str = "",
    session_state: str = "",
):
    coerced_state, should_serialize = _coerce_session_state(session_state)
    filter_payload: Any | None
    if not view_filter:
        filter_payload = None
    else:
        filter_payload = view_filter

    result = _generate_layout_preview(
        datamodel or None,
        template_path=template_path or None,
        session_state=coerced_state,
        view_filter=filter_payload,
    )
    return _attach_session_state(result, coerced_state, should_serialize)


def finalize_datamodel(
    datamodel: str,
    template_path: str,
    session_state: str = "",
):
    coerced_state, should_serialize = _coerce_session_state(session_state)
    result = _finalize_datamodel(
        datamodel,
        template_path,
        session_state=coerced_state,
    )
    return _attach_session_state(result, coerced_state, should_serialize)


def save_datamodel(
    datamodel: str = "",
    filename: str = DEFAULT_DATAMODEL_FILENAME,
    session_state: str = "",
):
    target = filename or DEFAULT_DATAMODEL_FILENAME
    payload: Any | None = datamodel or None
    coerced_state, should_serialize = _coerce_session_state(session_state)
    result = _save_datamodel(payload, target, session_state=coerced_state)
    return _attach_session_state(result, coerced_state, should_serialize)


def generate_archimate_diagram(
    model_json_path: str = "",
    output_filename: str = DEFAULT_DIAGRAM_FILENAME,
    template_path: str = "",
    validate: bool = True,
    xsd_dir: str = "",
    session_state: str = "",
):
    target_output = output_filename or DEFAULT_DIAGRAM_FILENAME
    coerced_state, should_serialize = _coerce_session_state(session_state)
    result = _generate_archimate_diagram(
        model_json_path or None,
        output_filename=target_output,
        template_path=template_path or None,
        validate=validate,
        xsd_dir=xsd_dir or None,
        session_state=coerced_state,
    )
    return _attach_session_state(result, coerced_state, should_serialize)


diagramador_agent = Agent(
    model=DEFAULT_MODEL,
    name="diagramador",
    description=diagramador_description,
    instruction=ORCHESTRATOR_PROMPT,
    tools=[
        _make_tool(list_templates, name="list_templates"),
        _make_tool(describe_template, name="describe_template"),
        _make_tool(generate_layout_preview, name="generate_layout_preview"),
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
