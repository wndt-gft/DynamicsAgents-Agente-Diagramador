from __future__ import annotations

import base64
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
    LayoutValidationError,
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
from agents.diagramador.tools.generate_layout_preview.tool import (
    generate_layout_preview as tool_generate_layout_preview,
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


def test_generate_layout_preview_populates_layer_elements(session_state):
    datamodel = _load_sample_datamodel()
    generate_layout_preview(
        datamodel=datamodel,
        template_path=str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )

    artifact = session_state[SESSION_STATE_ROOT]["artifacts"][SESSION_ARTIFACT_LAYOUT_PREVIEW]
    layout_nodes = artifact["view"]["layout"]["nodes"]

    element_refs = {
        node.get("element_ref") or node.get("elementRef")
        for node in layout_nodes
        if (node.get("element_ref") or node.get("elementRef"))
    }
    expected_refs = {
        "id-da18b5f4b21a4bdab0c63fa99d95ba91",
        "id-37401d37c1034a718ab785406022fc9c",
        "id-7b0c03d4f05a410da57057c7e0b1ad25",
        "id-89aef989c04f448294e301fac2bb9f67",
    }
    assert expected_refs <= element_refs

    layer_labels = {
        node.get("label") for node in layout_nodes if node.get("type") == "Container"
    }
    assert "Layer DATA MANAGEMENT" in layer_labels
    assert "Layer CHANNELS" in layer_labels


def test_generate_layout_preview_matches_view_without_accents(session_state):
    datamodel = _load_sample_datamodel()
    datamodel = json.loads(json.dumps(datamodel))

    diagrams = datamodel.setdefault("views", {}).get("diagrams") or []
    assert diagrams, "Sample datamodel must contain at least one diagram"
    diagrams[0].pop("id", None)
    diagrams[0].pop("identifier", None)
    diagrams[0]["name"] = "Visao de Container - Sistema de Transferencias PIX"

    generate_layout_preview(
        datamodel=datamodel,
        template_path=str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )

    artifact = session_state[SESSION_STATE_ROOT]["artifacts"][SESSION_ARTIFACT_LAYOUT_PREVIEW]
    assert artifact["view"]["identifier"]
    assert artifact["view"]["name"].startswith("Visao de Container")
    assert artifact["view"]["layout"]["nodes"]


def test_generate_layout_preview_populates_layers_when_view_missing(session_state):
    datamodel = {
        "model_identifier": "auto-layer-test",
        "model_name": "Plataforma PIX Teste",
        "elements": [
            {
                "id": "elem-channel",
                "type": "ApplicationComponent",
                "name": "App Mobile Varejo",
                "documentation": "Canal digital onde o cliente inicia transferências PIX.",
            },
            {
                "id": "elem-inbound",
                "type": "TechnologyService",
                "name": "API Gateway Central",
                "documentation": "Gateway de entrada com autenticação e roteamento.",
            },
            {
                "id": "elem-exec",
                "type": "ApplicationComponent",
                "name": "Motor Orquestrador PIX",
                "documentation": "Serviço core que coordena validações e liquidação.",
            },
            {
                "id": "elem-data",
                "type": "DataObject",
                "name": "Banco de Dados PIX",
                "documentation": "Base transacional com histórico de transferências.",
            },
            {
                "id": "elem-outbound",
                "type": "TechnologyService",
                "name": "Serviço de Notificações Push",
                "documentation": "Canal outbound que envia alertas ao cliente.",
            },
            {
                "id": "elem-external",
                "type": "ApplicationCollaboration",
                "name": "DICT BACEN",
                "documentation": "Integração com diretório de chaves do Banco Central.",
            },
        ],
        "relations": [
            {
                "id": "rel-1",
                "source": "elem-channel",
                "target": "elem-inbound",
                "type": "Triggering",
                "label": "Inicia requisição",
            },
            {
                "id": "rel-2",
                "source": "elem-inbound",
                "target": "elem-exec",
                "type": "Serving",
                "label": "Encaminha",
            },
            {
                "id": "rel-3",
                "source": "elem-exec",
                "target": "elem-data",
                "type": "Access",
                "label": "Persiste",
            },
            {
                "id": "rel-4",
                "source": "elem-exec",
                "target": "elem-outbound",
                "type": "Serving",
                "label": "Notifica",
            },
            {
                "id": "rel-5",
                "source": "elem-exec",
                "target": "elem-external",
                "type": "Triggering",
                "label": "Consulta",
            },
        ],
        "views": {
            "diagrams": [
                {
                    "id": "id-171323",
                    "name": "Visão de Container - Plataforma PIX Teste",
                    "nodes": [],
                    "connections": [],
                }
            ]
        },
    }

    generate_layout_preview(
        datamodel=datamodel,
        template_path=str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )

    artifact = session_state[SESSION_STATE_ROOT]["artifacts"][SESSION_ARTIFACT_LAYOUT_PREVIEW]
    layout = artifact["view"]["layout"]
    layout_nodes = layout["nodes"]

    element_refs = {
        node.get("element_ref")
        for node in layout_nodes
        if node.get("element_ref")
    }
    assert {"elem-channel", "elem-inbound", "elem-exec", "elem-data", "elem-outbound", "elem-external"} <= element_refs

    container_labels = {
        node.get("label") for node in layout_nodes if node.get("type") == "Container"
    }
    assert "Layer GATEWAY INBOUND" in container_labels
    assert "Layer DATA MANAGEMENT" in container_labels
    assert "Layer GATEWAY OUTBOUND" in container_labels

    connections = layout.get("connections", [])
    assert len(connections) == len(datamodel["relations"])
    connection_refs = {conn.get("relationship_ref") for conn in connections}
    assert set(rel["id"] for rel in datamodel["relations"]) == connection_refs

    step_labels = [
        node.get("label")
        for node in layout_nodes
        if node.get("type") == "Label" and isinstance(node.get("label"), str)
    ]
    assert any("1." in label for label in step_labels)

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


def test_generate_layout_preview_reports_non_customized_element_names(
    session_state, template_blueprint
):
    datamodel = _load_sample_datamodel()
    datamodel = json.loads(json.dumps(datamodel))

    target_id = "id-da18b5f4b21a4bdab0c63fa99d95ba91"
    blueprint_element = next(
        element
        for element in template_blueprint["elements"]
        if element.get("id") == target_id or element.get("identifier") == target_id
    )
    datamodel_element = next(
        element for element in datamodel["elements"] if element.get("id") == target_id
    )
    datamodel_element["name"] = blueprint_element.get("name")
    if blueprint_element.get("documentation"):
        datamodel_element["documentation"] = blueprint_element.get("documentation")

    with pytest.raises(LayoutValidationError) as exc_info:
        generate_layout_preview(
            datamodel=datamodel,
            template_path=str(SAMPLE_TEMPLATE),
            session_state=session_state,
        )

    message = str(exc_info.value)
    assert "Itens não personalizados" in message
    assert "nome='Data Application Component'" in message
    assert exc_info.value.reason == "template_content_not_customized"


def test_generate_layout_preview_tool_returns_structured_error(
    session_state, template_blueprint
):
    datamodel = _load_sample_datamodel()
    datamodel = json.loads(json.dumps(datamodel))

    target_id = "id-da18b5f4b21a4bdab0c63fa99d95ba91"
    blueprint_element = next(
        element
        for element in template_blueprint["elements"]
        if element.get("id") == target_id or element.get("identifier") == target_id
    )
    datamodel_element = next(
        element for element in datamodel["elements"] if element.get("id") == target_id
    )
    datamodel_element["name"] = blueprint_element.get("name")
    if blueprint_element.get("documentation"):
        datamodel_element["documentation"] = blueprint_element.get("documentation")

    response = tool_generate_layout_preview(
        datamodel=json.dumps(datamodel),
        template_path=str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )

    assert response["status"] == "error"
    assert response["error"]["type"] == "layout_validation"
    assert response["error"]["reason"] == "template_content_not_customized"
    assert any(
        "Data Application Component" in issue for issue in response["error"]["issues"]
    )


def test_generate_layout_preview_overrides_blueprint_metadata(session_state):
    datamodel = _load_sample_datamodel()
    datamodel = json.loads(json.dumps(datamodel))

    element_id = "id-da18b5f4b21a4bdab0c63fa99d95ba91"
    relation_id = "rel-transfer-postgres"

    element = next(item for item in datamodel["elements"] if item["id"] == element_id)
    element["name"] = "Repositório Transacional PIX"
    element["documentation"] = (
        "Armazena com segurança as transferências concluídas para fins de auditoria."
    )

    relation = next(item for item in datamodel["relations"] if item["id"] == relation_id)
    relation["name"] = "Fluxo de persistência transacional"
    relation["documentation"] = (
        "Garante que cada transferência PIX seja gravada de forma consistente no banco."
    )

    generate_layout_preview(
        datamodel=datamodel,
        template_path=str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )

    artifact = session_state[SESSION_STATE_ROOT]["artifacts"][SESSION_ARTIFACT_LAYOUT_PREVIEW]
    layout_nodes = artifact["view"]["layout"]["nodes"]
    node = next(item for item in layout_nodes if item.get("element_ref") == element_id)
    assert node["label"] == element["name"]
    assert node["title"] == element["name"]
    assert node["documentation"] == element["documentation"]

    connections = artifact["view"]["layout"]["connections"]
    connection = next(
        item for item in connections if item.get("relationship_ref") == relation_id
    )
    assert connection["label"] == relation["name"]
    assert connection["documentation"] == relation["documentation"]


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


def test_generate_layout_preview_autolayouts_missing_nodes(session_state):
    datamodel = _load_sample_datamodel()
    datamodel = json.loads(json.dumps(datamodel))

    new_element_id = "id-auto-layout-test"
    datamodel["elements"].append(
        {
            "id": new_element_id,
            "type": "ApplicationComponent",
            "name": "Orquestrador de Antifraude",
            "documentation": "Elemento adicional para verificar autolayout automático.",
        }
    )

    view = datamodel["views"]["diagrams"][0]
    view.setdefault("child_order", []).append("node")
    view["nodes"].append(
        {
            "type": "ApplicationComponent",
            "elementRef": new_element_id,
            "label": "Orquestrador de Antifraude",
            "documentation": "Elemento adicional para verificar autolayout automático.",
        }
    )

    generate_layout_preview(
        datamodel=datamodel,
        template_path=str(SAMPLE_TEMPLATE),
        session_state=session_state,
    )

    artifact = session_state[SESSION_STATE_ROOT]["artifacts"][SESSION_ARTIFACT_LAYOUT_PREVIEW]
    layout_nodes = artifact["view"]["layout"]["nodes"]
    added = next(node for node in layout_nodes if node.get("element_ref") == new_element_id)
    bounds = added["bounds"]
    assert bounds["w"] > 0
    assert bounds["h"] > 0
    assert bounds["x"] != 0 or bounds["y"] != 0

    svg_data = artifact["render"]["svg_data_uri"]
    assert svg_data.startswith("data:image/svg+xml;base64,")
    svg_payload = svg_data.split(",", 1)[1]
    svg_text = base64.b64decode(svg_payload).decode("utf-8")
    assert "Orquestrador de Antifraude" in svg_text


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
