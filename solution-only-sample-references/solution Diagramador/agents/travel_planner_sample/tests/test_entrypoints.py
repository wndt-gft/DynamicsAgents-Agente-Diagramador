"""Tests for Travel Planner solution entry points."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable

import pytest


@pytest.fixture(autouse=True)
def _add_solution_to_syspath(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the Travel Planner package root is importable as ``app``."""

    solution_root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(solution_root))


def _clear_app_modules() -> None:
    """Remove cached ``app`` modules so patched dependencies take effect."""

    to_remove: Iterable[str] = [
        name
        for name in list(sys.modules)
        if name == "app" or name.startswith("app.")
    ]
    for name in to_remove:
        sys.modules.pop(name, None)


@pytest.fixture
def runtime_stub(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Provide a stubbed Dynamic Agents runtime for import-time hooks."""

    state = SimpleNamespace()
    state.app = object()
    state.root_agent = object()
    state.run_calls: list[Dict[str, Any] | None] = []

    def stub_run(payload: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
        state.run_calls.append(payload)
        if payload is None:
            return None
        return {"payload": payload}

    state.run = stub_run

    def fake_loader(name: str, file_path: str) -> SimpleNamespace:
        state.loader_args = (name, file_path)
        return SimpleNamespace(app=state.app, root_agent=state.root_agent, run=state.run)

    def fake_bootstrap(file_path: str) -> tuple[Any, Any, Any]:
        state.bootstrap_args = (file_path,)
        return state.app, state.root_agent, state.run

    monkeypatch.setitem(
        sys.modules,
        "dynamic_agents",
        SimpleNamespace(
            load_solution_app_module=fake_loader,
            bootstrap_solution_entrypoints=fake_bootstrap,
        ),
    )

    _clear_app_modules()
    return state


@pytest.mark.unit
def test_app_package_exposes_dynamic_runtime(runtime_stub: SimpleNamespace) -> None:
    """The ``app`` package should surface the runtime-provided entry points."""

    module = importlib.import_module("app")

    assert module.app is runtime_stub.app
    assert module.root_agent is runtime_stub.root_agent
    assert module.run is runtime_stub.run
    assert runtime_stub.loader_args[0] == "app"


@pytest.mark.unit
def test_app_module_exports_expected_symbols(runtime_stub: SimpleNamespace) -> None:
    """The module level ``__all__`` should remain aligned with runtime entry points."""

    module = importlib.import_module("app")

    assert set(module.__all__) == {"app", "root_agent", "run"}


@pytest.mark.unit
def test_agent_run_delegates_to_runtime(runtime_stub: SimpleNamespace) -> None:
    """The ``run`` helper must proxy to the bootstraped runtime callable."""

    module = importlib.import_module("app.agent")

    payload = {"destination": "Lisboa", "passengers": 2}
    result = module.run(payload)

    assert runtime_stub.run_calls == [payload]
    assert result == {"payload": payload}
    assert runtime_stub.bootstrap_args[0].endswith("agent.py")


@pytest.mark.unit
def test_agent_module_exports_expected_symbols(runtime_stub: SimpleNamespace) -> None:
    """The wrapper module should expose the same public API as the runtime."""

    module = importlib.import_module("app.agent")

    assert set(module.__all__) == {"app", "root_agent", "run"}
