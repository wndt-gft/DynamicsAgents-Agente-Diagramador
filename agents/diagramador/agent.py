"""Ponto de entrada do agente Diagramador."""

from __future__ import annotations

import warnings
from typing import Callable

from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool

from .callbacks import after_model_response_callback
from .prompt import ORCHESTRATOR_PROMPT
from .tools import (
    DEFAULT_MODEL,
    describe_template,
    finalize_datamodel,
    generate_archimate_diagram,
    generate_layout_preview,
    list_templates,
    save_datamodel,
)
from .utils.logging_config import get_logger

warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")

logger = get_logger(__name__)


diagramador_description = (
    "Agente orquestrador responsável por interpretar histórias de usuário, "
    "gerar datamodels no padrão ArchiMate e exportar diagramas XML validados."
)


def _make_tool(function: Callable[..., object], *, name: str | None = None) -> FunctionTool:
    """Cria instâncias de ``FunctionTool`` com nomes estáveis."""

    tool = FunctionTool(function)
    tool_name = name or getattr(function, "__tool_name__", None)
    if getattr(tool, "name", None) in (None, ""):
        tool.name = tool_name or function.__name__
    elif tool_name:
        tool.name = tool_name
    return tool


diagramador_agent = Agent(
    model=DEFAULT_MODEL,
    name="diagramador",
    description=diagramador_description,
    instruction=ORCHESTRATOR_PROMPT,
    after_model_callback=after_model_response_callback,
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
    """Retorna a instância do agente Diagramador."""

    return diagramador_agent


root_agent: Agent = diagramador_agent


__all__ = ["diagramador_agent", "get_root_agent", "root_agent"]
