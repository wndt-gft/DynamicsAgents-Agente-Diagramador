from __future__ import annotations
from pathlib import Path
import json
import sys
import urllib.parse

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "agents" / "diagramador"))
import sitecustomize  # noqa: F401  # Ensure stub packages are available before imports
from unittest import mock

import pytest

from tools.diagramador import (
    ARTIFACTS_CACHE_KEY,
    BLUEPRINT_CACHE_KEY,
    DEFAULT_TEMPLATE,
    SESSION_ARTIFACT_ARCHIMATE_XML,
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
    SESSION_ARTIFACT_SAVED_DATAMODEL,
    SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
    SESSION_ARTIFACT_TEMPLATE_LISTING,
    SESSION_STATE_ROOT,
    describe_template,
    finalize_datamodel,
    generate_archimate_diagram,
    generate_layout_preview,
    get_cached_artifact,
    get_view_focus,
    list_templates,
    save_datamodel,
)
from tools.diagramador import operations
from agents.diagramador import agent as diagramador_agent_module
from tools.diagramador.session import clear_fallback_session_state

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
def reset_fallback_state():
    clear_fallback_session_state()
    yield
    clear_fallback_session_state()


def test_list_templates_returns_entries(session_state):
    result = list_templates(directory=None, session_state=session_state)
    assert result["status"] == "ok"

    listing = get_cached_artifact(
        session_state, SESSION_ARTIFACT_TEMPLATE_LISTING
    )
    assert listing is not None
    assert listing["count"] > 0
    paths = {Path(entry["path"]).name for entry in listing["templates"]}
    assert SAMPLE_TEMPLATE.name in paths
    sample_entry = next(
        entry for entry in listing["templates"] if Path(entry["path"]).name == SAMPLE_TEMPLATE.name
    )
    assert sample_entry.get("views")
    assert any(view.get("name") for view in sample_entry["views"])
    indices = [view.get("index") for view in sample_entry["views"]]
    assert indices == list(range(len(indices)))


def test_describe_template_stores_blueprint(session_state):
    result = describe_template(str(SAMPLE_TEMPLATE), view_filter=None, session_state=session_state)
    assert result["status"] == "ok"

    guidance = get_cached_artifact(
        session_state, SESSION_ARTIFACT_TEMPLATE_GUIDANCE
    )
    assert guidance["model"]["identifier"]
    bucket = session_state[SESSION_STATE_ROOT]
    cache = bucket[BLUEPRINT_CACHE_KEY]
    resolved = str(SAMPLE_TEMPLATE.resolve())
    assert resolved in cache


def test_describe_template_filters_views(session_state):
    list_templates(directory=None, session_state=session_state)
    result = describe_template(
        str(SAMPLE_TEMPLATE),
        view_filter="id-154903",
        session_state=session_state,
    )
    assert result["status"] == "ok"

    guidance = get_cached_artifact(
        session_state, SESSION_ARTIFACT_TEMPLATE_GUIDANCE
    )
    diagrams = guidance["views"]["diagrams"]
    assert len(diagrams) == 1
    assert diagrams[0]["identifier"] == "id-154903"
    assert diagrams[0]["name"]
    assert diagrams[0]["list_view_name"] == diagrams[0]["name"]
    assert isinstance(diagrams[0].get("list_view_index"), int)
    focus_tokens = get_view_focus(session_state)
    assert focus_tokens == ["id-154903".casefold()]


def test_safe_json_loads_repairs_missing_commas():
    payload = '{"views": {"diagrams": [{"id": "v1", "name": "A"}\n  {"id": "v2", "name": "B"}]}}'
    repaired = operations._safe_json_loads(payload)
    assert repaired["views"]["diagrams"][0]["id"] == "v1"
    assert repaired["views"]["diagrams"][1]["id"] == "v2"


def test_agent_wrapper_describe_template_uses_session_state(session_state):
    response = diagramador_agent_module.describe_template(
        str(SAMPLE_TEMPLATE), "", session_state=session_state
    )
    assert response["status"] == "ok"
    assert response["artifact"] == SESSION_ARTIFACT_TEMPLATE_GUIDANCE
    assert "session_state" not in response

    guidance = get_cached_artifact(
        session_state, SESSION_ARTIFACT_TEMPLATE_GUIDANCE
    )
    assert guidance["model"]["identifier"]
    assert guidance.get("views", {}).get("diagrams")

    # Resposta deve permanecer enxuta, sem incluir a estrutura completa do
    # template diretamente.
    assert "model" not in response
    assert "views" not in response

