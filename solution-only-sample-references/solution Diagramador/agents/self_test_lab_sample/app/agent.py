"""Exports the Self-Test Lab app built from the workflow definition."""

from __future__ import annotations

from typing import Any, Dict, Optional

from dynamic_agents import bootstrap_solution_entrypoints

app, root_agent, _run = bootstrap_solution_entrypoints(__file__)


def run(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _run(payload)


__all__ = ["app", "root_agent", "run"]
