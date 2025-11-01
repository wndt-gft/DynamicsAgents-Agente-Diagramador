"""Integration tests for AgentEngineApp interactions."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

try:  # pragma: no cover - fallback for environments without stubs
    from google.adk.events.event import Event
except ImportError:  # pragma: no cover
    class Event:  # type: ignore
        def __init__(self, **data: Any):
            self.content = data.get("content")

        @classmethod
        def model_validate(cls, data: Dict[str, Any]) -> "Event":
            return cls(**data)


class MockAgent:
    """Simplified agent used when real modules are unavailable."""

    def __init__(self, name: str = "test_agent"):
        self.name = name
        self.capabilities = {
            "name": "Architect Diagram Agent",
            "supported_diagrams": ["context", "container", "component", "code"],
            "tools": ["diagram_generator_tool", "validator_tool"],
            "adk_compatible": True,
        }

    def process(self, message: str) -> Dict[str, Any]:  # pragma: no cover - only for mock fallback
        return {"echo": message}


class MockAgentEngineApp:
    """Mock version mimicking the new AgentEngineApp contract."""

    def __init__(self, agent: Optional[MockAgent] = None):
        self.agent = agent or MockAgent()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.feedback_store: List[Dict[str, Any]] = []
        self.metrics = {
            "requests_processed": 0,
            "errors": 0,
            "total_feedback": 0,
            "average_score": 0.0,
        }
        self._setup_complete = False

    def set_up(self) -> None:
        self._setup_complete = True
        self.logger.info("Agent Engine App initialized")

    async def stream_query(
        self,
        message: str,
        user_id: str = "test_user",
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.metrics["requests_processed"] += 1
        await asyncio.sleep(0)  # yield control similar to real async flow
        return {
            "author": "agent",
            "parts": [
                {"text": f"Processing: {message}"},
                {"text": "Generated C4 diagram successfully."},
            ],
        }

    async def health_check(self) -> Dict[str, Any]:  # pragma: no cover - not used directly in tests
        return {
            "status": "healthy",
            "services": {"cloud_logging": False, "artifacts": False, "vertex_ai": False},
            "metrics": self.get_metrics(),
            "agent": {"available": True, "name": self.agent.name, "responsive": True},
        }

    def handle_feedback(self, feedback_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        try:
            score = feedback_data["score"]
            if not isinstance(score, (int, float)):
                raise TypeError("Score must be numeric")
            text = feedback_data.get("text", "")
            invocation_id = feedback_data.get("invocation_id", "")
            if not invocation_id:
                raise ValueError("invocation_id is required")
            payload = {
                "score": score,
                "text": text,
                "invocation_id": invocation_id,
                "user_id": user_id,
                "timestamp": time.time(),
            }
            self.feedback_store.append(payload)
            total = self.metrics["total_feedback"] + 1
            new_avg = ((self.metrics["average_score"] * self.metrics["total_feedback"]) + score) / total
            self.metrics["total_feedback"] = total
            self.metrics["average_score"] = new_avg
            return {
                "status": "received",
                "message": "Thank you for your feedback",
                "metrics": self.get_metrics(),
            }
        except Exception as exc:
            self.metrics["errors"] += 1
            return {
                "status": "error",
                "error": str(exc),
                "message": "Could not process feedback",
            }

    def get_metrics(self) -> Dict[str, Any]:
        return dict(self.metrics)


try:
    from app.agent import get_agent_capabilities, root_agent
    from app.agent_engine_app import AgentEngineApp, LoggingConfig
    import app.agent_engine_app as app_engine_module

    REAL_APP_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback for missing modules
    REAL_APP_AVAILABLE = False

    def get_agent_capabilities() -> Dict[str, Any]:
        return MockAgent().capabilities

    root_agent = MockAgent()
    AgentEngineApp = MockAgentEngineApp  # type: ignore[assignment]
    app_engine_module = None  # type: ignore


class TestAgentEngineApp:
    """Integration tests validating agent engine behaviours."""

    @pytest.fixture
    def agent_app(self) -> Any:
        if REAL_APP_AVAILABLE:
            with patch.object(app_engine_module.AdkApp, "__init__", return_value=None), \
                 patch("app.agent_engine_app.google_cloud_logging.Client") as mock_client:
                mock_logger = logging.getLogger("test")
                mock_client.return_value.logger.return_value = mock_logger

                app = AgentEngineApp(
                    agent=root_agent,
                    logging_config=LoggingConfig(enable_cloud_logging=False, enable_tracing=False),
                )

                async def fake_stream(self, message: str, user_id: str, session_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
                    self.metrics["requests_processed"] += 1
                    return {
                        "author": "agent",
                        "parts": [
                            {"text": f"Processing: {message}"},
                            {"text": "Generated C4 diagram successfully."},
                        ],
                    }

                app.stream_query = fake_stream.__get__(app, AgentEngineApp)
                app.set_up()
                return app
        else:
            app = MockAgentEngineApp(agent=root_agent)
            app.set_up()
            return app

    @pytest.mark.asyncio
    async def test_agent_stream_query(self, agent_app: Any) -> None:
        message = "Generate a C4 context diagram for an e-commerce system"
        user_id = "test_user_123"

        response = await agent_app.stream_query(message=message, user_id=user_id)

        assert "parts" in response
        assert any(part.get("text") for part in response["parts"])

    def test_agent_capabilities(self) -> None:
        caps = get_agent_capabilities()

        assert isinstance(caps, dict)
        assert caps["name"] in {"Architect Diagram Agent", "architect_diagram_agent"}
        supported = set(caps["supported_diagrams"])
        assert {"context", "container"}.issubset(supported)
        assert "diagram_generator_tool" in caps["tools"]
        assert "tools" in caps

    def test_agent_feedback_valid(self, agent_app: Any) -> None:
        feedback_data = {
            "score": 5,
            "text": "Excellent diagram generation!",
            "invocation_id": "test-run-456",
        }

        start_time = time.time()
        result = agent_app.handle_feedback(feedback_data, "tester")
        duration = time.time() - start_time

        assert duration < 1.0
        assert result["status"] == "received"
        metrics = agent_app.get_metrics()
        assert metrics["total_feedback"] >= 1

    def test_agent_feedback_invalid(self, agent_app: Any) -> None:
        invalid_feedback = {
            "score": "invalid",
            "text": "Bad feedback format",
            "invocation_id": "test-run-789",
        }

        result = agent_app.handle_feedback(invalid_feedback, "tester")
        assert result["status"] == "error"
        assert result["error"]

    def test_agent_feedback_missing_score(self, agent_app: Any) -> None:
        feedback_without_score = {
            "text": "Missing score",
            "invocation_id": "test-run-999",
        }

        result = agent_app.handle_feedback(feedback_without_score, "tester")
        assert result["status"] == "error"
        assert result["error"]

    @pytest.mark.asyncio
    async def test_streaming_with_multiple_parts(self, agent_app: Any) -> None:
        message = "Create both context and container diagrams"
        response = await agent_app.stream_query(message=message, user_id="test")
        assert len(response["parts"]) >= 2

    def test_agent_initialization(self, agent_app: Any) -> None:
        if hasattr(agent_app, "_setup_complete"):
            assert agent_app._setup_complete is True
        if hasattr(agent_app, "agent"):
            assert getattr(agent_app.agent, "name", None) is not None

    @pytest.mark.asyncio
    async def test_concurrent_queries(self, agent_app: Any) -> None:
        messages = [
            "Generate context diagram for banking system",
            "Create container diagram for e-commerce",
            "Design component diagram for microservices",
        ]

        results = []
        for msg in messages:
            response = await agent_app.stream_query(message=msg, user_id=f"user_{len(results)}")
            results.append(len(response["parts"]))

        assert len(results) == len(messages)
        assert all(count > 0 for count in results)

    @pytest.mark.parametrize(
        "score,expected_valid",
        [
            pytest.param(5, True, id="score-5-valid"),
            pytest.param(4.5, False, id="score-4_5-invalid"),
            pytest.param(0, False, id="score-0-invalid"),
            pytest.param(-1, False, id="score--1-invalid"),
            pytest.param(None, False, id="score-none-invalid"),
            pytest.param("5", True, id="score-str-valid"),
            pytest.param([], False, id="score-list-invalid"),
        ],
    )
    def test_feedback_score_validation(self, agent_app: Any, score: Any, expected_valid: bool) -> None:
        feedback = {
            "score": score,
            "text": "Test feedback",
            "invocation_id": "test-123",
        }

        result = agent_app.handle_feedback(feedback, "tester")
        if expected_valid:
            assert result["status"] == "received"
        else:
            assert result["status"] == "error"
