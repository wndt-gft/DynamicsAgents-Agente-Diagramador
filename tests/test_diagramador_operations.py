from __future__ import annotations
from pathlib import Path
import json
import sys
from typing import Any, Dict, Optional

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

CONTAINER_VIEW_ID = "id-171323"
CONTAINER_VIEW_NAME = "Visão de Container - {SolutionName}"


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


def _load_full_preview(
    preview_result: Dict[str, Any],
    *,
    session_state: Optional[Dict[str, Any]] = None,
    include_image: bool = False,
) -> Dict[str, Any]:
    preview_id = preview_result.get("preview_id")
    assert preview_id, "preview should include an identifier stored em sessão"
    return operations.get_mermaid_preview(
        preview_id,
        session_state=session_state,
        include_image=include_image,
    )


def test_list_templates_returns_entries():
    result = list_templates()
    assert result["count"] > 0
    paths = {Path(entry["path"]).name for entry in result["templates"]}
    assert SAMPLE_TEMPLATE.name in paths


def test_list_templates_uses_default_when_custom_dir_missing():
    result = list_templates("agents/c4-model")
    assert result["count"] > 0
    default_dir = operations._resolve_templates_dir()
    assert Path(result["directory"]).resolve() == default_dir.resolve()


def test_list_templates_includes_view_metadata():
    result = list_templates()
    entry = next(
        template
        for template in result["templates"]
        if Path(template["path"]).name == SAMPLE_TEMPLATE.name
    )
    views = entry.get("views", [])
    assert views, "template deve expor metadados de visões"
    names = {view.get("name") for view in views}
    assert CONTAINER_VIEW_NAME in names
    assert any(view.get("documentation") for view in views)
    container_entry = next(view for view in views if view.get("name") == CONTAINER_VIEW_NAME)
    assert container_entry.get("role") == "container"


def test_describe_template_stores_blueprint(session_state):
    guidance = describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    assert guidance["model"]["identifier"]
    bucket = session_state[SESSION_STATE_ROOT]
    cache = bucket[BLUEPRINT_CACHE_KEY]
    resolved = str(SAMPLE_TEMPLATE.resolve())
    assert resolved in cache


def test_describe_template_filters_view_by_identifier(session_state):
    guidance = describe_template(
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
        view_identifier=CONTAINER_VIEW_ID,
    )
    diagrams = guidance["views"]["diagrams"]
    assert len(diagrams) == 1
    assert diagrams[0]["identifier"] == CONTAINER_VIEW_ID
    assert diagrams[0].get("role")


def test_describe_template_filters_view_by_name(session_state):
    guidance = describe_template(
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
        view_name=CONTAINER_VIEW_NAME,
    )
    diagrams = guidance["views"]["diagrams"]
    assert len(diagrams) == 1
    assert diagrams[0]["name"] == CONTAINER_VIEW_NAME
    assert diagrams[0].get("role")


def test_describe_template_filter_raises_for_unknown_view(session_state):
    with pytest.raises(ValueError):
        describe_template(
            str(SAMPLE_TEMPLATE),
            session_state=session_state,
            view_identifier="unknown-view",
        )


def test_describe_template_includes_role_metadata(session_state):
    guidance = describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    diagrams = guidance.get("views", {}).get("diagrams", [])
    assert diagrams, "describe_template deve retornar a hierarquia de visões"
    role_by_name = {
        entry.get("name"): entry.get("role") for entry in diagrams if entry.get("name")
    }
    assert role_by_name.get(CONTAINER_VIEW_NAME) == "container"


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
    assert preview["status"] == "ok"
    assert preview["view_count"] >= 1
    stored_preview = _load_full_preview(
        preview,
        session_state=session_state,
        include_image=True,
    )
    assert "datamodel" in stored_preview
    assert set(stored_preview["selectors"].keys()) == {"ids", "names"}
    mermaid_blocks = [view["mermaid"] for view in stored_preview["views"]]
    assert all(block.startswith("flowchart") for block in mermaid_blocks)
    image_payloads = [view["image"] for view in stored_preview["views"]]
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


