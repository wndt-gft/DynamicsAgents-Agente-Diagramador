"""Tests for the confirmation handler utility module."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
for p in (PROJECT_ROOT, APP_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import app.tools.utilities.confirmation_handler as ch  # noqa: E402


@pytest.fixture(autouse=True)
def reset_state():
    ch.reset_confirmation_state()
    yield
    ch.reset_confirmation_state()


def test_handle_user_confirmation_positive_sets_state():
    analysis = {"summary": "ok"}
    result = ch.handle_user_confirmation("Sim, pode gerar", current_analysis=analysis)
    assert result["should_generate"] is True
    assert result["action"] == "confirmed"
    assert ch.CONFIRMATION_STATE["user_confirmed"] is True
    assert result["analysis"] == analysis


def test_handle_user_confirmation_negative_branch():
    result = ch.handle_user_confirmation("está errado")
    assert result["action"] == "correction_needed"
    assert result["should_generate"] is False


def test_handle_user_confirmation_ambiguous_requests_clarification():
    result = ch.handle_user_confirmation("Talvez")
    assert result["action"] == "clarification_needed"
    assert "por favor" in result["message"].lower()


def test_mark_diagram_generated_blocks_new_generation():
    ch.mark_diagram_generated({"xml": "<d/>"})
    follow_up = ch.handle_user_confirmation("Sim")
    assert follow_up["action"] == "already_generated"
    assert ch.is_diagram_generated() is True
    assert ch.get_generation_result()["xml"] == "<d/>"


def test_handle_user_confirmation_error_path():
    response = ch.handle_user_confirmation(None)  # type: ignore[arg-type]
    assert response["action"] == "error"
    assert response["should_generate"] is False
