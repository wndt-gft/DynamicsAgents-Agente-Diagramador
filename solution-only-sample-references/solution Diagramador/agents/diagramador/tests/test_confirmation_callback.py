import sys
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parents[1]
if str(SOLUTION_ROOT) not in sys.path:
    sys.path.insert(0, str(SOLUTION_ROOT))

from app.tools.callbacks.user_message.confirmation_state.callback import Callback


def test_confirmation_positive_transition():
    callback = Callback({})
    state = {}
    result = callback.handle_event(
        "after_user_message",
        {"message": "Aprovado"},
        state,
    )
    confirmation = result["confirmation"]
    assert confirmation["status"] == "confirmed"
    assert confirmation["should_generate"] is True
    assert confirmation["diagram_generated"] is False


def test_confirmation_requests_correction():
    callback = Callback({})
    state = {}
    result = callback.handle_event(
        "after_user_message",
        {"message": "precisa corrigir o fluxo"},
        state,
    )
    confirmation = result["confirmation"]
    assert confirmation["status"] == "correction_needed"
    assert confirmation["should_generate"] is False


def test_confirmation_stops_after_generation():
    callback = Callback({})
    state = {"confirmation": {"diagram_generated": True}}
    result = callback.handle_event(
        "after_user_message",
        {"message": "SIM"},
        state,
    )
    confirmation = result["confirmation"]
    assert confirmation["status"] == "already_generated"
    assert confirmation["should_generate"] is False