def test_generate_mermaid_preview_uses_cached_reference(sample_payload, session_state):
    describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    first = generate_mermaid_preview(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )
    ref_payload = json.dumps({"preview_id": first["preview_id"]})
    second = generate_mermaid_preview(
        ref_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )
    assert second["status"] == "ok"
    assert second["view_count"] == first["view_count"]


def test_generate_mermaid_preview_reuses_latest_snapshot(sample_payload, session_state):
    describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    generate_mermaid_preview(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
        view_name="Visão de Container",
    )
    follow_up = generate_mermaid_preview(
        "status: ok",
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
        view_name="Visao de Container",
    )
    assert follow_up["status"] == "ok"


def test_generate_mermaid_preview_resolves_agent_relative_path(sample_payload):
    preview = generate_mermaid_preview(
        sample_payload,
        ALTERNATIVE_TEMPLATE_PATH,
        session_state=None,
    )
    assert preview["status"] == "ok"
    stored_preview = _load_full_preview(preview, session_state=None)
    assert stored_preview["view_count"] >= 1


def test_generate_mermaid_preview_reuses_preview_without_session(sample_payload):
    first = generate_mermaid_preview(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=None,
    )
    assert first["status"] == "ok"
    reference = f"preview_id: {first['preview_id']}"
    follow_up = generate_mermaid_preview(
        reference,
        session_state=None,
        view_name="visao de container",
    )
    assert follow_up["status"] == "ok"
    assert follow_up["view_count"] >= 1
    view_names = {entry.get("name", "") for entry in follow_up["views"]}
    assert any("container" in name.lower() for name in view_names)


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
    stored_preview = _load_full_preview(preview)
    mermaid_lines = stored_preview["views"][0]["mermaid"].split("\n")

    node_line = next(line for line in mermaid_lines if "node_1" in line and "[")
    assert "&#91;" in node_line
    assert "&#93;" in node_line

    edge_line = next(line for line in mermaid_lines if "node_1 -->" in line)
    assert "&#124;" in edge_line


def test_filter_views_by_selectors_handles_accents():
    selectors = operations._extract_view_selectors({"view_name": "Visao de Container"})
    views = [
        {"id": "context", "name": "Visão de Contexto"},
        {"id": "container", "name": "Visão de Container"},
    ]
    filtered = operations._filter_views_by_selectors(views, selectors)
    assert [view["id"] for view in filtered] == ["container"]


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
    stored_preview = _load_full_preview(preview)
    mermaid_source = stored_preview["views"][0]["mermaid"]

    assert "</BR>" not in mermaid_source.upper()

    lines = mermaid_source.split("\n")
    assert lines[0].strip().startswith("flowchart")
    assert lines[1].startswith("title ")

    node_line = next(line for line in lines if "node_html" in line and "[")
    assert "<br/>" in node_line


def _sample_elements_and_relations():
    return (
        [
            {
                "id": "element_alpha",
                "type": "ApplicationComponent",
                "name": "Serviço Alpha",
            },
            {
                "id": "element_beta",
                "type": "ApplicationComponent",
                "name": "Serviço Beta",
            },
        ],
        [
            {
                "id": "rel_alpha_beta",
                "type": "FlowRelationship",
                "source": "element_alpha",
                "target": "element_beta",
            }
        ],
    )


def _sample_view_payload(name: str, suffix: str) -> dict:
    return {
        "id": f"view_{suffix}",
        "name": name,
        "nodes": [
            {
                "id": f"node_{suffix}_alpha",
                "elementRef": "element_alpha",
            },
            {
                "id": f"node_{suffix}_beta",
                "elementRef": "element_beta",
            },
        ],
        "connections": [
            {
                "id": f"conn_{suffix}",
                "source": f"node_{suffix}_alpha",
                "target": f"node_{suffix}_beta",
                "relationshipRef": "rel_alpha_beta",
            }
        ],
    }


