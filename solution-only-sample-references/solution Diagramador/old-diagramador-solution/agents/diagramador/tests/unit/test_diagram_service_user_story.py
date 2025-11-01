"""Unit tests for DiagramService.process_user_story covering metamodel and fallback paths."""
import sys
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
for p in (PROJECT_ROOT, APP_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import app.tools.diagram_service as ds_mod
from app.tools.diagram_service import DiagramService


@pytest.fixture
def service_metamodel(monkeypatch):
    # Ensure metamodel path logic works but override heavy parts
    monkeypatch.setattr(ds_mod, "SCHEMA_VALIDATOR_AVAILABLE", False, raising=False)
    s = DiagramService()
    # Force use_metamodel True and stub generator + validator outputs
    class DummyMeta:
        def get_metamodel_compliance_summary(self):
            return {"compliance_score": 92}
        def generate_container_diagram(self, story, system_name):
            return f"<model><name>{system_name}</name><elements/></model>"
        def generate_context_diagram(self, story, system_name):
            return f"<model><name>{system_name}</name><elements/></model>"
        def generate_component_diagram(self, story, system_name):
            return f"<model><name>{system_name}</name><elements/></model>"
    s.metamodel_generator = DummyMeta()
    s._generate_pure_metamodel_diagram = lambda *a, **k: "<model><elements/></model>"
    s._apply_template_layout_to_metamodel_diagram = lambda xml, story: xml
    s._validate_diagram_quality = lambda xml, dt: {"overall_score": 89, "is_metamodel_compliant": True}
    s._extract_layers_mapping_and_summary = lambda xml: ({"execution_logic": 1}, "summary")
    s._enforce_xml_integrity = lambda xml: xml
    s._save_xml_to_outputs = lambda xml, dt, story: ("/tmp/story.xml", "story.xml")
    s.use_metamodel = True
    return s


@pytest.fixture
def service_fallback(monkeypatch):
    monkeypatch.setattr(ds_mod, "METAMODEL_AVAILABLE", False, raising=False)
    monkeypatch.setattr(ds_mod, "SCHEMA_VALIDATOR_AVAILABLE", False, raising=False)
    s = DiagramService()
    s.use_metamodel = False
    s.engine = None  # Force fallback path
    s._fallback_xml_generation = lambda story: "<model><fallback/></model>"
    s._validate_diagram_quality = lambda xml, dt: {"overall_score": 10, "is_metamodel_compliant": False}
    s._extract_layers_mapping_and_summary = lambda xml: ({}, "")
    s._enforce_xml_integrity = lambda xml: xml
    s._save_xml_to_outputs = lambda *a, **k: ("/tmp/fallback.xml", "fallback.xml")
    return s


def test_process_user_story_metamodel_success(service_metamodel):
    story = "Como cliente eu quero consultar saldo para planejar finanças"
    result = service_metamodel.process_user_story(story, "container")
    assert result["success"] is True
    assert result["compliance_summary"]["compliance_score"] == 92
    assert result["quality_report"]["overall_score"] == 89
    assert result["metamodel_applied"] is True


def test_process_user_story_fallback(service_fallback):
    story = "Mensagem genérica sem metamodelo"
    result = service_fallback.process_user_story(story, "context")
    assert result["success"] is True
    assert result["metamodel_applied"] is False
    assert "fallback" in result["xml_content"]

