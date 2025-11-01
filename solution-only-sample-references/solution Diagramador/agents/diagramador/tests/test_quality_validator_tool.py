from __future__ import annotations

import importlib
from pathlib import Path

import pytest


class _StubQualityReport:
    def __init__(self) -> None:
        self.overall_score = 87.5
        self.metamodel_compliance = 92.3
        self.c4_structure_score = 81.0
        self.naming_conventions_score = 76.0
        self.documentation_score = 70.0
        self.relationships_count = 19
        self.elements_count = 22
        self.is_metamodel_compliant = True
        self.recommendations = ["Revise integrações externas"]
        self.issues = ["Relacionamento duplicado"]
        self.quality_level = type("Level", (), {"name": "GOOD"})()


class _StubQualityValidator:
    def __init__(self, metamodel: str) -> None:
        self.metamodel = metamodel
        self.report = _StubQualityReport()
        self.last_xml: str | None = None

    def validate_diagram_quality(self, xml_content: str) -> _StubQualityReport:
        self.last_xml = xml_content
        return self.report

    def generate_quality_badge(self, level: object) -> str:
        return "✅ GOOD"


@pytest.mark.unit
def test_quality_validator_reads_xml_from_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = importlib.import_module(
        "agents.diagramador.app.tools.interactions.quality_validator_tool.tool"
    )

    monkeypatch.setattr(module, "C4QualityValidator", _StubQualityValidator)

    tool = module.Tool()
    assert isinstance(tool.validator, _StubQualityValidator)

    xml_path = tmp_path / "diagram.xml"
    xml_path.write_text("<model/>", encoding="utf-8")

    state = {
        "diagram": {
            "last_result": {
                "xml_content": str(xml_path),
                "storage": {"local_path": str(xml_path)},
                "local_path": str(xml_path),
            },
            "xml_path": str(xml_path),
        },
    }

    result = tool.evaluate_quality(
        xml_content={"$state": "diagram.last_result.xml_content"},
        elements=[{"name": "A"}],
        relationships=[{"source": "A", "target": "B"}],
        state=state,
    )

    quality = result["quality"]
    assert pytest.approx(quality["score"], rel=1e-3) == 87.5
    assert quality["level"] == "✅ GOOD"
    assert quality["input_elements"] == 1
    assert quality["input_relationships"] == 1
    # Garantir que o XML foi lido a partir do caminho compartilhado.
    assert tool.validator.last_xml == "<model/>"


@pytest.mark.unit
def test_quality_validator_accepts_complex_state_pointer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = importlib.import_module(
        "agents.diagramador.app.tools.interactions.quality_validator_tool.tool"
    )

    monkeypatch.setattr(module, "C4QualityValidator", _StubQualityValidator)

    tool = module.Tool()
    xml_path = tmp_path / "diagram.xml"
    xml_path.write_text("<model/>", encoding="utf-8")

    state = {
        "diagram": {
            "last_result": {
                "storage": {"local_path": str(xml_path)},
                "artifact": {"local_path": str(xml_path)},
            }
        }
    }

    result = tool.evaluate_quality(
        xml_content={"$state": {"segments": ["diagram", "last_result", "storage"]}},
        state=state,
    )

    assert result["quality"]["score"] == pytest.approx(87.5, rel=1e-3)
    assert tool.validator.last_xml == "<model/>"


@pytest.mark.unit
def test_quality_validator_resolves_input_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module(
        "agents.diagramador.app.tools.interactions.quality_validator_tool.tool"
    )

    monkeypatch.setattr(module, "C4QualityValidator", _StubQualityValidator)

    tool = module.Tool()

    state = {
        "inputs": {
            "diagram_xml": "<model/>",
        }
    }

    result = tool.evaluate_quality(
        xml_content={"$input": "diagram_xml"},
        state=state,
    )

    assert result["quality"]["score"] == pytest.approx(87.5, rel=1e-3)
    assert tool.validator.last_xml == "<model/>"


@pytest.mark.unit
def test_quality_validator_finds_xml_in_nested_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = importlib.import_module(
        "agents.diagramador.app.tools.interactions.quality_validator_tool.tool"
    )

    monkeypatch.setattr(module, "C4QualityValidator", _StubQualityValidator)

    tool = module.Tool()

    xml_path = tmp_path / "diagram.xml"
    xml_path.write_text("<model/>", encoding="utf-8")

    state = {
        "outputs": {
            "phase2": {
                "xml_content": str(xml_path),
            }
        }
    }

    result = tool.evaluate_quality(
        xml_content=None,
        state=state,
    )

    assert result["quality"]["score"] == pytest.approx(87.5, rel=1e-3)
    assert tool.validator.last_xml == "<model/>"
