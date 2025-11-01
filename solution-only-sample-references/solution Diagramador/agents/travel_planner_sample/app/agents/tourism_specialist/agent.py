"""Wrapper mínimo para executar o agente com o runtime dinâmico."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from dynamic_agents import DynamicAgentRuntime

_FILE_PATH = Path(__file__).resolve()
_SOLUTION_ROOT = next(parent for parent in _FILE_PATH.parents if (parent / "runtime.yaml").exists())
_RUNTIME = DynamicAgentRuntime(_SOLUTION_ROOT)
_SOLUTION_NAME = _SOLUTION_ROOT.name


def _resolve_agent_name() -> str:
    parent = _FILE_PATH.parent
    if parent == _SOLUTION_ROOT:
        descriptor = _RUNTIME.get_solution(_SOLUTION_NAME)
        return descriptor.entrypoint_agent or parent.name
    return parent.name


_AGENT_NAME = _resolve_agent_name()


def run(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Executa o agente específico usando o runtime compartilhado."""

    return _RUNTIME.run(_SOLUTION_NAME, agent_name=_AGENT_NAME, payload=payload)


__all__ = ["run"]
