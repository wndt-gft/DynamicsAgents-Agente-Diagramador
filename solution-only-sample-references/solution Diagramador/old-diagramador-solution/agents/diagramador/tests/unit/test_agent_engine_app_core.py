"""Unit tests for AgentEngineApp core behaviors in testing mode."""
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
for p in (PROJECT_ROOT, APP_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import app.agent_engine_app as app_module
from app.agent_engine_app import AgentEngineApp, LoggingConfig


@pytest.fixture(autouse=True)
def set_testing_env(monkeypatch):
    monkeypatch.setenv("TESTING", "true")
    yield


@pytest.fixture(autouse=True)
def patch_adkapp_init(monkeypatch):
    def dummy_init(self, *args, **kwargs):
        self._adk_init_args = args
        self._adk_init_kwargs = kwargs

    monkeypatch.setattr(app_module.AdkApp, "__init__", dummy_init, raising=False)
    yield


class DummyAgent:
    name = "dummy"
    version = "1.0"

    def process(self, message: str):
        return {"echo": message}

    async def stream_async(self, message: str):
        return {"author": "agent", "content": message}

    def process_feedback(self, payload):  # pragma: no cover - simple passthrough
        return {"status": "received", "payload": payload}


def _make_app() -> AgentEngineApp:
    return AgentEngineApp(
        agent=DummyAgent(),
        logging_config=LoggingConfig(enable_cloud_logging=False, enable_tracing=False)
    )


@pytest.mark.asyncio
async def test_health_check_contains_status():
    app = _make_app()
    hc = await app.health_check()
    assert hc["status"] == "healthy"
    assert "services" in hc
    assert hc["agent"]["responsive"] is True


def test_handle_feedback_success_updates_metrics():
    app = _make_app()
    feedback = {
        "score": 5,
        "text": "ótimo",
        "invocation_id": "abc",
        "user_id": "tester"
    }
    result = app.handle_feedback(feedback, "tester")
    assert result["status"] == "received"
    metrics = app.get_metrics()
    assert metrics["total_feedback"] == 1
    assert pytest.approx(metrics["average_score"], rel=1e-6) == 5.0


def test_handle_feedback_missing_score_returns_error():
    app = _make_app()
    response = app.handle_feedback({
        "text": "sem score",
        "invocation_id": "123"
    }, "tester")
    assert response["status"] == "error"
    assert response["error"]


def test_handle_feedback_invalid_score_type_returns_error():
    app = _make_app()
    response = app.handle_feedback({
        "score": "bad",
        "text": "valor inválido",
        "invocation_id": "abc"
    }, "tester")
    assert response["status"] == "error"
    assert response["error"]


@pytest.mark.asyncio
async def test_stream_query_updates_metrics_and_returns_agent_result():
    app = _make_app()
    reply = await app.stream_query("Test message", user_id="tester")
    assert reply["author"] == "agent"
    assert reply["content"] == "Test message"
    assert app.get_metrics()["requests_processed"] == 1


def test_get_metrics_returns_copy():
    app = _make_app()
    metrics = app.get_metrics()
    metrics["requests_processed"] = 999
    assert app.metrics["requests_processed"] == 0

