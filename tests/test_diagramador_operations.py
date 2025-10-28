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
import requests

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


@pytest.fixture(autouse=True)
def stub_mermaid_validation(monkeypatch):
    response = mock.Mock()
    response.raise_for_status = mock.Mock()
    response.text = "<svg id='mermaidInkSvg'></svg>"
    validator = mock.Mock(return_value=response)
    monkeypatch.setattr(operations, "_mermaid_validation_request", validator)
    return validator


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
    assert all(payload.get("method") == "POST" for payload in image_payloads)
    assert all(
        payload.get("body", {}).get("diagram_type") == "mermaid"
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


def test_generate_mermaid_preview_converts_html_line_breaks():
    datamodel = {
        "model_identifier": "demo_html_breaks",
        "elements": [
            {
                "id": "element_1",
                "type": "ApplicationComponent",
                "name": "Core</BR>Sistema",
                "documentation": "Primeira linha</BR>Segunda linha",
            }
        ],
        "relations": [],
        "views": {
            "diagrams": [
                {
                    "id": "view_html",
                    "name": "Visão</BR>Principal",
                    "nodes": [
                        {
                            "id": "node_html",
                            "elementRef": "element_1",
                        }
                    ],
                    "connections": [],
                    "documentation": "Comentário</BR>extra",
                }
            ]
        },
    }

    preview = generate_mermaid_preview(json.dumps(datamodel))
    mermaid_source = preview["views"][0]["mermaid"]

    assert "</BR>" not in mermaid_source.upper()

    lines = mermaid_source.split("\n")
    assert lines[0].strip().startswith("flowchart TD")
    assert lines[1].startswith("view_html[")
    assert "<br/>" in lines[1]

    node_line = next(line for line in lines if "node_html" in line and "[")
    assert "<br/>" in node_line


def test_generate_mermaid_preview_validates_each_view(
    sample_payload, session_state, stub_mermaid_validation
):
    describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    preview = generate_mermaid_preview(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )
    assert stub_mermaid_validation.call_count == preview["view_count"]


def test_generate_mermaid_preview_appends_statement_terminators():
    datamodel = {
        "model_identifier": "demo_semicolon",
        "elements": [],
        "relations": [],
        "views": {
            "diagrams": [
                {
                    "id": "view_semicolon",
                    "name": "Visão",
                    "nodes": [
                        {"id": "node_semicolon", "name": "Label", "type": "Label"}
                    ],
                    "connections": [],
                }
            ]
        },
    }

    preview = generate_mermaid_preview(json.dumps(datamodel))
    mermaid_lines = preview["views"][0]["mermaid"].split("\n")

    for line in mermaid_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        assert stripped.endswith(";")

    # Mesmo sem quebras de linha os delimitadores mantêm a sintaxe válida.
    collapsed = " ".join(
        part for part in mermaid_lines if part.strip() and not part.strip().startswith("%%")
    )
    assert "; " in collapsed or collapsed.endswith(";")


def test_generate_mermaid_preview_fetches_image_with_post(monkeypatch, tmp_path):
    datamodel = {
        "model_identifier": "demo_fetch",
        "elements": [],
        "relations": [],
        "views": {
            "diagrams": [
                {
                    "id": "view_fetch",
                    "name": "Visão",
                    "nodes": [
                        {"id": "node_fetch", "name": "Label", "type": "Label"}
                    ],
                    "connections": [],
                }
            ]
        },
    }

    response = mock.Mock()
    response.raise_for_status = mock.Mock()
    response.content = b"PNGDATA"
    response.headers = {"Content-Type": "image/png"}

    monkeypatch.setattr(operations, "FETCH_MERMAID_IMAGES", True)
    monkeypatch.setattr(operations, "OUTPUT_DIR", tmp_path)
    post = mock.Mock(return_value=response)
    monkeypatch.setattr(operations.requests, "post", post)

    preview = generate_mermaid_preview(json.dumps(datamodel))
    view = preview["views"][0]

    assert post.called
    called_url = post.call_args[0][0]
    assert called_url == f"{operations._kroki_base_url()}/render"
    image_payload = view["image"]
    call_kwargs = post.call_args.kwargs
    body = call_kwargs["json"]
    assert body["diagram_type"] == "mermaid"
    assert body["output_format"] == operations.DEFAULT_MERMAID_IMAGE_FORMAT
    assert body["diagram_source"] == view["mermaid"]
    assert call_kwargs["headers"] == {"Accept": image_payload["mime_type"]}
    assert image_payload["status"] == "cached"
    assert image_payload["method"] == "POST"
    assert image_payload["body"]["diagram_source"] == view["mermaid"]
    assert image_payload["headers"] == {"Accept": image_payload["mime_type"]}
    assert image_payload["data_uri"].startswith(
        f"data:{image_payload['mime_type']};base64,"
    )

    image_path = Path(image_payload["path"])
    assert image_path.exists()


def test_validate_mermaid_syntax_raises_on_error(stub_mermaid_validation):
    stub_mermaid_validation.return_value.text = (
        '<svg aria-roledescription="error"><text>Parse error on line 1</text></svg>'
    )

    with pytest.raises(ValueError, match="Parse error on line 1"):
        operations._validate_mermaid_syntax("flowchart TD; A-->B;")


def test_validate_mermaid_syntax_ignores_network_error(stub_mermaid_validation):
    stub_mermaid_validation.side_effect = requests.RequestException("network down")

    operations._validate_mermaid_syntax("flowchart TD; X-->Y;")


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
