from __future__ import annotations
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest import mock

import pytest

from tools.diagramador import (
    BLUEPRINT_CACHE_KEY,
    DEFAULT_TEMPLATE,
    SESSION_STATE_ROOT,
    describe_template,
    finalize_datamodel,
    generate_archimate_diagram,
    generate_mermaid_preview,
    list_templates,
    save_datamodel,
)
from tools.diagramador import operations

SAMPLE_TEMPLATE = DEFAULT_TEMPLATE
SAMPLE_DATAMODEL = Path(
    "tools/archimate_exchange/samples/pix_solution_case/pix_container_datamodel.json"
)


@pytest.fixture()
def sample_payload() -> str:
    return SAMPLE_DATAMODEL.read_text(encoding="utf-8")


@pytest.fixture()
def session_state() -> dict:
    return {}


def test_list_templates_returns_entries():
    result = list_templates()
    assert result["count"] > 0
    paths = {Path(entry["path"]).name for entry in result["templates"]}
    assert SAMPLE_TEMPLATE.name in paths


def test_describe_template_stores_blueprint(session_state):
    guidance = describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    assert guidance["model"]["identifier"]
    bucket = session_state[SESSION_STATE_ROOT]
    cache = bucket[BLUEPRINT_CACHE_KEY]
    resolved = str(SAMPLE_TEMPLATE.resolve())
    assert resolved in cache


def test_finalize_datamodel_uses_cached_blueprint(sample_payload, session_state):
    describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    with mock.patch(
        "tools.diagramador.operations._parse_template_blueprint",
        side_effect=AssertionError("blueprint should be served from cache"),
    ):
        result = finalize_datamodel(
            sample_payload,
            str(SAMPLE_TEMPLATE),
            session_state=session_state,
        )
    assert result["element_count"] > 0
    assert "json" in result


def test_generate_mermaid_preview_reuses_cache(sample_payload, session_state):
    describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    with mock.patch(
        "tools.diagramador.operations._parse_template_blueprint",
        side_effect=AssertionError("template parse should not run when cached"),
    ):
        preview = generate_mermaid_preview(
            sample_payload,
            str(SAMPLE_TEMPLATE),
            session_state=session_state,
        )
    assert preview["view_count"] >= 1
    mermaid_blocks = [view["mermaid"] for view in preview["views"]]
    assert all(block.startswith("flowchart TD") for block in mermaid_blocks)


def test_save_and_generate_archimate_diagram(tmp_path, sample_payload):
    # Redireciona os artefatos para um diretório temporário.
    operations.OUTPUT_DIR = tmp_path  # type: ignore[attr-defined]

    result = save_datamodel(sample_payload, filename="test_datamodel.json")
    saved_path = Path(result["path"])
    assert saved_path.exists()

    xml_result = generate_archimate_diagram(
        str(saved_path),
        output_filename="test_diagram.xml",
        template_path=str(SAMPLE_TEMPLATE),
        validate=True,
    )
    xml_path = Path(xml_result["path"])
    assert xml_path.exists()
    assert xml_result["validation_report"]["valid"] is True


def test_agent_instantiation():
    from agent import diagramador_agent

    assert diagramador_agent.name == "diagramador"