def test_finalize_datamodel_uses_cached_blueprint(sample_payload, session_state):
    describe_template(str(SAMPLE_TEMPLATE), view_filter=None, session_state=session_state)
    with mock.patch(
        "tools.diagramador.operations._parse_template_blueprint",
        side_effect=AssertionError("blueprint should be served from cache"),
    ):
        result = finalize_datamodel(
            sample_payload,
            str(SAMPLE_TEMPLATE),
            session_state=session_state,
        )
    assert result["status"] == "ok"
    artifact = get_cached_artifact(
        session_state, SESSION_ARTIFACT_FINAL_DATAMODEL
    )
    assert artifact["element_count"] > 0
    assert "json" in artifact
    preview = get_cached_artifact(
        session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW
    )
    assert preview is not None


def test_generate_layout_preview_reuses_cache(sample_payload, session_state):
    describe_template(str(SAMPLE_TEMPLATE), view_filter=None, session_state=session_state)
    finalize_datamodel(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )
    datamodel_view_count = len(json.loads(sample_payload)["views"]["diagrams"])

    with mock.patch(
        "tools.diagramador.operations._parse_template_blueprint",
        side_effect=AssertionError("template parse should not run when cached"),
    ):
        result = generate_layout_preview(
            None,
            str(SAMPLE_TEMPLATE),
            view_filter=None,
            session_state=session_state,
        )
    assert result["status"] == "ok"
    assert result["artifact"] == SESSION_ARTIFACT_LAYOUT_PREVIEW
    assert result["view_count"] == datamodel_view_count
    assert set(result.keys()) <= {"status", "artifact", "view_count", "message"}
    if "message" in result:
        assert result["message"] == "Pré-visualização armazenada com sucesso."
    preview = get_cached_artifact(
        session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW
    )
    assert preview["view_count"] == datamodel_view_count
    layout_payloads = [view.get("layout_preview") for view in preview["views"]]
    if any(payload is None for payload in layout_payloads):
        pytest.skip("Pré-visualização requer svgwrite para gerar o layout.")
    assert all(payload["format"] == "svg" for payload in layout_payloads)
    assert all(Path(payload["local_path"]).exists() for payload in layout_payloads)
    assert preview.get("preview_summaries")
    assert preview.get("artifacts")

    replacements = diagramador_agent_module._collect_layout_preview_replacements(preview)
    png_placeholder = replacements.get("{diagram_img_png}")
    assert png_placeholder and "data:image/png;base64," in png_placeholder
    svg_placeholder = replacements.get("{link_diagrama_svg_base64}")
    assert svg_placeholder and "data:image/svg+xml;base64," in svg_placeholder

    state_replacements = diagramador_agent_module._build_placeholder_replacements(session_state)
    assert any(
        key.endswith("inline_markdown}}") and "data:image/png;base64," in value
        for key, value in state_replacements.items()
    )
    assert any(
        key.endswith("download_markdown}}") and "data:image/svg+xml;base64," in value
        for key, value in state_replacements.items()
    )

    # Tool responses should avoid embedding large preview payloads when a session
    # state mapping is supplied.
    assert "previews" not in result
    assert "inline_markdown" not in result
    assert "download_markdown" not in result
    assert "preview_messages" not in result
    assert "primary_preview" not in result
    assert "artifacts" not in result


def test_register_placeholder_handles_percent_encoding():
    replacements: dict[str, str] = {}
    token = "{{state.preview_png}}"
    value = "BASE64DATA"

    diagramador_agent_module._register_placeholder(replacements, token, value)

    encoded_token = urllib.parse.quote(token, safe="")
    assert encoded_token in replacements
    assert replacements[encoded_token] == value


