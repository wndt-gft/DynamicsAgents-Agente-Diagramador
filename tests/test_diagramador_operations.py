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


def test_list_templates_returns_entries(session_state):
    result = list_templates(session_state=session_state)
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


def test_describe_template_stores_blueprint(session_state):
    result = describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
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
    focus_tokens = get_view_focus(session_state)
    assert focus_tokens == ["id-154903".casefold()]


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
    describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
    finalize_datamodel(
        sample_payload,
        str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )
    with mock.patch(
        "tools.diagramador.operations._parse_template_blueprint",
        side_effect=AssertionError("template parse should not run when cached"),
    ):
        result = generate_layout_preview(
            None,
            str(SAMPLE_TEMPLATE),
            session_state=session_state,
        )
    assert result["status"] == "ok"
    preview = get_cached_artifact(
        session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW
    )
    datamodel_view_count = len(json.loads(sample_payload)["views"]["diagrams"])
    assert preview["view_count"] == datamodel_view_count
    layout_payloads = [view.get("layout_preview") for view in preview["views"]]
    if any(payload is None for payload in layout_payloads):
        pytest.skip("Pré-visualização requer svgwrite para gerar o layout.")
    assert all(payload["format"] == "svg" for payload in layout_payloads)
    assert all(Path(payload["local_path"]).exists() for payload in layout_payloads)
    assert all(payload["data_uri"].startswith("data:image/svg+xml;base64,") for payload in layout_payloads)
    assert all("<svg" in payload["inline_markdown"] for payload in layout_payloads)
    assert preview.get("preview_summaries")
    assert preview.get("artifacts")
    primary_preview = preview.get("primary_preview")
    assert primary_preview
    assert "<svg" in primary_preview["inline_markdown"]
    assert primary_preview["download_markdown"].startswith("<a ")
    assert primary_preview["download_uri"].startswith("data:image/")

    summaries = result.get("previews")
    assert summaries
    assert all("<svg" in summary["inline_markdown"] for summary in summaries)
    assert all(summary["download_uri"].startswith("data:image/") for summary in summaries)
    assert all(summary["download_markdown"].startswith("<a ") for summary in summaries)

    assert result.get("message")
    assert "<svg" in result.get("inline_markdown", "")
    assert result.get("download_markdown", "").startswith("<a ")
    primary_status_preview = result.get("primary_preview")
    assert primary_status_preview
    assert "<svg" in primary_status_preview["inline_markdown"]
    assert primary_status_preview["download_markdown"].startswith("<a ")
    assert primary_status_preview["download_uri"].startswith("data:image/")
    messages = result.get("preview_messages")
    assert messages and all(message.startswith("###") for message in messages)

    artifacts = result.get("artifacts")
    assert artifacts
    assert all(artifact.get("mime_type") for artifact in artifacts)


def test_generate_layout_preview_resolves_agent_relative_path(sample_payload):
    preview = generate_layout_preview(
        sample_payload,
        ALTERNATIVE_TEMPLATE_PATH,
        session_state=None,
    )
    assert preview["view_count"] >= 1
    if any(view.get("layout_preview") is None for view in preview["views"]):
        pytest.skip("Pré-visualização requer svgwrite para gerar o layout.")
    assert all("layout_preview" in view for view in preview["views"])
    assert all(
        view["layout_preview"]["data_uri"].startswith("data:image/svg+xml;base64,")
        for view in preview["views"]
        if view.get("layout_preview")
    )
    assert preview.get("preview_summaries")
    assert preview["preview_summaries"][0]["download_uri"].startswith("data:image/svg+xml;base64,")
    assert preview["preview_summaries"][0]["download_markdown"].startswith("<a ")
    assert preview.get("message")
    assert "<svg" in preview.get("inline_markdown", "")
    assert preview.get("download_markdown", "").startswith("<a ")
    primary_preview = preview.get("primary_preview")
    assert primary_preview
    assert primary_preview["download_uri"].startswith("data:image/svg+xml;base64,")
    messages = preview.get("preview_messages")
    assert messages and all(msg.startswith("###") for msg in messages)


def test_generate_layout_preview_filters_views(sample_payload, session_state):
    describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
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
    preview = get_cached_artifact(
        session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW
    )
    assert preview["view_count"] == 1
    assert preview["views"][0]["id"] == "id-154903"
    if preview["views"][0].get("layout_preview") is None:
        pytest.skip("Pré-visualização requer svgwrite para gerar o layout.")
    summaries = result.get("previews")
    assert summaries and len(summaries) == 1
    assert summaries[0]["download_uri"].startswith("data:image/svg+xml;base64,")
    assert result.get("message")
    assert "<svg" in result.get("inline_markdown", "")
    assert result.get("download_markdown", "").startswith("<a ")
    assert result.get("preview_messages")
    primary_preview = result.get("primary_preview")
    assert primary_preview
    assert "<svg" in primary_preview["inline_markdown"]


def test_generate_layout_preview_filters_views_with_string(sample_payload, session_state):
    describe_template(str(SAMPLE_TEMPLATE), session_state=session_state)
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
    preview = get_cached_artifact(
        session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW
    )
    assert preview["view_count"] == 1
    assert preview["views"][0]["id"] == "id-154903"
    if preview["views"][0].get("layout_preview") is None:
        pytest.skip("Pré-visualização requer svgwrite para gerar o layout.")
    summaries = result.get("previews")
    assert summaries and len(summaries) == 1
    assert summaries[0]["download_markdown"].startswith("<a ")
    primary_preview = result.get("primary_preview")
    assert primary_preview
    assert "<svg" in primary_preview["inline_markdown"]


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
        session_state=session_state,
    )
    assert result["status"] == "ok"
    updated_preview = get_cached_artifact(
        session_state, SESSION_ARTIFACT_LAYOUT_PREVIEW
    )
    assert updated_preview["view_count"] == 1
    assert updated_preview["views"][0]["id"] == "id-154903"


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
