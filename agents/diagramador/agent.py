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
    describe_template,
    finalize_datamodel,
    generate_archimate_diagram,
    generate_mermaid_preview,
    list_templates,
    save_datamodel,
)

warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")


diagramador_description = (
    "Agente orquestrador responsável por interpretar histórias de usuário, "
    "gerar datamodels no padrão ArchiMate e exportar diagramas XML validados."
)


def _make_tool(function):
    tool = FunctionTool(function)
    if getattr(tool, "name", None) in (None, ""):
        tool.name = function.__name__
    return tool


def _list_templates_tool(directory: str = ""):
    """Wrapper to keep the public signature simple for automatic calling."""

    return list_templates(directory or None)


def _describe_template_tool(template_path: str):
    return describe_template(template_path, session_state=None)


def _generate_mermaid_preview_tool(datamodel: str, template_path: str = ""):
    return generate_mermaid_preview(
        datamodel,
        template_path=template_path or None,
        session_state=None,
    )


def _finalize_datamodel_tool(datamodel: str, template_path: str):
    return finalize_datamodel(datamodel, template_path, session_state=None)


def _save_datamodel_tool(
    datamodel: str,
    filename: str = DEFAULT_DATAMODEL_FILENAME,
):
    target = filename or DEFAULT_DATAMODEL_FILENAME
    return save_datamodel(datamodel, target)


def _generate_archimate_diagram_tool(
    model_json_path: str,
    output_filename: str = DEFAULT_DIAGRAM_FILENAME,
    template_path: str = "",
    validate: bool = True,
    xsd_dir: str = "",
):
    target_output = output_filename or DEFAULT_DIAGRAM_FILENAME
    return generate_archimate_diagram(
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
        _make_tool(_list_templates_tool),
        _make_tool(_describe_template_tool),
        _make_tool(_generate_mermaid_preview_tool),
        _make_tool(_finalize_datamodel_tool),
        _make_tool(_save_datamodel_tool),
        _make_tool(_generate_archimate_diagram_tool),
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
