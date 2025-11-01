"""Unit tests for core agent functions to improve coverage.
Covers:
- get_agent_capabilities
- process_message unicode decoding & logging paths
- diagram_generator_tool success & failure
- quality_validator_tool in metamodel and fallback modes
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure app package importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import importlib
agent_module = importlib.import_module("app.agent")


def test_get_agent_capabilities_basic():
    caps = agent_module.get_agent_capabilities()
    assert isinstance(caps, dict)
    assert caps["name"].lower().startswith("architect")
    assert "supported_diagrams" in caps
    assert "tools" in caps and "diagram_generator_tool" in caps["tools"]


def test_process_message_decodes_unicode():
    # Patch architect_agent.invoke to return escaped unicode
    with patch.object(agent_module, "architect_agent") as mock_agent:
        mock_agent.invoke.return_value = "Resposta com acentuacao: \u00E1rvore"
        # Enable logging path
        with patch.object(agent_module, "is_logging_enabled", return_value=True):
            response = agent_module.process_message("Teste")
    assert "árvore" in response


def test_diagram_generator_tool_missing_elements():
    # Missing explicit mapping must fail
    result = agent_module.diagram_generator_tool(user_story="História", diagram_type="container", elements=None, relationships=None)
    assert result["success"] is False
    assert "Mapeamento explícito" in result["error"]


def test_diagram_generator_tool_success_with_mocked_service():
    class DummyService:
        def process_mapped_elements(self, elements, relationships, diagram_type, system_name, steps_labels):
            return {
                "success": True,
                "xml_content": f"<diagram type='{diagram_type}'/>",
                "plantuml_content": "@startuml\n@enduml",
                "metadata": {"system_name": system_name or "SYS"},
                "quality_report": {"overall_score": 95.0},
                "compliance_summary": {"compliance_score": 90},
                "metamodel_applied": True,
                "metamodel_status": "OK",
                "layered_mapping": {"layer": ["A", "B"]},
                "layered_summary": "summary"
            }
    with patch.object(agent_module, "DiagramService", DummyService):
        result = agent_module.diagram_generator_tool(
            user_story="Como usuário quero testar",
            diagram_type="container",
            elements=[{"id": "e1", "name": "API", "type": "ApplicationComponent", "layer": "application"}],
            relationships=[{"source_id": "e1", "target_id": "e1", "type": "Self", "rationale": "test"}],
            system_name="SistemaX",
            steps=["Etapa 1", "Etapa 2"],
        )
    assert result["success"] is True
    assert result["metamodel_status"] == "OK"
    assert "xml_content" in result
    assert result["quality_report"]["overall_score"] == 95.0


def test_quality_validator_tool_metamodel_path():
    # Simulate service with metamodel active
    class MetaService:
        use_metamodel = True
        def _validate_diagram_quality(self, xml_content, diagram_type):
            return {"is_metamodel_compliant": True, "overall_score": 88}
    with patch.object(agent_module, "DiagramService", MetaService):
        result = agent_module.quality_validator_tool("<xml/>")
    assert result["success"] is True
    assert result["metamodel_compliant"] is True


def test_quality_validator_tool_fallback_path():
    # Simulate service without metamodel to trigger fallback validator
    class FallbackService:
        use_metamodel = False
    with patch.object(agent_module, "DiagramService", FallbackService), \
         patch.object(agent_module, "validate_diagram_quality", return_value=types.SimpleNamespace(overall_score=70, quality_level="medium", summary="ok", elements_count=1, relationships_count=0, recommendations=[], issues=[])):
        result = agent_module.quality_validator_tool("<xml/>")
    assert result["success"] is True
    assert result["metamodel_compliant"] is False
    assert result["overall_score"] == 70


def test_private_decode_unicode_escapes():
    text = "Unicode: \\u00E1\\u00E9"
    decoded = agent_module._decode_unicode_escapes(text)
    assert "á" in decoded and "é" in decoded

