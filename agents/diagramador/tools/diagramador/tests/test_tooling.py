from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.diagramador.callbacks import after_model_response_callback
from agents.diagramador.tools.diagramador import (
    DEFAULT_TEMPLATE,
    SESSION_ARTIFACT_ARCHIMATE_XML,
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
    SESSION_ARTIFACT_SAVED_DATAMODEL,
    SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
    SESSION_ARTIFACT_TEMPLATE_LISTING,
    describe_template,
    finalize_datamodel,
    generate_archimate_diagram,
    generate_layout_preview,
    list_templates,
    save_datamodel,
)
from agents.diagramador.tools.diagramador.templates import load_template_blueprint
from agents.diagramador.tools.diagramador.session import (
    SESSION_STATE_ROOT,
    clear_fallback_session_state,
)

SAMPLE_DATAMODEL_FILE = (
    Path(__file__).resolve().parents[2]
    / "archimate_exchange"
    / "samples"
    / "pix_solution_case"
    / "pix_container_datamodel.json"
)

SAMPLE_TEMPLATE = DEFAULT_TEMPLATE


@pytest.fixture(autouse=True)
def reset_session_state():
    clear_fallback_session_state()
    yield
    clear_fallback_session_state()


@pytest.fixture()
def session_state() -> dict:
    return {}


@pytest.fixture()
def template_blueprint():
    return load_template_blueprint(SAMPLE_TEMPLATE)


def _load_sample_datamodel() -> dict:
    with SAMPLE_DATAMODEL_FILE.open(encoding="utf-8") as handler:
        return json.load(handler)


def test_list_templates_registers_artifact(session_state):
    response = list_templates(session_state=session_state)
    assert response["status"] == "ok"

    listing = session_state[SESSION_STATE_ROOT]["artifacts"][SESSION_ARTIFACT_TEMPLATE_LISTING]
    assert listing["count"] > 0
    assert any(
        Path(path).exists()
        for entry in listing["templates"]
        if (path := entry.get("absolute_path") or entry.get("path"))
    )


def test_describe_template_caches_guidance(session_state):
    response = describe_template(str(SAMPLE_TEMPLATE), view_filter=None, session_state=session_state)
    assert response["status"] == "ok"

    artifact = session_state[SESSION_STATE_ROOT]["artifacts"][SESSION_ARTIFACT_TEMPLATE_GUIDANCE]
    assert artifact["model"]["path"].endswith(SAMPLE_TEMPLATE.name)
    assert artifact["views"]


def test_generate_layout_preview_creates_replacements(session_state):
    datamodel = _load_sample_datamodel()
    generate_layout_preview(
        datamodel=datamodel,
        template_path=str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )

    artifact = session_state[SESSION_STATE_ROOT]["artifacts"][SESSION_ARTIFACT_LAYOUT_PREVIEW]
    replacements = artifact["replacements"]
    assert "layout_preview.inline" in replacements
    assert "data:image/svg+xml" in replacements["layout_preview.svg"]


def test_generate_layout_preview_requires_datamodel(session_state):
    with pytest.raises(ValueError):
        generate_layout_preview(
            datamodel=None,
            template_path=str(SAMPLE_TEMPLATE),
            session_state=session_state,
        )


def test_generate_layout_preview_detects_placeholders(session_state):
    datamodel = _load_sample_datamodel()
    datamodel = json.loads(json.dumps(datamodel))  # deep copy
    datamodel["views"]["diagrams"][0]["nodes"][2]["label"] = "[[Nome da Solução Do Usuário]]"

    with pytest.raises(ValueError):
        generate_layout_preview(
            datamodel=datamodel,
            template_path=str(SAMPLE_TEMPLATE),
            session_state=session_state,
        )


def test_generate_layout_preview_requires_customized_blueprint(
    session_state, template_blueprint
):
    datamodel = json.loads(json.dumps(template_blueprint))
    datamodel["model_name"] = "Modelo Base Genérico"
    datamodel.pop("views", None)

    with pytest.raises(ValueError) as exc_info:
        generate_layout_preview(
            datamodel=datamodel,
            template_path=str(SAMPLE_TEMPLATE),
            session_state=session_state,
        )

    assert "contexto do usuário" in str(exc_info.value)


def test_generate_layout_preview_replaces_template_placeholders(session_state):
    datamodel = _load_sample_datamodel()
    datamodel = json.loads(json.dumps(datamodel))

    generate_layout_preview(
        datamodel=datamodel,
        template_path=str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )

    artifact = session_state[SESSION_STATE_ROOT]["artifacts"][SESSION_ARTIFACT_LAYOUT_PREVIEW]
    layout_snapshot = json.dumps(artifact["view"]["layout"])
    assert "[[" not in layout_snapshot
    assert "{{" not in layout_snapshot
    layout_nodes = artifact["view"]["layout"]["nodes"]
    labels = {node.get("label") for node in layout_nodes if node.get("element_ref")}
    assert "Mobile Banking App" in labels
    assert "Conector SPI/BACEN" in labels
    connections = artifact["view"]["layout"]["connections"]
    connection_labels = {conn.get("label") for conn in connections if conn.get("relationship_ref")}
    assert "Roteamento autenticado" in connection_labels
    assert "Portal web envia requisições PIX" in connection_labels


def test_finalize_and_save_datamodel(session_state):
    payload = {
        "model_identifier": "id-model",
        "elements": [],
        "relations": [],
    }
    json_payload = json.dumps(payload)

    finalize_datamodel(json_payload, str(SAMPLE_TEMPLATE), session_state=session_state)
    final_artifact = session_state[SESSION_STATE_ROOT]["artifacts"][SESSION_ARTIFACT_FINAL_DATAMODEL]
    assert "json" in final_artifact

    save_response = save_datamodel(
        datamodel=None,
        filename="test_datamodel.json",
        session_state=session_state,
    )
    assert save_response["status"] == "ok"
    saved_path = Path(save_response["path"])
    assert saved_path.exists()
    assert saved_path.read_text(encoding="utf-8").strip().startswith("{")


def test_generate_archimate_diagram_uses_session_state(session_state):
    payload = {
        "model_identifier": "id-model",
        "elements": [],
        "relations": [],
    }
    json_payload = json.dumps(payload)
    finalize_datamodel(json_payload, str(SAMPLE_TEMPLATE), session_state=session_state)
    save_datamodel(datamodel=None, filename=None, session_state=session_state)

    response = generate_archimate_diagram(
        model_json_path=None,
        validate=False,
        session_state=session_state,
    )
    assert response["status"] == "ok"
    xml_path = Path(response["path"])
    assert xml_path.exists()

    artifact = session_state[SESSION_STATE_ROOT]["artifacts"][SESSION_ARTIFACT_ARCHIMATE_XML]
    assert artifact["path"] == str(xml_path)


def test_after_model_callback_replaces_placeholders(session_state):
    generate_layout_preview(
        datamodel=_load_sample_datamodel(),
        template_path=str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )

    llm_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                "Prévia inline: {{state.layout_preview.inline}}\n"
                                "Link SVG: [[state.layout_preview.download]]\n"
                                "URI: {{state.layout_preview.svg}}"
                            )
                        }
                    ]
                }
            }
        ]
    }

    after_model_response_callback(
        callback_context=SimpleNamespace(session_state=session_state),
        llm_response=llm_response,
    )

    rendered = llm_response["candidates"][0]["content"]["parts"][0]["text"]
    assert "{{state.layout_preview.inline}}" not in rendered
    assert "data:image/svg+xml" in rendered
    assert "<img " in rendered
    assert 'width="100%"' in rendered
