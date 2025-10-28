"""Stub simples para `google.adk.tools.function_tool`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class FunctionTool:
    function: Callable[..., Any]
    name: Optional[str] = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - trivial
        return self.function(*args, **kwargs)
