import ast
from types import SimpleNamespace

import pytest

from app.tools.search import discovery_engine_search as des


ORIGINAL_DISCOVERYENGINE = des.discoveryengine
ORIGINAL_CLIENT_OPTIONS = des.ClientOptions
ORIGINAL_LOAD_LOCAL_ACRONYMS = des._load_local_acronyms


@pytest.fixture(autouse=True)
def restore_dependencies(monkeypatch):
    """Ensure each test starts with a clean dependency state."""
    monkeypatch.setattr(des, "discoveryengine", ORIGINAL_DISCOVERYENGINE, raising=False)
    monkeypatch.setattr(des, "ClientOptions", ORIGINAL_CLIENT_OPTIONS, raising=False)
    monkeypatch.setattr(des, "_load_local_acronyms", ORIGINAL_LOAD_LOCAL_ACRONYMS, raising=False)
    monkeypatch.delenv("SUGGEST_ACRONYMS", raising=False)
    monkeypatch.delenv("SUGGEST_ACRONYMS_LIMIT", raising=False)
    yield


def test_discovery_search_tool_returns_fallback_when_sdk_missing(caplog, monkeypatch):
    monkeypatch.setattr(des, "discoveryengine", None)
    monkeypatch.setattr(des, "ClientOptions", None)

    caplog.set_level("WARNING")
    result = des.discovery_search_tool("architecture diagram", des.ToolContext())

    assert result == "[]"
    assert "client libraries not available" in caplog.text


def test_discovery_search_tool_returns_fallback_when_configuration_incomplete(monkeypatch, caplog):
    class DummyClientOptions:
        def __init__(self, api_endpoint: str):  # pragma: no cover - simple holder
            self.api_endpoint = api_endpoint

    fake_module = SimpleNamespace(
        SearchServiceClient=lambda *_, **__: pytest.fail("Search should not be called when config is incomplete"),
        SearchRequest=None,
    )

    monkeypatch.setattr(des, "discoveryengine", fake_module)
    monkeypatch.setattr(des, "ClientOptions", DummyClientOptions)

    monkeypatch.delenv("DISCOVERY_PROJECT_ID", raising=False)
    monkeypatch.delenv("DISCOVERY_ENGINE_ID", raising=False)
    monkeypatch.setenv("DISCOVERY_LOCATION", "us")

    caplog.set_level("WARNING")
    result = des.discovery_search_tool("architecture diagram", des.ToolContext())

    assert result == "[]"
    assert "configuration incomplete" in caplog.text


def test_discovery_search_tool_executes_search_when_dependencies_present(monkeypatch):
    captured = {}

    class DummyClientOptions:
        def __init__(self, api_endpoint: str):
            self.api_endpoint = api_endpoint
            captured["api_endpoint"] = api_endpoint

    class DummyQueryExpansionSpec:
        class Condition:
            AUTO = "auto"

        def __init__(self, condition):
            captured.setdefault("query_expansion_conditions", []).append(condition)

    class DummySpellCorrectionSpec:
        class Mode:
            SUGGESTION_ONLY = "suggestion"

        def __init__(self, mode):
            captured.setdefault("spell_correction_modes", []).append(mode)

    class DummySearchRequest:
        QueryExpansionSpec = DummyQueryExpansionSpec
        SpellCorrectionSpec = DummySpellCorrectionSpec

        def __init__(self, **kwargs):
            captured["request_kwargs"] = kwargs

    class DummySearchServiceClient:
        def __init__(self, client_options=None):
            captured["client_options"] = client_options

        def search(self, request):
            captured["request"] = request
            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        rank_signals=SimpleNamespace(semantic_similarity_score=0.8),
                        document=SimpleNamespace(
                            struct_data={
                                "u_acronym": "ARCH",
                                "u_tribe_name": "Architecture",
                                "u_service_classification": "Core",
                                "comments": "Ready",
                                "u_squad_name": "Infra",
                                "u_install_status": "prod",
                                "u_tower": "Platform",
                                "environment": "prod",
                            }
                        ),
                    )
                ]
            )

    fake_module = SimpleNamespace(
        SearchServiceClient=DummySearchServiceClient,
        SearchRequest=DummySearchRequest,
    )

    monkeypatch.setattr(des, "discoveryengine", fake_module)
    monkeypatch.setattr(des, "ClientOptions", DummyClientOptions)

    monkeypatch.setenv("DISCOVERY_PROJECT_ID", "my-project")
    monkeypatch.setenv("DISCOVERY_LOCATION", "us-central1")
    monkeypatch.setenv("DISCOVERY_ENGINE_ID", "engine-1")

    result = des.discovery_search_tool("cloud", des.ToolContext())

    assert captured["api_endpoint"] == "us-central1-discoveryengine.googleapis.com"
    assert captured["client_options"].api_endpoint == captured["api_endpoint"]
    assert captured["request_kwargs"]["serving_config"] == (
        "projects/my-project/locations/us-central1/collections/default_collection/"
        "engines/engine-1/servingConfigs/default_config"
    )

    formatted = ast.literal_eval(result)
    assert formatted == [
        {
            "u_acronym": "ARCH",
            "u_tribe_name": "Architecture",
            "u_service_classification": "Core",
            "comments": "Ready",
            "u_squad_name": "Infra",
            "u_install_status": "prod",
            "u_tower": "Platform",
            "environment": "prod",
            "similarity_score": 0.8,
        }
    ]