def test_collect_layout_preview_registers_prefix_tokens():
    inline_html = '<img src="data:image/png;base64,IMG" alt="Visão">'
    download_html = '<a href="data:image/svg+xml;base64,SVG">Abrir</a>'

    layout = {
        "preview_summaries": [
            {
                "view_name": "Visão",
                "inline_html": inline_html,
                "download_html": download_html,
                "inline_data_uri": "data:image/png;base64,IMG",
                "download_data_uri": "data:image/svg+xml;base64,SVG",
                "state_placeholder_prefix": "preview_token",
                "placeholder_token": "preview_token",
                "placeholders": {
                    "image": "{{state.preview_token_img}}",
                    "link": "{{state.preview_token_link}}",
                    "uri": "{{state.preview_token_url}}",
                    "url": "{{state.preview_token_url}}",
                },
            }
        ]
    }

    replacements = diagramador_agent_module._collect_layout_preview_replacements(layout)

    assert replacements.get("{{state.preview_token}}") == inline_html
    assert replacements.get("[[state.preview_token]]") == inline_html
    assert replacements.get("{{state.preview_token_url}}") == "data:image/svg+xml;base64,SVG"
    assert replacements.get("[[state.preview_token_url]]") == "data:image/svg+xml;base64,SVG"


def test_generate_layout_preview_resolves_agent_relative_path(sample_payload, session_state):
    result = generate_layout_preview(
        sample_payload,
        ALTERNATIVE_TEMPLATE_PATH,
        view_filter=None,
        session_state=session_state,
    )
    assert result["status"] == "ok"
    assert result["artifact"] == SESSION_ARTIFACT_LAYOUT_PREVIEW
    assert set(result.keys()) <= {"status", "artifact", "view_count", "message"}

    preview = get_cached_artifact(
        session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW
    )
    assert preview["view_count"] >= 1
    if any(view.get("layout_preview") is None for view in preview["views"]):
        pytest.skip("Pré-visualização requer svgwrite para gerar o layout.")
    assert all("layout_preview" in view for view in preview["views"])
    assert preview.get("preview_summaries")
    assert preview.get("message")
    inline_markdown = preview.get("inline_markdown", "")
    if inline_markdown:
        assert inline_markdown.startswith("![")
        if "data:image/png;base64," not in inline_markdown:
            pytest.skip(
                "Pré-visualização requer conversão para PNG (cairosvg) para exibir inline."
            )
    download_md = preview.get("download_markdown", "")
    if download_md:
        assert download_md.startswith("[Abrir diagrama em SVG]")
    primary_preview = preview.get("primary_preview")
    assert primary_preview
    messages = preview.get("preview_messages")
    assert messages and all(msg.startswith("###") for msg in messages)

    replacements = diagramador_agent_module._collect_layout_preview_replacements(preview)
    assert replacements.get("{diagram_img_png}", "").count("data:image/png;base64,") >= 1
    assert replacements.get("{link_diagrama_svg_base64}", "").count(
        "data:image/svg+xml;base64,"
    ) >= 1


def test_generate_layout_preview_without_session_state_uses_fallback(sample_payload):
    result = generate_layout_preview(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        view_filter=None,
        session_state=None,
    )
    assert result["status"] == "ok"
    assert result["artifact"] == SESSION_ARTIFACT_LAYOUT_PREVIEW

    preview = get_cached_artifact(None, SESSION_ARTIFACT_LAYOUT_PREVIEW)
    assert preview is not None
    assert preview.get("view_count", 0) >= 1
    if any(view.get("layout_preview") is None for view in preview.get("views", [])):
        pytest.skip("Pré-visualização requer svgwrite para gerar o layout.")
    primary = preview.get("primary_preview")
    if primary and primary.get("inline_markdown"):
        inline = primary["inline_markdown"]
        if "data:image/png;base64," not in inline:
            pytest.skip(
                "Pré-visualização requer conversão para PNG (cairosvg) para exibir inline."
            )
    replacements = diagramador_agent_module._collect_layout_preview_replacements(preview)
    assert replacements.get("{diagram_img_png}", "").count("data:image/png;base64,") >= 1
    assert replacements.get("{link_diagrama_svg_base64}", "").count(
        "data:image/svg+xml;base64,"
    ) >= 1


