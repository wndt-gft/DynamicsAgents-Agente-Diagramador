"""Stubs mínimos para o pacote `google.adk`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass
class Agent:
    model: str
    name: str
    description: str
    instruction: str
    tools: Iterable[object] = field(default_factory=list)
    enable_session_state: bool = True
    after_model_callback: Any | None = None

    def __post_init__(self) -> None:  # pragma: no cover - comportamento trivial
        self.tools = list(self.tools)