def test_filter_and_format_documents_orders_by_similarity():
    low = SimpleNamespace(
        rank_signals=SimpleNamespace(semantic_similarity_score=0.4),
        document=SimpleNamespace(struct_data={"u_acronym": "LOW"}),
    )
    medium = SimpleNamespace(
        rank_signals=SimpleNamespace(semantic_similarity_score=0.7),
        document=SimpleNamespace(struct_data={"u_acronym": "MED"}),
    )
    high = SimpleNamespace(
        rank_signals=SimpleNamespace(semantic_similarity_score=0.9),
        document=SimpleNamespace(struct_data={"u_acronym": "HIGH"}),
    )

    result = des._filter_and_format_documents([low, medium, high], similarity_threshold=0.6)

    assert [doc["u_acronym"] for doc in result] == ["HIGH", "MED"]
    assert all(score >= 0.6 for score in [doc["similarity_score"] for doc in result])


def test_discovery_search_tool_suggests_when_enabled(monkeypatch):
    monkeypatch.setattr(des, "discoveryengine", None)
    monkeypatch.setattr(des, "ClientOptions", None)
    monkeypatch.setenv("SUGGEST_ACRONYMS", "true")

    def fake_loader():
        return [
            {
                "u_acronym": "ARCH",
                "comments": "Plataforma de arquitetura em nuvem",
                "u_install_status": "Em Uso",
                "environment": "Produção",
                "u_service_classification": "Serviço",
                "u_tower": "Arquitetura",
                "u_squad_name": "Cloud",
                "u_tribe_name": "Tech",
            },
            {
                "u_acronym": "TEST",
                "comments": "Ambiente de testes",
                "u_install_status": "Em Uso",
                "environment": "Homologação",
                "u_service_classification": "Serviço",
                "u_tower": "QA",
                "u_squad_name": "QA",
                "u_tribe_name": "Tech",
            },
        ]

    monkeypatch.setattr(des, "_load_local_acronyms", fake_loader)

    result = ast.literal_eval(des.discovery_search_tool("Arquitetura de soluções em nuvem", des.ToolContext()))

    assert result
    assert result[0]["u_acronym"] == "ARCH"
    assert 0 < result[0]["similarity_score"] <= 1


def test_discovery_search_tool_respects_disabled_suggestions(monkeypatch):
    monkeypatch.setattr(des, "discoveryengine", None)
    monkeypatch.setattr(des, "ClientOptions", None)
    monkeypatch.setattr(des, "_load_local_acronyms", lambda: [
        {
            "u_acronym": "ARCH",
            "comments": "Plataforma de arquitetura",
            "u_install_status": "Em Uso",
            "environment": "Produção",
            "u_service_classification": "Serviço",
            "u_tower": "Arquitetura",
            "u_squad_name": "Cloud",
            "u_tribe_name": "Tech",
        }
    ])

    result = des.discovery_search_tool("Arquitetura em nuvem", des.ToolContext())

    assert result == "[]"


def test_suggestions_return_all_matches_without_limit(monkeypatch):
    monkeypatch.setattr(des, "discoveryengine", None)
    monkeypatch.setattr(des, "ClientOptions", None)
    monkeypatch.setenv("SUGGEST_ACRONYMS", "1")

    def fake_loader():
        return [
            {
                "u_acronym": "FULL",
                "comments": "Serviço dados integrações pagamentos financeiros",
                "environment": "Produção",
            },
            {
                "u_acronym": "MOST",
                "comments": "Serviço dados integrações pagamentos",
                "environment": "Produção",
            },
            {
                "u_acronym": "SOME",
                "comments": "Serviço dados integrações",
                "environment": "Produção",
            },
            {
                "u_acronym": "MIN",
                "comments": "Serviço dados",
                "environment": "Produção",
            },
        ]

    monkeypatch.setattr(des, "_load_local_acronyms", fake_loader)

    result = ast.literal_eval(
        des.discovery_search_tool(
            "Serviço de dados financeiros integrações pagamentos",
            des.ToolContext(),
        )
    )

    assert [item["u_acronym"] for item in result] == ["FULL", "MOST", "SOME", "MIN"]
    assert all(item["similarity_score"] <= 1 for item in result)


def test_suggestions_respect_configured_limit(monkeypatch):
    monkeypatch.setattr(des, "discoveryengine", None)
    monkeypatch.setattr(des, "ClientOptions", None)
    monkeypatch.setenv("SUGGEST_ACRONYMS", "true")
    monkeypatch.setenv("SUGGEST_ACRONYMS_LIMIT", "2")

    def fake_loader():
        return [
            {
                "u_acronym": "FULL",
                "comments": "Serviço dados integrações pagamentos financeiros",
                "environment": "Produção",
            },
            {
                "u_acronym": "MOST",
                "comments": "Serviço dados integrações pagamentos",
                "environment": "Produção",
            },
            {
                "u_acronym": "SOME",
                "comments": "Serviço dados integrações",
                "environment": "Produção",
            },
        ]

    monkeypatch.setattr(des, "_load_local_acronyms", fake_loader)

    result = ast.literal_eval(
        des.discovery_search_tool(
            "Serviço de dados financeiros integrações pagamentos",
            des.ToolContext(),
        )
    )

    assert [item["u_acronym"] for item in result] == ["FULL", "MOST"]
