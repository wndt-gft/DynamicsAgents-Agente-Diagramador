"""Ponto de entrada do agente Diagramador."""

from __future__ import annotations

import warnings

from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool

from prompt import ORCHESTRATOR_PROMPT
from tools.diagramador import (
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


diagramador_agent = Agent(
    model=DEFAULT_MODEL,
    name="diagramador",
    description=diagramador_description,
    instruction=ORCHESTRATOR_PROMPT,
    tools=[
        FunctionTool(list_templates, name="list_templates"),
        FunctionTool(describe_template, name="describe_template"),
        FunctionTool(generate_mermaid_preview, name="generate_mermaid_preview"),
        FunctionTool(finalize_datamodel, name="finalize_datamodel"),
        FunctionTool(save_datamodel, name="save_datamodel"),
        FunctionTool(generate_archimate_diagram, name="generate_archimate_diagram"),
    ],
)


__all__ = ["diagramador_agent"]
