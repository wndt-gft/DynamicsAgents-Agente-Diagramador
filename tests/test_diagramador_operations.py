from __future__ import annotations
from pathlib import Path
import json
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "agents" / "diagramador"))
import sitecustomize  # noqa: F401  # Ensure stub packages are available before imports
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

SAMPLE_TEMPLATE = operations._resolve_package_path(DEFAULT_TEMPLATE)
SAMPLE_DATAMODEL = operations._resolve_package_path(
    Path("tools/archimate_exchange/samples/pix_solution_case/pix_container_datamodel.json")
)
ALTERNATIVE_TEMPLATE_PATH = "agents/BV-C4-Model-SDLC/layout_template.xml"


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
    image_payloads = [view["image"] for view in preview["views"]]
    assert all(payload["url"].startswith("https://") for payload in image_payloads)
    assert all(
        payload["format"] == operations.DEFAULT_MERMAID_IMAGE_FORMAT
        for payload in image_payloads
    )


def test_generate_mermaid_preview_resolves_agent_relative_path(sample_payload):
    preview = generate_mermaid_preview(
        sample_payload,
        ALTERNATIVE_TEMPLATE_PATH,
        session_state=None,
    )
    assert preview["view_count"] >= 1


def test_generate_mermaid_preview_escapes_mermaid_sensitive_characters():
    datamodel = {
        "model_identifier": "demo",
        "elements": [
            {
                "id": "element_1",
                "type": "ApplicationComponent",
                "name": "Core [Gateway]",
            },
            {
                "id": "element_2",
                "type": "ApplicationComponent",
                "name": "Ledger",
            },
        ],
        "relations": [
            {
                "id": "rel_1",
                "type": "FlowRelationship",
                "source": "element_1",
                "target": "element_2",
                "name": "Status | Update",
            }
        ],
        "views": {
            "diagrams": [
                {
                    "id": "view_1",
                    "name": "View | Demo",
                    "nodes": [
                        {
                            "id": "node_1",
                            "label": "Primary [Node]",
                            "elementRef": "element_1",
                        },
                        {
                            "id": "node_2",
                            "label": "Secondary",
                            "elementRef": "element_2",
                        },
                    ],
                    "connections": [
                        {
                            "id": "conn_1",
                            "source": "node_1",
                            "target": "node_2",
                            "relationshipRef": "rel_1",
                            "label": "Status | Update",
                        }
                    ],
                }
            ]
        },
    }

    preview = generate_mermaid_preview(json.dumps(datamodel))
    mermaid_lines = preview["views"][0]["mermaid"].split("\n")

    node_line = next(line for line in mermaid_lines if "node_1" in line and "[")
    assert "&#91;" in node_line
    assert "&#93;" in node_line

    edge_line = next(line for line in mermaid_lines if "node_1 -->" in line)
    assert "&#124;" in edge_line


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


def test_finalize_datamodel_resolves_agent_relative_path(sample_payload):
    result = finalize_datamodel(
        sample_payload,
        ALTERNATIVE_TEMPLATE_PATH,
        session_state=None,
    )
    assert result["element_count"] > 0
    assert result["relationship_count"] > 0


def test_agent_instantiation():
    import importlib

    module = importlib.import_module("agents.diagramador.agent")
    assert module.diagramador_agent.name == "diagramador"
