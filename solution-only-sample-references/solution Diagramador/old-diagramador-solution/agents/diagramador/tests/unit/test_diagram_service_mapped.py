"""Unit tests for DiagramService.process_mapped_elements explicit mapping pathway.
Covers success path, validation failures, BusinessActor removal, layer rule, relationship filtering, schema failure.
"""
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.tools.diagram_service import DiagramService
import app.tools.diagram_service as ds_mod

@pytest.fixture
def svc(monkeypatch):
    # Disable schema validator for normal fixture runs (we test schema failure separately)
    monkeypatch.setattr(ds_mod, "SCHEMA_VALIDATOR_AVAILABLE", False, raising=False)
    s = DiagramService()
    # Patch heavy collaborators
    s._enforce_xml_to_outputs = None
    s._enforce_xml_integrity = lambda xml: xml  # no-op
    s._validate_diagram_quality = lambda xml, dt: {"is_metamodel_compliant": True, "overall_score": 90}
    class DummyMeta:
        def get_metamodel_compliance_summary(self):
            return {"compliance_score": 88}
    s.metamodel_generator = DummyMeta()
    s.use_metamodel = True
    class DummyTemplate:
        def apply_layout_from_mapped_layers(self, by_layer, relationships_in, system_name, steps_labels):
            # Return a minimal XML that would pass downstream parsing when schema check disabled
            return (
                f"<model identifier='m1'><name xml:lang='pt-br'>{system_name}</name>"
                f"<summary elements='{sum(len(v) for v in by_layer.values())}' rels='{len(relationships_in)}'/></model>"
            )
    s.template_enforcer = DummyTemplate()
    s._save_xml_to_outputs = lambda xml, dt, sys_name: ("/tmp/diagram.xml", "diagram.xml")
    return s

# ---------- Success Path ----------

def test_mapped_success_minimal(svc):
    elements = [
        {"id": "e1", "name": "API Gateway", "type": "ApplicationComponent", "layer": "channels"},
        {"id": "e2", "name": "Core Service", "type": "ApplicationComponent", "layer": "execution logic"},
    ]
    relationships = [
        {"source_id": "e1", "target_id": "e2", "type": "Serving", "rationale": "calls"}
    ]
    result = svc.process_mapped_elements(elements, relationships, diagram_type="container", system_name="SistemaX")
    assert result["success"] is True
    assert result["metadata"]["total_elements"] == 2
    assert result["metadata"]["total_relationships"] == 1
    assert result["compliance_summary"]["compliance_score"] == 88

# ---------- Validation Failures ----------

def test_mapped_fail_empty_elements(svc):
    result = svc.process_mapped_elements([], [], "container")
    assert result["success"] is False
    assert "Lista de elementos vazia" in result["error"]

def test_mapped_fail_missing_name(svc):
    elements = [{"id": "e1", "type": "ApplicationComponent", "layer": "channels"}]
    result = svc.process_mapped_elements(elements, [], "container")
    assert result["success"] is False
    assert "Elemento inválido" in result["error"]


def test_mapped_fail_invalid_element_type(svc):
    elements = [{"id": "e1", "name": "Thing", "type": "UnknownType", "layer": "channels"}]
    result = svc.process_mapped_elements(elements, [], "container")
    assert result["success"] is False
    assert "Tipo de elemento não permitido" in result["error"]


def test_mapped_fail_invalid_relationship_type(svc):
    elements = [{"id": "e1", "name": "API", "type": "ApplicationComponent", "layer": "channels"},
                {"id": "e2", "name": "DB", "type": "DataObject", "layer": "data"}]
    relationships = [{"source_id": "e1", "target_id": "e2", "type": "InvalidRel", "rationale": "x"}]
    result = svc.process_mapped_elements(elements, relationships, "container")
    assert result["success"] is False
    assert "Tipo de relacionamento não permitido" in result["error"]

# ---------- BusinessActor removal & layer rule ----------

def test_mapped_business_actor_removed_and_relationship_skipped(svc):
    elements = [
        {"id": "a1", "name": "Cliente", "type": "BusinessActor", "layer": "channels"},
        {"id": "e1", "name": "API", "type": "ApplicationComponent", "layer": "channels"},
        {"id": "e2", "name": "Core", "type": "ApplicationComponent", "layer": "execution logic"}
    ]
    # Relationship referencing removed BusinessActor a1 should be skipped silently
    relationships = [
        {"source_id": "a1", "target_id": "e1", "type": "Serving", "rationale": "ignored"},
        {"source_id": "e1", "target_id": "e2", "type": "Serving", "rationale": "valid"}
    ]
    result = svc.process_mapped_elements(elements, relationships, "container")
    assert result["success"] is True
    assert result["metadata"]["total_elements"] == 3  # original count including BusinessActor input
    # Only one relationship should survive (BusinessActor one skipped)
    # relationships_in length encoded in xml_content rels='1'
    assert "rels='1'" in result["xml_content"]


def test_mapped_layer_rule_gateway_inbound_without_channels_fails(svc):
    elements = [
        {"id": "e1", "name": "GatewayInbound", "type": "ApplicationComponent", "layer": "gateway inbound"}
    ]
    result = svc.process_mapped_elements(elements, [], "container")
    assert result["success"] is False
    assert "GATEWAY INBOUND" in result["error"]

# ---------- Relationship referencing unknown element ignored ----------

def test_mapped_relationship_with_unknown_ids_ignored(svc):
    elements = [{"id": "e1", "name": "API", "type": "ApplicationComponent", "layer": "channels"}]
    relationships = [
        {"source_id": "e1", "target_id": "missing", "type": "Serving", "rationale": "ignored"}
    ]
    result = svc.process_mapped_elements(elements, relationships, "container")
    # Should still succeed with 0 valid relationships recorded
    assert result["success"] is True
    assert "rels='0'" in result["xml_content"]

# ---------- Schema validator failure path ----------

def test_mapped_schema_validator_failure(monkeypatch):
    # Force schema validator availability and failing validation
    monkeypatch.setattr(ds_mod, "SCHEMA_VALIDATOR_AVAILABLE", True)
    class DummyValidator:
        def is_valid_archimate_xml(self, xml):
            return False
        def generate_validation_report(self, xml):
            return "Invalid order"
    monkeypatch.setattr(ds_mod, "ArchiMate30SchemaValidator", DummyValidator)
    s = DiagramService()
    s._enforce_xml_integrity = lambda x: x
    s._validate_diagram_quality = lambda x, y: {}
    s.template_enforcer = None  # simplify
    elements = [{"id": "e1", "name": "API", "type": "ApplicationComponent", "layer": "channels"}]
    result = s.process_mapped_elements(elements, [], "container")
    assert result["success"] is False
    assert "XML inválido" in result["error"]
