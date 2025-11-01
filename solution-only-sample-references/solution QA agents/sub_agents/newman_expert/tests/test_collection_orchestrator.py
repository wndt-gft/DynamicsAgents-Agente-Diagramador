"""Tests for the Newman collection orchestrator tooling."""

from __future__ import annotations

import json
import importlib
import sys
import types
from typing import Any, Dict
from unittest.mock import Mock

import pytest


class _AutoStubModule(types.ModuleType):
    """Module that lazily creates child modules or stub classes on demand."""

    def __getattr__(self, item: str) -> Any:  # pragma: no cover - defensive
        qualified_name = f"{self.__name__}.{item}"
        if item and item[0].isupper():
            stub_class = type(item, (), {})
            setattr(self, item, stub_class)
            return stub_class
        if qualified_name not in sys.modules:
            child = _AutoStubModule(qualified_name)
            child.__path__ = []  # mark as package-like
            sys.modules[qualified_name] = child
        return sys.modules[qualified_name]


def _ensure_google_adk_stub() -> None:
    """Inject lightweight stubs for optional google.adk dependencies."""

    if "google" in sys.modules:
        return

    google_module = _AutoStubModule("google")
    google_module.__path__ = []
    sys.modules["google"] = google_module

    adk_module = _AutoStubModule("google.adk")
    adk_module.__path__ = []
    adk_module.Agent = type("Agent", (), {})
    google_module.adk = adk_module
    sys.modules["google.adk"] = adk_module

    tools_module = _AutoStubModule("google.adk.tools")
    tools_module.__path__ = []
    sys.modules["google.adk.tools"] = tools_module
    adk_module.tools = tools_module

    function_tool_module = _AutoStubModule("google.adk.tools.function_tool")
    function_tool_module.__path__ = []
    function_tool_module.FunctionTool = type("FunctionTool", (), {})
    sys.modules["google.adk.tools.function_tool"] = function_tool_module
    tools_module.function_tool = function_tool_module

    agents_module = _AutoStubModule("google.adk.agents")
    agents_module.__path__ = []
    sys.modules["google.adk.agents"] = agents_module
    adk_module.agents = agents_module

    callback_module = _AutoStubModule("google.adk.agents.callback_context")
    callback_module.__path__ = []
    callback_module.CallbackContext = type("CallbackContext", (), {})
    sys.modules["google.adk.agents.callback_context"] = callback_module
    agents_module.callback_context = callback_module


def _ensure_jsonschema_stub() -> None:
    if "jsonschema" in sys.modules:
        return

    class _Draft7Validator:
        def __init__(self, _schema: Dict[str, Any]):
            self.schema = _schema

        def iter_errors(self, _instance: Dict[str, Any]):  # pragma: no cover - simple stub
            return []

    module = types.ModuleType("jsonschema")
    module.Draft7Validator = _Draft7Validator
    sys.modules["jsonschema"] = module


def _ensure_yaml_stub() -> None:
    if "yaml" in sys.modules:
        return

    def _safe_load(payload: str) -> Dict[str, Any]:
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}

    module = types.ModuleType("yaml")
    module.safe_load = _safe_load
    sys.modules["yaml"] = module


@pytest.fixture
def orchestrator_module() -> Any:
    _ensure_google_adk_stub()
    _ensure_jsonschema_stub()
    _ensure_yaml_stub()
    return importlib.import_module(
        "app.sub_agents.newman_expert.tools.collection_orchestrator"
    )


