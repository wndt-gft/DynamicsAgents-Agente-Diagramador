"""Travel planner solution entry package for Google ADK integration."""

from __future__ import annotations

from typing import Any

from dynamic_agents import load_solution_app_module

__all__ = ["app", "root_agent", "run"]


_MODULE = load_solution_app_module(__name__, __file__)
app: Any = getattr(_MODULE, "app")
root_agent: Any = getattr(_MODULE, "root_agent")
run: Any = getattr(_MODULE, "run")
