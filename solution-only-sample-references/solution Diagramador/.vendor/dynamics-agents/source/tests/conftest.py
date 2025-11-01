from __future__ import annotations

from pathlib import Path
import sys

import pytest


THIS_FILE = Path(__file__).resolve()
ROOT = next(parent for parent in THIS_FILE.parents if (parent / "pyproject.toml").exists())
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from dynamic_agents import runtime as runtime_module


@pytest.fixture(autouse=True)
def reset_session_registry() -> None:
    runtime_module._session_registry_reset()
    try:
        yield
    finally:
        runtime_module._session_registry_reset()