@pytest.fixture
def sample_collection() -> Dict[str, Any]:
    """Return a minimal but valid Postman collection for validation tests."""

    return {
        "info": {
            "name": "Payments API",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            {
                "name": "Payments",
                "item": [
                    {
                        "name": "Create payment",
                        "request": {
                            "url": {
                                "raw": "https://api.example.com/payments",
                            }
                        },
                        "event": [
                            {
                                "listen": "test",
                                "script": {
                                    "exec": [
                                        "pm.test('payment succeeds', function () {",
                                        "  pm.expect(pm.response.code).to.have.status(200);",
                                        "  pm.expect(pm.response.code).to.have.status(400);",
                                        "});",
                                    ]
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }


@pytest.fixture
def orchestrator_patches(monkeypatch, orchestrator_module, sample_collection):
    build_mock = Mock(return_value=sample_collection)
    environments_mock = Mock(
        return_value={
            "dev": {"name": "dev", "values": []},
            "staging": {"name": "staging", "values": []},
        }
    )
    auth_mock = Mock(
        return_value={
            "bearer": {
                "info": {"name": "Bearer Auth"},
                "item": [],
            }
        }
    )
    monitoring_mock = Mock(return_value={"monitors": [], "alerts": []})
    collaboration_mock = Mock(return_value={"workspaces": ["payments"]})
    execution_mock = Mock(return_value={"strategy": "parallel"})
    ci_cd_mock = Mock(return_value={"github_workflow": "ci.yml"})
    data_driven_mock = Mock(
        return_value={
            "info": {"name": "Payments data"},
            "data_file": "data/payments.csv",
        }
    )
    security_mock = Mock(
        return_value={
            "info": {"name": "Security"},
            "checks": ["OWASP"],
        }
    )
    quality_mock = Mock(
        return_value={
            "score": 87,
            "penalties": [],
            "bonuses": [{"reason": "environments_present", "impact": 5}],
        }
    )

    modules_to_patch = {
        "app.sub_agents.newman_expert.tools.smart_collection_builder": (
            "build_smart_newman_collection",
            build_mock,
        ),
        "app.sub_agents.newman_expert.tools.environment_generator": (
            "generate_multi_environment_configs",
            environments_mock,
        ),
        "app.sub_agents.newman_expert.tools.auth_generator": (
            "generate_authentication_collections",
            auth_mock,
        ),
        "app.sub_agents.newman_expert.tools.monitoring_generator": (
            "generate_monitoring_config",
            monitoring_mock,
        ),
        "app.sub_agents.newman_expert.tools.collaboration_generator": (
            "generate_collaboration_features",
            collaboration_mock,
        ),
        "app.sub_agents.newman_expert.tools.execution_generator": (
            "generate_execution_strategies",
            execution_mock,
        ),
        "app.sub_agents.newman_expert.tools.ci_cd_generator": (
            "generate_ci_cd_integration",
            ci_cd_mock,
        ),
        "app.sub_agents.newman_expert.tools.data_driven_generator": (
            "generate_data_driven_tests",
            data_driven_mock,
        ),
        "app.sub_agents.newman_expert.tools.security_generator": (
            "generate_security_tests",
            security_mock,
        ),
        "app.sub_agents.newman_expert.tools.quality_validator": (
            "evaluate_newman_quality",
            quality_mock,
        ),
    }

    for module_path, (attr, mock_obj) in modules_to_patch.items():
        target_module = importlib.import_module(module_path)
        monkeypatch.setattr(target_module, attr, mock_obj)
        assert getattr(target_module, attr) is mock_obj

    monkeypatch.setattr(
        orchestrator_module,
        "evaluate_newman_quality",
        quality_mock,
        raising=False,
    )

    return orchestrator_module, {
        "build": build_mock,
        "environments": environments_mock,
        "auth": auth_mock,
        "monitoring": monitoring_mock,
        "collaboration": collaboration_mock,
        "execution": execution_mock,
        "ci_cd": ci_cd_mock,
        "data_driven": data_driven_mock,
        "security": security_mock,
        "quality": quality_mock,
    }


def test_generate_collections_with_openapi_and_zephyr(orchestrator_patches):
    orchestrator, mocks = orchestrator_patches

    result = orchestrator.generate_expert_newman_collections(
        api_specification="openapi: 3.1.0\ninfo: {}",
        test_scenarios=['{"id": 1, "name": "ZE-123"}'],
        business_domain="payments",
        endpoints=[{"name": "create"}],
    )

    assert result["collections"][0]["collection"] == mocks["build"].return_value

    call = mocks["build"].call_args
    assert call is not None
    kwargs = call.kwargs
    assert kwargs["openapi_spec"] == "openapi: 3.1.0\ninfo: {}"
    assert kwargs["zephyr_scenarios"] == '{"id": 1, "name": "ZE-123"}'
    assert mocks["quality"].call_args is not None

    assert result["quality_score"] == 87
    assert result["metadata"]["status"] == "success"
    assert result["metadata"]["quality"]["score"] == 87
    assert result["metadata"]["validation"]["schema"]["valid"] is True
    assert (
        result["metadata"]["supplemental_assets"]["data_driven"]["data_file"]
        == "data/payments.csv"
    )
    assert result["newman_plan"]["cli_command"].startswith("newman run")
    assert result["scripts"]["requests"]["Create payment"]["test"]

    # Regression: ensure the orchestrator output remains JSON serializable
    serialized = json.dumps(result)
    assert isinstance(json.loads(serialized), dict)


def test_generate_collections_returns_structured_error(orchestrator_module, monkeypatch):
    def _boom(**_kwargs):
        raise RuntimeError("boom")

    target_module = importlib.import_module(
        "app.sub_agents.newman_expert.tools.smart_collection_builder"
    )
    monkeypatch.setattr(target_module, "build_smart_newman_collection", _boom)

    result = orchestrator_module.generate_expert_newman_collections(
        api_specification="{}",
        include_monitoring=False,
        include_collaboration_features=False,
    )

    assert result["collections"] == []
    assert result["metadata"]["status"] == "error"
    assert result["metadata"]["error"]["code"] == "collection_generation_failed"
    assert result["metadata"]["error"]["hint"]
    assert result["quality_score"] == 0
