"""Ponto de entrada do agente Diagramador."""

from __future__ import annotations

import warnings

from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool

from .prompt import ORCHESTRATOR_PROMPT
from .tools.diagramador import (
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


diagramador_agent = Agent(
    model=DEFAULT_MODEL,
    name="diagramador",
    description=diagramador_description,
    instruction=ORCHESTRATOR_PROMPT,
    tools=[
        _make_tool(list_templates),
        _make_tool(describe_template),
        _make_tool(generate_mermaid_preview),
        _make_tool(finalize_datamodel),
        _make_tool(save_datamodel),
        _make_tool(generate_archimate_diagram),
    ],
)


__all__ = ["diagramador_agent"]
