"""Integração opcional do Diagramador com o Vertex AI Agent Engine."""

from __future__ import annotations

import logging
from typing import Any

from vertexai.agent_engines.templates.adk import AdkApp

from .agent import root_agent


class DiagramadorAgentEngineApp(AdkApp):
    """Aplicação ADK especializada para o agente Diagramador."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(agent=root_agent, **kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)

    def register_operations(self) -> dict[str, list[str]]:
        """Registra operações padrão e permite extensões futuras."""

        operations = super().register_operations()
        operations.setdefault("", [])
        return operations


__all__ = ["DiagramadorAgentEngineApp"]
