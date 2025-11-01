from __future__ import annotations

import importlib
from pathlib import Path
import sys

import pytest


def _import_confirmation_handler():
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return importlib.import_module(
        "agents.diagramador.app.tools.shared.diagram_generator.utilities.confirmation_handler"
    )


@pytest.mark.unit
def test_handle_user_confirmation_populates_global_snapshot() -> None:
    module = _import_confirmation_handler()
    module.reset_confirmation_state()

    analysis = {
        "system_name": "Sistema Confirmado",
        "elements": {
            "layer_1": [
                {"name": "Canal", "type": "ApplicationCollaboration"},
            ],
        },
        "relationships": [
            {"source": "Canal", "target": "Backend", "label": "Usa"},
        ],
        "steps": [
            {"description": "Fluxo confirmado"},
        ],
    }

    result = module.handle_user_confirmation("Sim, pode gerar", analysis)
    snapshot = module.get_approved_snapshot()

    assert snapshot["system_name"] == "Sistema Confirmado"
    assert snapshot["elements"]["layer_1"][0]["name"] == "Canal"
    assert result["analysis"]["elements"]["layer_1"][0]["name"] == "Canal"

    module.reset_confirmation_state()


@pytest.mark.unit
def test_update_snapshot_supports_nested_payload() -> None:
    module = _import_confirmation_handler()
    module.reset_confirmation_state()

    nested_payload = {
        "analysis": {
            "summary": {"system_name": "Sistema Aninhado"},
            "elements": {
                "layer_1": [
                    {"name": "Mobile", "type": "ApplicationCollaboration"},
                ],
            },
            "relationships": [
                {"source": "Mobile", "target": "Core", "label": "Integra"},
            ],
            "steps": ["Fluxo aninhado"],
        }
    }

    module.update_approved_snapshot(nested_payload)
    snapshot = module.get_approved_snapshot()

    assert snapshot["system_name"] == "Sistema Aninhado"
    assert snapshot["elements"]["layer_1"][0]["name"] == "Mobile"
    assert snapshot["relationships"][0]["label"] == "Integra"

    module.reset_confirmation_state()