def test_generate_mermaid_preview_accepts_named_view_mapping():
    elements, relations = _sample_elements_and_relations()
    datamodel = {
        "model_identifier": "demo_named_views",
        "elements": elements,
        "relations": relations,
        "views": {
            "Visão Técnica (VT)": _sample_view_payload("Visão Técnica (VT)", "vt"),
        },
    }

    preview = generate_mermaid_preview(json.dumps(datamodel))

    assert preview["status"] == "ok"
    assert preview["view_count"] == 1
    view_summary = preview["views"][0]
    assert view_summary["name"] == "Visão Técnica (VT)"
    assert view_summary["sources"]["nodes"]["total"] == 2
    assert view_summary["sources"]["connections"]["total"] == 1
    assert view_summary["has_mermaid"] is True


def test_generate_mermaid_preview_accepts_top_level_view_payload():
    elements, relations = _sample_elements_and_relations()
    datamodel = {
        "model_identifier": "demo_top_level_view",
        "elements": elements,
        "relations": relations,
        "view": _sample_view_payload("Visão de Container", "container"),
    }

    preview = generate_mermaid_preview(json.dumps(datamodel))

    assert preview["status"] == "ok"
    assert preview["view_count"] == 1
    assert preview["views"][0]["name"] == "Visão de Container"


def test_generate_mermaid_preview_filters_by_selected_view_name():
    elements, relations = _sample_elements_and_relations()
    datamodel = {
        "model_identifier": "demo_selected_view",
        "elements": elements,
        "relations": relations,
        "views": {
            "diagrams": [
                _sample_view_payload("Visão A", "a"),
                _sample_view_payload("Visão B", "b"),
            ],
        },
        "selected_view": "Visão B",
    }

    preview = generate_mermaid_preview(json.dumps(datamodel))

    assert preview["status"] == "ok"
    assert preview["view_count"] == 1
    assert preview["views"][0]["name"] == "Visão B"


def test_generate_mermaid_preview_honors_view_name_argument():
    elements, relations = _sample_elements_and_relations()
    datamodel = {
        "model_identifier": "demo_argument_view",
        "elements": elements,
        "relations": relations,
        "views": {
            "diagrams": [
                _sample_view_payload("Visão de Contexto", "contexto"),
                _sample_view_payload("Visão de Container", "container"),
            ],
        },
    }

    preview = generate_mermaid_preview(
        json.dumps(datamodel),
        view_name="Visão de Container",
    )

    assert preview["status"] == "ok"
    assert preview["view_count"] == 1
    assert preview["views"][0]["name"] == "Visão de Container"


def test_generate_mermaid_preview_validates_each_view(
    sample_payload, session_state, stub_mermaid_validation
):
    describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    preview = generate_mermaid_preview(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )
    assert stub_mermaid_validation.call_count >= preview["view_count"]


def test_generate_mermaid_preview_falls_back_to_flowchart_on_c4_error(
    sample_payload, session_state, stub_mermaid_validation
):
    error_response = mock.Mock()
    error_response.raise_for_status = mock.Mock()
    error_response.text = (
        '<svg aria-roledescription="error"><text>Syntax error</text></svg>'
    )
    ok_response = mock.Mock()
    ok_response.raise_for_status = mock.Mock()
    ok_response.text = "<svg id='mermaidInkSvg'></svg>"

    responses = [error_response] + [ok_response] * 10
    stub_mermaid_validation.side_effect = responses

    describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    preview = generate_mermaid_preview(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )
    stored_preview = _load_full_preview(preview, session_state=session_state)

    assert any(
        view["mermaid"].startswith("flowchart")
        for view in stored_preview["views"]
    )


def test_generate_mermaid_preview_removes_styles_after_repeated_errors(
    sample_payload, session_state, stub_mermaid_validation
):
    error_response = mock.Mock()
    error_response.raise_for_status = mock.Mock()
    error_response.text = (
        '<svg aria-roledescription="error"><text>Syntax error</text></svg>'
    )
    ok_response = mock.Mock()
    ok_response.raise_for_status = mock.Mock()
    ok_response.text = "<svg id='mermaidInkSvg'></svg>"

    stub_mermaid_validation.side_effect = [
        error_response,
        error_response,
        ok_response,
        ok_response,
        ok_response,
    ]

    describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    preview = generate_mermaid_preview(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
        view_name=CONTAINER_VIEW_NAME,
    )
    stored_preview = _load_full_preview(preview, session_state=session_state)

    mermaid_sources = [view["mermaid"] for view in stored_preview["views"]]
    assert all("style " not in source for source in mermaid_sources)
    assert all("linkStyle" not in source for source in mermaid_sources)


