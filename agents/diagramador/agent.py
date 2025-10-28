"""Ponto de entrada do agente Diagramador."""

from __future__ import annotations

import warnings

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
    generate_mermaid_preview as _generate_mermaid_preview,
    list_templates as _list_templates,
    save_datamodel as _save_datamodel,
)

warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")


diagramador_description = (
    "Agente orquestrador responsável por interpretar histórias de usuário, "
    "gerar datamodels no padrão ArchiMate e exportar diagramas XML validados."
)


def _make_tool(function, *, name: str | None = None):
    tool = FunctionTool(function)
    tool_name = name or getattr(function, "__tool_name__", None)
    if getattr(tool, "name", None) in (None, ""):
        tool.name = tool_name or function.__name__
    elif tool_name:
        tool.name = tool_name
    return tool


def list_templates(directory: str = ""):
    """Wrapper to keep the public signature simple for automatic calling."""

    return _list_templates(directory or None)


def describe_template(template_path: str):
    return _describe_template(template_path, session_state=None)


def generate_mermaid_preview(datamodel: str, template_path: str = ""):
    return _generate_mermaid_preview(
        datamodel,
        template_path=template_path or None,
        session_state=None,
    )


def finalize_datamodel(datamodel: str, template_path: str):
    return _finalize_datamodel(datamodel, template_path, session_state=None)


def save_datamodel(
    datamodel: str,
    filename: str = DEFAULT_DATAMODEL_FILENAME,
):
    target = filename or DEFAULT_DATAMODEL_FILENAME
    return _save_datamodel(datamodel, target)


def generate_archimate_diagram(
    model_json_path: str,
    output_filename: str = DEFAULT_DIAGRAM_FILENAME,
    template_path: str = "",
    validate: bool = True,
    xsd_dir: str = "",
):
    target_output = output_filename or DEFAULT_DIAGRAM_FILENAME
    return _generate_archimate_diagram(
        model_json_path,
        output_filename=target_output,
        template_path=template_path or None,
        validate=validate,
        xsd_dir=xsd_dir or None,
    )


diagramador_agent = Agent(
    model=DEFAULT_MODEL,
    name="diagramador",
    description=diagramador_description,
    instruction=ORCHESTRATOR_PROMPT,
    tools=[
        _make_tool(list_templates, name="list_templates"),
        _make_tool(describe_template, name="describe_template"),
        _make_tool(generate_mermaid_preview, name="generate_mermaid_preview"),
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
