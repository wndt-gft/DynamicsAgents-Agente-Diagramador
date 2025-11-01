from __future__ import annotations

import importlib
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

import pytest


def _import_confirmation_module():
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return importlib.import_module(
        "agents.diagramador.app.tools.shared.diagram_generator.utilities.confirmation_handler"
    )


@pytest.fixture(autouse=True)
def _reset_confirmation_state() -> None:
    module = _import_confirmation_module()
    module.reset_confirmation_state()
    yield
    module.reset_confirmation_state()


class _StubDiagramService:
    """Lightweight stand-in for the heavy legacy service used by the tool."""

    template_name = "C4-Model"

    def __init__(self, xml_path: Path):
        self._xml_path = xml_path
        self._allowed_element_types = {
            "ApplicationComponent",
            "ApplicationCollaboration",
            "TechnologyService",
            "DataObject",
        }
        self.calls: List[Dict[str, Any]] = []
        self.last_call: Dict[str, Any] = {}

    @staticmethod
    def _coerce_to_text(value: Any, *, allow_iterable: bool = True) -> str:  # pragma: no cover - parity shim
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple, set)) and allow_iterable:
            return ", ".join(str(item) for item in value if item)
        return str(value)

    def _get_allowed_element_types(self) -> List[str]:
        return sorted(self._allowed_element_types)

    def process_mapped_elements(
        self,
        elements: List[Dict[str, Any]],
        relationships: Optional[List[Dict[str, Any]]],
        diagram_type: str,
        system_name: str,
        steps_labels: List[str],
    ) -> Dict[str, Any]:
        call_payload = {
            "elements": elements,
            "relationships": relationships,
            "steps": steps_labels,
            "system": system_name,
            "diagram_type": diagram_type,
        }
        self.last_call = call_payload
        self.calls.append(call_payload)
        return {
            "success": True,
            "diagram_type": diagram_type,
            "xml_content": "id",  # força o código a ler o arquivo salvo
            "filename": f"out_{diagram_type}.xml",
            "local_file_path": str(self._xml_path),
            "template_name": "C4-Model",
            "metadata": {
                "total_elements": len(elements),
                "total_relationships": len(relationships or []),
            },
            "quality_report": {},
            "compliance_summary": {},
        }