def test_generate_mermaid_preview_filters_by_role_hint(session_state):
    describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    datamodel = {"model_identifier": "role_hint_demo"}
    preview = generate_mermaid_preview(
        json.dumps(datamodel),
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
        view_metadata={"role": "container"},
    )
    stored = _load_full_preview(preview, session_state=session_state)
    roles = {view.get("role") for view in stored["views"]}
    assert roles == {"container"}


def test_generate_mermaid_preview_ignores_template_only_nodes(sample_payload):
    payload = json.loads(sample_payload)
    diagrams = payload["views"]["diagrams"]
    assert diagrams, "payload should contain diagrams for the sample template"

    target_view = diagrams[0]
    removed_node = None
    for index in range(len(target_view["nodes"]) - 1, -1, -1):
        candidate = target_view["nodes"][index]
        if isinstance(candidate, dict) and candidate.get("id"):
            removed_node = target_view["nodes"].pop(index)
            break

    assert removed_node is not None, "expected at least one node with an identifier"

    removed_id = str(removed_node.get("id"))
    target_view["connections"] = [
        conn
        for conn in target_view.get("connections", [])
        if conn.get("source") != removed_id and conn.get("target") != removed_id
    ]

    preview = generate_mermaid_preview(
        json.dumps(payload),
        str(SAMPLE_TEMPLATE),
    )

    stored_preview = _load_full_preview(preview)
    rendered_view = stored_preview["views"][0]
    rendered_ids = {
        str(node.get("id"))
        for node in rendered_view["nodes"]
        if isinstance(node, dict) and node.get("id")
    }

    assert removed_id not in rendered_ids
    assert all(node.get("id") != removed_id for node in rendered_view["nodes"])
    assert removed_id not in rendered_view["mermaid"]


def test_generate_mermaid_preview_applies_node_styles():
    datamodel = {
        "model_identifier": "style-demo",
        "model_name": "Visão Estilizada",
        "elements": [
            {
                "id": "element-service",
                "type": "ApplicationComponent",
                "name": "Serviço Central",
            }
        ],
        "relations": [],
        "views": {
            "diagrams": [
                {
                    "id": "view-style",
                    "name": "Visão Estilizada",
                    "nodes": [
                        {
                            "id": "container-root",
                            "type": "Container",
                            "label": "Layer Verde",
                            "style": {
                                "fillColor": {"r": 0, "g": 255, "b": 0, "a": 100},
                                "lineColor": {"r": 0, "g": 128, "b": 0, "a": 100},
                            },
                            "children": [
                                {
                                    "id": "node-service",
                                    "type": "Element",
                                    "refs": {"elementRef": "element-service"},
                                    "style": {
                                        "fillColor": {"r": 255, "g": 255, "b": 255, "a": 100},
                                        "lineColor": {"r": 0, "g": 0, "b": 0, "a": 100},
                                    },
                                }
                            ],
                        }
                    ],
                    "connections": [],
                }
            ]
        },
    }

    preview = generate_mermaid_preview(json.dumps(datamodel))
    stored_preview = _load_full_preview(preview)
    mermaid = stored_preview["views"][0]["mermaid"]

    assert "subgraph container_root" in mermaid
    assert "style container_root fill:#00FF00" in mermaid
    assert "style node_service fill:#FFFFFF" in mermaid


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
    stored_preview = _load_full_preview(preview)
    mermaid_lines = stored_preview["views"][0]["mermaid"].split("\n")

    for line in mermaid_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("%%") or stripped.startswith("title "):
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
    assert preview["views"][0]["has_image"] is True
    stored_preview = _load_full_preview(preview, include_image=True)
    view = stored_preview["views"][0]

    assert post.called
    called_url = post.call_args[0][0]
    expected_url = (
        f"{operations._kroki_base_url()}/mermaid/{operations.DEFAULT_MERMAID_IMAGE_FORMAT}"
    )
    assert called_url == expected_url
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
