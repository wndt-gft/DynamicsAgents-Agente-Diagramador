from __future__ import annotations

import importlib
from pathlib import Path
import sys
from typing import Any, Dict

import pytest


def _ensure_repo_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


@pytest.mark.unit
def test_confirmation_callback_stores_approved_analysis_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_repo_on_path()
    module = importlib.import_module(
        "agents.diagramador.app.tools.callbacks.user_message.confirmation_state.callback"
    )
    module.confirmation_handler.reset_confirmation_state()
    calls: Dict[str, Any] = {}

    original_update = module.confirmation_handler.update_approved_snapshot

    def _capture(snapshot: Dict[str, Any]) -> None:  # noqa: ANN001
        calls["snapshot"] = snapshot
        original_update(snapshot)

    monkeypatch.setattr(module.confirmation_handler, "update_approved_snapshot", _capture)

    callback = module.Callback()
    state: Dict[str, Any] = {
        "analysis": {
            "system_name": "Sistema Original",
            "elements": {
                "layer_1": [
                    {"name": "Canal", "type": "ApplicationCollaboration"},
                ]
            },
            "relationships": [
                {"source": "Canal", "target": "Backend"},
            ],
            "steps": [
                {"description": "Fluxo"},
            ],
        }
    }

    result = callback.handle_event(
        "after_user_message",
        {"message": "SIM"},
        state,
    )

    confirmation = result["confirmation"]
    assert confirmation["status"] == "confirmed"
    assert confirmation["should_generate"] is True
    assert confirmation["approved_system_name"] == "Sistema Original"
    assert confirmation["approved_analysis"]["elements"]["layer_1"][0]["name"] == "Canal"

    # Ensure snapshot is decoupled from original analysis
    state["analysis"]["elements"]["layer_1"][0]["name"] = "Alterado"
    assert (
        confirmation["approved_analysis"]["elements"]["layer_1"][0]["name"]
        == "Canal"
    )

    assert calls["snapshot"]["system_name"] == "Sistema Original"
    module.confirmation_handler.reset_confirmation_state()