@pytest.fixture()
def tool_with_stub(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Tuple[Any, _StubDiagramService]:
    module = importlib.import_module(
        "agents.diagramador.app.tools.interactions.diagram_generator_tool.tool"
    )

    xml_path = tmp_path / "out.xml"
    xml_path.write_text("<model/>", encoding="utf-8")

    service = _StubDiagramService(xml_path)
    monkeypatch.setattr(module, "DiagramService", lambda: service)
    monkeypatch.setattr(
        module,
        "upload_xml_to_gcs",
        lambda xml, filename, bucket_name, project, expiration_hours: (
            f"gs://{bucket_name}/{filename}",
            f"https://example.com/{filename}",
        ),
    )
    tool = module.Tool()
    return tool, service


@pytest.mark.unit
def test_generate_diagram_creates_data_url_when_upload_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = importlib.import_module(
        "agents.diagramador.app.tools.interactions.diagram_generator_tool.tool"
    )

    xml_path = tmp_path / "out.xml"
    xml_path.write_text("<model/>", encoding="utf-8")

    service = _StubDiagramService(xml_path)
    monkeypatch.setattr(module, "DiagramService", lambda: service)

    def failing_upload(*_a, **_kw):  # noqa: ANN001
        raise RuntimeError("no credentials")

    monkeypatch.setattr(module, "upload_xml_to_gcs", failing_upload)

    tool = module.Tool()
    result = tool.generate_diagram(
        system_name={"name": "Sistema"},
        elements={
            "layer_1": [{"name": "Canal", "type": "ApplicationCollaboration"}],
            "layer_2": [{"name": "Backend", "type": "ApplicationComponent"}],
        },
        relationships=[{"source": "Canal", "target": "Backend", "label": "Usa"}],
        steps=[{"description": "Fluxo"}],
    )

    last_result = result["diagram"]["last_result"]
    artifact = last_result["artifact"]
    assert artifact["signed_url"].startswith("file:")
    saved = Path(artifact["local_path"]).read_text(encoding="utf-8").strip()
    assert saved == "<model/>"


@pytest.mark.unit
def test_generate_diagram_resolves_state_and_reads_xml(
    tool_with_stub: Tuple[Any, _StubDiagramService]
) -> None:
    tool, service = tool_with_stub

    state = {
        "analysis": {
            "system_name": {"name": "Sistema de Transferências PIX"},
            "elements": {
            "layer_1": [
                {
                    "name": "Mobile App",
                    "type": "ApplicationCollaboration",
                    "description": "Canal móvel",
                },
                {
                    "name": "Internet Banking",
                    "type": "ApplicationCollaboration",
                    "description": "Canal web",
                },
            ],
                "layer_4": [
                    {
                        "name": "HSM",
                        "type": "TechnologyService",
                        "description": "Protege chaves PIX",
                    }
                ],
            },
            "relationships": [
                {
                    "source": "Mobile App/Internet Banking",
                    "target": "HSM",
                    "label": "Acessa chaves seguras",
                }
            ],
            "steps": {
                "process_steps": [
                    {"description": "Cliente inicia a transferência", "step": 1},
                    {"description": "Serviço valida chaves", "step": 2},
                ]
            },
        }
    }

    result = tool.generate_diagram(
        system_name={"$state": "analysis.system_name"},
        elements={"$state": "analysis.elements"},
        relationships={"$state": "analysis.relationships"},
        steps={"$state": "analysis.steps"},
        state=state,
    )

    diagram_info = result["diagram"]
    last_result = diagram_info["last_result"]

    stored_xml = Path(last_result["local_path"]).read_text(encoding="utf-8").strip()
    assert stored_xml == "<model/>"
    assert last_result["steps_count"] == 2
    assert last_result["steps_preview"][0].startswith("Cliente inicia")
    container_call = service.calls[-1]
    assert container_call["system"] == "Sistema de Transferências PIX"
    assert len(container_call["elements"]) == 3
    ids_by_name = {element["name"]: element["id"] for element in container_call["elements"]}
    assert ids_by_name["Mobile App"] == "mobileapp"
    assert ids_by_name["Internet Banking"] == "internetbanking"


@pytest.mark.unit
def test_generate_diagram_uses_confirmation_snapshot(
    tool_with_stub: Tuple[Any, _StubDiagramService]
) -> None:
    tool, service = tool_with_stub

    approved = {
        "system_name": "Sistema Confirmado",
        "elements": {
            "layer_1": [
                {"name": "Canal", "type": "ApplicationCollaboration"},
            ],
            "layer_2": [
                {"name": "Backend", "type": "ApplicationComponent"},
            ],
        },
        "relationships": [
            {"source": "Canal", "target": "Backend", "label": "Usa"},
        ],
        "steps": [
            {"description": "Fluxo confirmado"},
        ],
    }

    state = {
        "confirmation": {
            "approved_analysis": approved,
            "approved_elements": approved["elements"],
            "approved_relationships": approved["relationships"],
            "approved_steps": approved["steps"],
            "approved_system_name": approved["system_name"],
        }
    }

    result = tool.generate_diagram(
        system_name=None,
        elements=None,
        relationships=None,
        steps=None,
        state=state,
    )

    diagram_info = result["diagram"]
    last_result = diagram_info["last_result"]

    assert last_result["system"] == "Sistema Confirmado"
    assert service.last_call["system"] == "Sistema Confirmado"
    assert len(service.last_call["elements"]) == 2
    assert service.last_call["relationships"][0]["source"] == "Canal"
    assert last_result["steps_count"] == 1


@pytest.mark.unit
def test_generate_diagram_accepts_complex_state_pointers(
    tool_with_stub: Tuple[Any, _StubDiagramService]
) -> None:
    tool, service = tool_with_stub

    state = {
        "analysis": {
            "system_name": {"name": "Hub de Pagamentos"},
            "elements": {
                "layer_1": [
                    {
                        "name": "App Mobile",
                        "type": "ApplicationCollaboration",
                        "description": "Canal mobile",
                    }
                ],
            },
            "relationships": [
                {
                    "source": "App Mobile",
                    "target": "Core PIX",
                    "label": "Envia requisições",
                }
            ],
            "steps": {
                "process_steps": [
                    {"description": "Cliente inicia pagamento", "step": 1},
                    {"description": "Sistema processa PIX", "step": 2},
                ]
            },
        }
    }

    result = tool.generate_diagram(
        system_name={"$state": {"segments": ["analysis", "system_name"]}},
        elements={"$state": {"path": ["analysis", "elements"]}},
        relationships={"$state": {"value": ["analysis", "relationships"]}},
        steps={"$state": {"path": "analysis.steps.process_steps"}},
        state=state,
    )

    assert result["diagram"]["last_result"]["steps_count"] == 2
    assert service.calls[-1]["relationships"]


@pytest.mark.unit
def test_generate_diagram_uses_global_confirmation_snapshot(
    tool_with_stub: Tuple[Any, _StubDiagramService],
) -> None:
    tool, service = tool_with_stub

    approved = {
        "system_name": "Sistema Global",
        "elements": {
            "layer_1": [
                {"name": "Front", "type": "ApplicationCollaboration"},
            ],
            "layer_2": [
                {"name": "Core", "type": "ApplicationComponent"},
            ],
        },
        "relationships": [
            {"source": "Front", "target": "Core", "label": "Consome"},
        ],
        "steps": [
            {"description": "Fluxo global"},
        ],
    }

    confirmation_module = _import_confirmation_module()
    confirmation_module.update_approved_snapshot(approved)

    result = tool.generate_diagram(
        system_name=None,
        elements=None,
        relationships=None,
        steps=None,
        state={},
    )

    last_result = result["diagram"]["last_result"]
    assert last_result["system"] == "Sistema Global"
    assert service.last_call["system"] == "Sistema Global"
    assert len(service.last_call["elements"]) == 2
    assert service.last_call["relationships"][0]["label"] == "Consome"
    assert last_result["steps_count"] == 1


@pytest.mark.unit
def test_generate_diagram_uses_state_fallbacks(
    tool_with_stub: Tuple[Any, _StubDiagramService]
) -> None:
    tool, service = tool_with_stub

    state = {
        "analysis": {
            "last_presented": {
                "system_name": "Plataforma Cartões",
                "elements": {
                    "layer_2": [
                        {
                            "name": "Motor de Cartões",
                            "type": "ApplicationComponent",
                            "description": "Processa transações",
                        }
                    ],
                },
                "relationships": [
                    {
                        "source": "Motor de Cartões",
                        "target": "Banco de Dados",
                        "label": "Persiste operações",
                    }
                ],
                "steps": ["1. Cliente solicita cartão"],
            }
        }
    }

    result = tool.generate_diagram(
        system_name=None,
        elements=None,
        relationships=None,
        steps=None,
        state=state,
    )

    assert result["diagram"]["last_result"]["system"] == "Plataforma Cartões"
    assert any(el["name"] == "Motor de Cartões" for el in service.calls[-1]["elements"])
@pytest.mark.unit
def test_generate_diagram_auto_suggests_system_name(
    tool_with_stub: Tuple[Any, _StubDiagramService]
) -> None:
    tool, service = tool_with_stub

    result = tool.generate_diagram(
        system_name="",
        elements={
            "layer_1": [
                {
                    "name": "Canal Web",
                    "type": "ApplicationCollaboration",
                }
            ],
            "layer_2": [
                {
                    "name": "Plataforma PIX",
                    "type": "ApplicationComponent",
                }
            ],
        },
        relationships=[
            {"source": "Canal Web", "target": "Plataforma PIX", "label": "Acessa"}
        ],
        steps=["Fluxo"],
    )

    assert result["diagram"]["last_result"]["system"] == "Plataforma PIX"
    assert service.calls[-1]["system"] == "Plataforma PIX"


@pytest.mark.unit
def test_generate_diagram_discovers_nested_analysis_state(
    tool_with_stub: Tuple[Any, _StubDiagramService]
) -> None:
    tool, service = tool_with_stub

    state = {
        "phase_cache": {
            "analysis_bundle": {
                "system_name": {"name": "Orquestrador PIX"},
                "elements": {
                    "layer_channels": [
                        {
                            "name": "Canal Mobile",
                            "type": "ApplicationCollaboration",
                            "description": "Aplicativo bancário",
                        }
                    ],
                    "layer_execution": [
                        {
                            "name": "Serviço PIX",
                            "type": "ApplicationComponent",
                            "description": "Processa transferências instantâneas",
                        }
                    ],
                },
                "relationships": [
                    {
                        "source": "Canal Mobile",
                        "target": "Serviço PIX",
                        "label": "Inicia transação",
                    }
                ],
                "steps": [
                    "O cliente inicia a transferência pelo canal mobile.",
                ],
            }
        }
    }

    result = tool.generate_diagram(
        system_name={"$state": "analysis.system_name"},
        elements={"$state": "analysis.elements"},
        relationships={"$state": "analysis.relationships"},
        steps={"$state": "analysis.steps"},
        state=state,
    )

    assert service.calls[-1]["system"] == "Orquestrador PIX"
    assert any(el["name"] == "Serviço PIX" for el in service.calls[-1]["elements"])
    assert result["diagram"]["last_result"]["steps_count"] == 1


@pytest.mark.unit
def test_generate_diagram_honors_multiple_diagram_types(
    tool_with_stub: Tuple[Any, _StubDiagramService]
) -> None:
    tool, service = tool_with_stub

    state = {
        "analysis": {
            "system_name": {"name": "Hub PIX Omnicanal"},
            "elements": {
                "layer_1": [
                    {"name": "App Mobile", "type": "ApplicationCollaboration"},
                    {"name": "Internet Banking", "type": "ApplicationCollaboration"},
                ],
                "layer_3": [
                    {"name": "Serviço PIX", "type": "ApplicationComponent"},
                ],
            },
            "relationships": [
                {"source": "App Mobile", "target": "Serviço PIX", "label": "Inicia"},
                {"source": "Internet Banking", "target": "Serviço PIX", "label": "Processa"},
            ],
            "steps": [
                {"description": "Cliente autentica no canal"},
                {"description": "Serviço PIX valida limites"},
            ],
            "diagram_types": ["container", "context"],
            "user_story": (
                "Desejo diagramas Container e Contexto para mapear integrações PIX."
            ),
        }
    }

    result = tool.generate_diagram(
        system_name={"$state": "analysis.system_name"},
        elements={"$state": "analysis.elements"},
        relationships={"$state": "analysis.relationships"},
        steps={"$state": "analysis.steps"},
        state=state,
    )

    diagram_info = result["diagram"]
    confirmation = result["confirmation"]

    assert diagram_info["diagram_types"] == ["container", "context"]
    assert diagram_info["primary_type"] == "container"
    assert len(service.calls) == 2

    additional = diagram_info["additional_results"]
    assert additional, "Should expose additional diagram results when more than one type is generated"
    context_result = diagram_info["results_by_type"]["context"]
    assert context_result["diagram_type"] == "Contexto C4"
    assert context_result["filename"].endswith("out_context.xml")
    assert context_result["signed_url"].endswith("out_context.xml")
    assert confirmation["diagram_types"] == ["container", "context"]
    assert confirmation["additional_diagrams"][0]["diagram_key"] == "context"


@pytest.mark.unit
def test_generate_diagram_accepts_explicit_diagram_type_argument(
    tool_with_stub: Tuple[Any, _StubDiagramService],
) -> None:
    tool, service = tool_with_stub

    state = {
        "analysis": {
            "system_name": {"name": "Hub PIX Omnicanal"},
            "elements": {
                "layer_1": [
                    {"name": "App Mobile", "type": "ApplicationCollaboration"},
                ],
                "layer_3": [
                    {"name": "Serviço PIX", "type": "ApplicationComponent"},
                ],
            },
            "relationships": [
                {"source": "App Mobile", "target": "Serviço PIX", "label": "Inicia"},
            ],
            "steps": [
                {"description": "Cliente autentica no canal"},
            ],
        }
    }

    result = tool.generate_diagram(
        system_name={"$state": "analysis.system_name"},
        elements={"$state": "analysis.elements"},
        relationships={"$state": "analysis.relationships"},
        steps={"$state": "analysis.steps"},
        diagram_type="context",
        state=state,
    )

    diagram_info = result["diagram"]
    assert diagram_info["diagram_types"] == ["context"]
    assert diagram_info["primary_type"] == "context"
    assert [call["diagram_type"] for call in service.calls] == ["context"]


@pytest.mark.unit
def test_generate_diagram_accepts_explicit_diagram_types_list(
    tool_with_stub: Tuple[Any, _StubDiagramService],
) -> None:
    tool, service = tool_with_stub

    state = {
        "analysis": {
            "system_name": {"name": "Hub PIX Omnicanal"},
            "elements": {
                "layer_2": [
                    {"name": "API Gateway", "type": "TechnologyService"},
                ],
                "layer_3": [
                    {"name": "Serviço PIX", "type": "ApplicationComponent"},
                ],
            },
            "relationships": [
                {"source": "API Gateway", "target": "Serviço PIX", "label": "Encaminha"},
            ],
            "steps": [
                {"description": "Gateway valida credenciais"},
            ],
        }
    }

    result = tool.generate_diagram(
        system_name={"$state": "analysis.system_name"},
        elements={"$state": "analysis.elements"},
        relationships={"$state": "analysis.relationships"},
        steps={"$state": "analysis.steps"},
        diagram_types=["context", "component"],
        state=state,
    )

    diagram_info = result["diagram"]
    assert diagram_info["diagram_types"] == ["context", "component"]
    assert diagram_info["primary_type"] == "context"
    assert [call["diagram_type"] for call in service.calls] == ["context", "component"]


@pytest.mark.unit
def test_generate_diagram_explicit_all_keyword_generates_all_types(
    tool_with_stub: Tuple[Any, _StubDiagramService],
) -> None:
    tool, service = tool_with_stub

    state = {
        "analysis": {
            "system_name": {"name": "Hub PIX Omnicanal"},
            "elements": {
                "layer_1": [
                    {"name": "Canal Digital", "type": "ApplicationCollaboration"},
                ],
                "layer_3": [
                    {"name": "Serviço PIX", "type": "ApplicationComponent"},
                ],
                "layer_6": [
                    {"name": "DICT", "type": "ApplicationCollaboration"},
                ],
            },
            "relationships": [
                {"source": "Canal Digital", "target": "Serviço PIX", "label": "Solicita"},
                {"source": "Serviço PIX", "target": "DICT", "label": "Consulta"},
            ],
            "steps": [
                {"description": "Cliente envia solicitação"},
            ],
        }
    }

    result = tool.generate_diagram(
        system_name={"$state": "analysis.system_name"},
        elements={"$state": "analysis.elements"},
        relationships={"$state": "analysis.relationships"},
        steps={"$state": "analysis.steps"},
        diagram_types="todos",
        state=state,
    )

    diagram_info = result["diagram"]
    assert diagram_info["diagram_types"] == ["container", "context", "component"]
    assert [call["diagram_type"] for call in service.calls] == [
        "container",
        "context",
        "component",
    ]
