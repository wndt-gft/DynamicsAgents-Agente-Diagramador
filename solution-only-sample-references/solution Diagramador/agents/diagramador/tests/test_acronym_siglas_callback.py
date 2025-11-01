from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.diagramador.app.tools.callbacks.after_tool_execution.acronym_siglas_state.callback import (
    Callback,
)


def _build_payload(siglas):
    return {
        "tool": "acronym_lookup_tool",
        "result": {"siglas": siglas},
    }


@pytest.mark.parametrize("env_value", [None, "false", "0", "off"])
def test_placeholder_without_suggestions(monkeypatch: pytest.MonkeyPatch, env_value):
    if env_value is None:
        monkeypatch.delenv("ENABLED_ACRONYM_SUGGESTIONS", raising=False)
    else:
        monkeypatch.setenv("ENABLED_ACRONYM_SUGGESTIONS", env_value)

    callback = Callback()
    state: dict[str, object] = {}

    response = callback.handle_event(
        "after_tool_execution",
        _build_payload(["SIGLAS_CMDB"]),
        state,
    )

    assert state["analysis"]["siglas"] == ["SIGLAS_CMDB"]
    assert state["analysis"]["siglas_status"] == "empty"
    assert state["analysis"]["siglas_suggestions_required"] is False
    assert state["config"]["acronym_suggestions_enabled"] is False
    assert response["suggestions_required"] is False


def test_placeholder_with_suggestions_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLED_ACRONYM_SUGGESTIONS", "true")
    callback = Callback()
    state: dict[str, object] = {}

    response = callback.handle_event(
        "after_tool_execution",
        _build_payload(["SIGLAS_CMDB"]),
        state,
    )

    assert state["analysis"]["siglas"] == []
    assert state["analysis"]["siglas_status"] == "suggestions_required"
    assert state["analysis"]["siglas_suggestions_required"] is True
    assert state["config"]["acronym_suggestions_enabled"] is True
    assert response["suggestions_required"] is True


def test_catalog_results_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLED_ACRONYM_SUGGESTIONS", "true")
    callback = Callback()
    state: dict[str, object] = {}

    response = callback.handle_event(
        "after_tool_execution",
        _build_payload(["APRO - Administração de Propostas"]),
        state,
    )

    assert state["analysis"]["siglas"] == ["APRO - Administração de Propostas"]
    assert state["analysis"]["siglas_status"] == "catalog"
    assert state["analysis"]["siglas_suggestions_required"] is False
    assert state["config"]["acronym_suggestions_enabled"] is True
    assert response["suggestions_required"] is False
