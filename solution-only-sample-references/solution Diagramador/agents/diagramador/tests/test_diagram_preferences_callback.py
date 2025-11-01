"""Tests for the diagram preferences callback."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SOLUTION_ROOT = Path(__file__).resolve().parents[1]
if str(SOLUTION_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLUTION_ROOT))

REPO_ROOT = SOLUTION_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.tools.callbacks.user_message.diagram_preferences_state.callback import Callback


@pytest.fixture
def callback() -> Callback:
    return Callback()


def test_detect_context_diagram_updates_state(callback: Callback) -> None:
    state: dict = {}
    payload = {"message": "Preciso do diagrama de contexto para o PIX"}

    result = callback.handle_event("after_user_message", payload, state)

    assert "analysis" in result
    analysis = result["analysis"]
    assert analysis["diagram_types"] == ["context"]
    assert analysis["diagram_type"] == "context"
    preferences = analysis.get("diagram_preferences", {})
    assert preferences["detected_types"] == ["context"]
    assert preferences["last_user_message"] == payload["message"]
    assert preferences["source"] == "user_message"


def test_detect_multiple_diagrams_preserves_default_order(callback: Callback) -> None:
    state: dict = {}
    payload = {"message": "Gerar diagramas Container e Contexto"}

    callback.handle_event("after_user_message", payload, state)

    analysis = state["analysis"]
    assert analysis["diagram_types"] == ["container", "context"]
    assert analysis["diagram_type"] == "container"


def test_detect_all_diagrams_from_keyword(callback: Callback) -> None:
    state: dict = {}
    payload = {"message": "Quero todos os diagramas disponíveis"}

    callback.handle_event("after_user_message", payload, state)

    analysis = state["analysis"]
    assert analysis["diagram_types"] == ["container", "context", "component"]


def test_ignores_message_without_diagram_reference(callback: Callback) -> None:
    state: dict = {}
    payload = {"message": "Obrigado pela ajuda"}

    result = callback.handle_event("after_user_message", payload, state)

    assert result == {}
    assert state == {}
