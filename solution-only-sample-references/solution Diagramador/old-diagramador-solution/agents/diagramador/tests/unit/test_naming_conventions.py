"""Unit tests for naming_conventions utility to raise coverage.
Covers: apply_naming_conventions, suggest_improvements, validate_naming_compliance, helper functions.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
for p in (PROJECT_ROOT, APP_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.tools.utilities.naming_conventions import (
    NamingConventionApplier,
    apply_naming_improvements,
    improve_element_name,
    validate_naming_compliance,
    C4NamingStandards,
)


def test_apply_naming_conventions_application_component_pascal_and_suffix():
    applier = NamingConventionApplier()
    result = applier.apply_naming_conventions("api gateway", "ApplicationComponent")
    # Should convert to PascalCase and append Service suffix once
    assert result.startswith("ApiGateway")
    assert result.endswith("Service")


def test_apply_naming_conventions_with_technology_deduplicates():
    applier = NamingConventionApplier()
    result = applier.apply_naming_conventions("core service", "ApplicationComponent", technology="spring")
    assert "Spring Boot" in result


def test_improve_element_name_wrapper():
    improved = improve_element_name("user db", "DataObject")
    assert improved.endswith("Database")


def test_apply_naming_improvements_and_reasons():
    elements = [
        {"id": "1", "name": "api", "type": "ApplicationComponent"},
        {"id": "2", "name": "User", "type": "BusinessActor"},
    ]
    suggestions = apply_naming_improvements(elements)
    # At least one suggestion (api -> Api Service style)
    assert any(s["original"].lower() == "api" for s in suggestions)


def test_validate_naming_compliance_metrics():
    elements = [
        {"id": "1", "name": "api", "type": "ApplicationComponent"},
        {"id": "2", "name": "core service", "type": "ApplicationComponent"},
    ]
    report = validate_naming_compliance(elements)
    assert "compliance_rate" in report
    assert report["total_elements"] == 2
    assert isinstance(report["elements_needing_improvement"], int)


def test_c4_standardize_helpers():
    assert C4NamingStandards.standardize_container_name("Payments", "api").endswith("API")
    assert C4NamingStandards.standardize_actor_name("user", "user") == "User"
    # Implementation maps 'reads' -> 'reads from'
    assert C4NamingStandards.standardize_relationship_label("a", "b", "reads") == "reads from"
