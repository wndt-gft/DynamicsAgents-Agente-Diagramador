"""Wrapper mínimo para executar o agente com o runtime dinâmico."""

from __future__ import annotations

from typing import Any, Dict, Optional

from dynamic_agents import bootstrap_solution_entrypoints

app, root_agent, _run = bootstrap_solution_entrypoints(__file__)


def run(payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Executa o agente específico usando o runtime compartilhado."""

    return _run(payload)


__all__ = ["app", "root_agent", "run"]