def test_generate_layout_preview_filters_views(sample_payload, session_state):
    describe_template(str(SAMPLE_TEMPLATE), view_filter=None, session_state=session_state)
    finalize_datamodel(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )
    result = generate_layout_preview(
        None,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
        view_filter=["id-154903"],
    )
    assert result["status"] == "ok"
    assert result["artifact"] == SESSION_ARTIFACT_LAYOUT_PREVIEW
    assert result["view_count"] == 1
    assert set(result.keys()) <= {"status", "artifact", "view_count", "message"}
    if "message" in result:
        assert result["message"] == "Pré-visualização armazenada com sucesso."
    preview = get_cached_artifact(
        session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW
    )
    assert preview["view_count"] == 1
    assert preview["views"][0]["id"] == "id-154903"
    if preview["views"][0].get("layout_preview") is None:
        pytest.skip("Pré-visualização requer svgwrite para gerar o layout.")
    assert "previews" not in result
    assert "primary_preview" not in result

def test_generate_layout_preview_filters_views_with_string(sample_payload, session_state):
    describe_template(str(SAMPLE_TEMPLATE), view_filter=None, session_state=session_state)
    finalize_datamodel(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )
    result = generate_layout_preview(
        None,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
        view_filter="id-154903,  id-12345",
    )
    assert result["status"] == "ok"
    assert result["artifact"] == SESSION_ARTIFACT_LAYOUT_PREVIEW
    assert result["view_count"] == 1
    assert set(result.keys()) <= {"status", "artifact", "view_count", "message"}
    if "message" in result:
        assert result["message"] == "Pré-visualização armazenada com sucesso."
    preview = get_cached_artifact(
        session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW
    )
    assert preview["view_count"] == 1
    assert preview["views"][0]["id"] == "id-154903"
    if preview["views"][0].get("layout_preview") is None:
        pytest.skip("Pré-visualização requer svgwrite para gerar o layout.")
    assert "previews" not in result
    assert "primary_preview" not in result


def test_finalize_generates_preview_with_view_focus(sample_payload, session_state):
    describe_template(
        str(SAMPLE_TEMPLATE),
        view_filter="id-154903",
        session_state=session_state,
    )
    finalize_datamodel(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )
    preview = get_cached_artifact(
        session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW
    )
    assert preview["view_count"] == 1
    assert preview["views"][0]["id"] == "id-154903"

    result = generate_layout_preview(
        None,
        str(SAMPLE_TEMPLATE),
        view_filter=None,
        session_state=session_state,
    )
    assert result["status"] == "ok"
    assert result["artifact"] == SESSION_ARTIFACT_LAYOUT_PREVIEW
    assert result["view_count"] == 1
    assert set(result.keys()) <= {"status", "artifact", "view_count", "message"}
    if "message" in result:
        assert result["message"] == "Pré-visualização armazenada com sucesso."
    updated_preview = get_cached_artifact(
        session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW
    )
    assert updated_preview["view_count"] == 1
    assert updated_preview["views"][0]["id"] == "id-154903"
    if updated_preview["views"][0].get("layout_preview") is None:
        pytest.skip("Pré-visualização requer svgwrite para gerar o layout.")

def test_save_and_generate_archimate_diagram(tmp_path, sample_payload, session_state):
    # Redireciona os artefatos para um diretório temporário.
    operations.OUTPUT_DIR = tmp_path  # type: ignore[attr-defined]

    finalize_datamodel(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )

    result = save_datamodel(
        None,
        filename="test_datamodel.json",
        session_state=session_state,
    )
    assert result["status"] == "ok"
    saved_artifact = get_cached_artifact(
        session_state, SESSION_ARTIFACT_SAVED_DATAMODEL
    )
    saved_path = Path(saved_artifact["path"])
    assert saved_path.exists()

    xml_result = generate_archimate_diagram(
        None,
        output_filename="test_diagram.xml",
        template_path=str(SAMPLE_TEMPLATE),
        validate=True,
        xsd_dir=None,
        session_state=session_state,
    )
    assert xml_result["status"] == "ok"
    xml_artifact = get_cached_artifact(
        session_state, SESSION_ARTIFACT_ARCHIMATE_XML
    )
    xml_path = Path(xml_artifact["path"])
    assert xml_path.exists()
    assert xml_artifact["validation_report"]["valid"] is True


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
