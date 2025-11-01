"""Additional targeted tests to raise coverage over 80%.
Covers:
- logging_toggle.parse_bool and is_logging_enabled for various env values
- process_message exception branch
- diagram_generator_tool steps + etapas merge handling
- quality_validator_tool exception path
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import importlib

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

logging_toggle = importlib.import_module("app.utils.logging_toggle")
agent_mod = importlib.import_module("app.agent")


def test_logging_toggle_parse_bool_and_env_matrix():
    matrix = {
        "1": True,
        "true": True,
        "TRUE": True,
        "yes": True,
        "on": True,
        "0": False,
        "false": False,
        "OFF": False,
        "no": False,
        "n": False,
        "junk": False,  # default fallback
        None: False,
    }
    for value, expected in matrix.items():
        if value is None:
            os.environ.pop("LOGGING_ENABLE", None)
        else:
            os.environ["LOGGING_ENABLE"] = value
        assert logging_toggle.is_logging_enabled() is expected


def test_process_message_exception_branch():
    # architect_agent.invoke will raise => triggers exception path
    with patch.object(agent_mod, "architect_agent") as mock_agent:
        mock_agent.invoke.side_effect = RuntimeError("boom")
        resp = agent_mod.process_message("Qualquer")
    assert resp.startswith("❌ Erro no processamento")


def test_diagram_generator_tool_steps_and_etapas_merge():
    captured = {}

    class DummyService:
        def process_mapped_elements(self, elements, relationships, diagram_type, system_name, steps_labels):
            captured["steps_labels"] = steps_labels
            return {
                "success": True,
                "xml_content": "<d/>",
                "plantuml_content": "@startuml\n@enduml",
                "metadata": {},
                "quality_report": {},
                "compliance_summary": {},
                "metamodel_applied": True,
                "metamodel_status": "OK",
                "layered_mapping": {},
                "layered_summary": ""
            }
    with patch.object(agent_mod, "DiagramService", DummyService):
        result = agent_mod.diagram_generator_tool(
            user_story="Como usuário, quero testar",
            diagram_type="container",
            elements=[{"id": "e1", "name": "API", "type": "ApplicationComponent", "layer": "application"}],
            relationships=[],
            system_name="SYS",
            steps=["Etapa 1"],
            etapas=["Etapa 2", "Etapa 3"],
        )
    assert result["success"] is True
    assert captured["steps_labels"] == ["Etapa 1", "Etapa 2", "Etapa 3"]


def test_quality_validator_tool_exception_path():
    class BadService:
        def __init__(self):
            raise RuntimeError("init fail")
    with patch.object(agent_mod, "DiagramService", BadService):
        with patch.object(agent_mod, "validate_diagram_quality", return_value=SimpleNamespace(overall_score=17, issues=["fallback"], recommendations=["use metamodel"], summary="ok")):
            out = agent_mod.quality_validator_tool("<x/>")
    assert out["success"] is True
    assert out["metamodel_compliant"] is False
    assert out["overall_score"] == 17
    assert out["issues"] == ["fallback"]

