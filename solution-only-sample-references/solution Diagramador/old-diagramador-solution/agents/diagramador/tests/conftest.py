"""
Pytest configuration and shared fixtures for Architect Agent ADK tests.

This module provides:
- Common fixtures for all tests
- Mock objects for testing
- Path configuration
- Test data generators
- Environment setup
"""

import asyncio
import json
import os
import sys
import tempfile
import types
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ========== OPTIONAL DEPENDENCY STUBS ==========

def _ensure_dotenv_stub() -> None:
    """Provide a minimal stub for python-dotenv when not installed."""

    if "dotenv" in sys.modules:
        return

    dotenv_module = types.ModuleType("dotenv")

    def _noop(*_args, **_kwargs):
        return None

    dotenv_module.load_dotenv = _noop  # type: ignore[attr-defined]
    sys.modules["dotenv"] = dotenv_module


def _ensure_google_adk_stubs() -> None:
    """Create lightweight google.* module stubs when SDK is unavailable."""

    if "google" not in sys.modules:
        google_module = types.ModuleType("google")
        sys.modules["google"] = google_module
    else:
        google_module = sys.modules["google"]

    # ---- google.genai.types ----
    genai_module = getattr(google_module, "genai", None)
    if genai_module is None:
        genai_module = types.ModuleType("google.genai")
        setattr(google_module, "genai", genai_module)
        sys.modules["google.genai"] = genai_module

    if "google.genai.types" not in sys.modules:
        types_module = types.ModuleType("google.genai.types")

        class Part:  # type: ignore[override]
            def __init__(self, text: str = ""):
                self.text = text

        class Content:  # type: ignore[override]
            def __init__(self, parts: Optional[List[Part]] = None, role: str = "model"):
                self.parts = parts or []
                self.role = role

            def model_copy(self, update: Optional[Dict[str, Any]] = None):
                data: Dict[str, Any] = {"parts": list(self.parts), "role": self.role}
                if update:
                    data.update(update)
                return Content(**data)

        types_module.Part = Part  # type: ignore[attr-defined]
        types_module.Content = Content  # type: ignore[attr-defined]
        sys.modules["google.genai.types"] = types_module
        setattr(genai_module, "types", types_module)

    # ---- google.adk namespace ----
    if "google.adk" not in sys.modules:
        adk_module = types.ModuleType("google.adk")
        sys.modules["google.adk"] = adk_module
        setattr(google_module, "adk", adk_module)
    else:
        adk_module = sys.modules["google.adk"]

    # google.adk.agents.callback_context.CallbackContext
    if "google.adk.agents" not in sys.modules:
        agents_module = types.ModuleType("google.adk.agents")
        sys.modules["google.adk.agents"] = agents_module
        setattr(adk_module, "agents", agents_module)
    else:
        agents_module = sys.modules["google.adk.agents"]

    if "google.adk.agents.callback_context" not in sys.modules:
        callback_ctx_module = types.ModuleType("google.adk.agents.callback_context")

        class CallbackContext:  # type: ignore[override]
            def __init__(self, content: Any = None, final_content: Any = None, state: Optional[Dict[str, Any]] = None):
                self.content = content
                self.final_content = final_content
                self.state = state or {}

        callback_ctx_module.CallbackContext = CallbackContext  # type: ignore[attr-defined]
        sys.modules["google.adk.agents.callback_context"] = callback_ctx_module
        setattr(agents_module, "callback_context", callback_ctx_module)

    if not hasattr(agents_module, "LlmAgent"):
        class LlmAgent:  # type: ignore[override]
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs
                self.name = kwargs.get("name", "architect_agent")
                self.model = kwargs.get("model", "test-model")
                self.description = kwargs.get("description", "")

            def process(self, message: str) -> Dict[str, Any]:
                return {"echo": message}

            def invoke(self, message: str) -> Dict[str, Any]:
                return {"response": message}

        agents_module.LlmAgent = LlmAgent  # type: ignore[attr-defined]

    if not hasattr(agents_module, "Agent"):
        class Agent:  # type: ignore[override]
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs
                self.name = kwargs.get("name", "agent")

        agents_module.Agent = Agent  # type: ignore[attr-defined]

    # google.adk.models.llm_response.LlmResponse
    if "google.adk.models" not in sys.modules:
        models_module = types.ModuleType("google.adk.models")
        sys.modules["google.adk.models"] = models_module
        setattr(adk_module, "models", models_module)
    else:
        models_module = sys.modules["google.adk.models"]

    if "google.adk.models.llm_response" not in sys.modules:
        llm_module = types.ModuleType("google.adk.models.llm_response")

        class LlmResponse:  # type: ignore[override]
            def __init__(self, content: Any = None):
                self.content = content

            def model_copy(self, update: Optional[Dict[str, Any]] = None):
                data = {"content": self.content}
                if update:
                    data.update(update)
                return LlmResponse(**data)

        llm_module.LlmResponse = LlmResponse  # type: ignore[attr-defined]
        sys.modules["google.adk.models.llm_response"] = llm_module
        setattr(models_module, "llm_response", llm_module)

    # google.adk.events.event.Event
    if "google.adk.events" not in sys.modules:
        events_module = types.ModuleType("google.adk.events")
        sys.modules["google.adk.events"] = events_module
        setattr(adk_module, "events", events_module)
    else:
        events_module = sys.modules["google.adk.events"]

    if "google.adk.events.event" not in sys.modules:
        event_module = types.ModuleType("google.adk.events.event")

        class Event:  # type: ignore[override]
            def __init__(self, **kwargs):
                self.content = kwargs.get("content")

            @classmethod
            def model_validate(cls, data: Dict[str, Any]) -> "Event":
                return cls(**data)

        event_module.Event = Event  # type: ignore[attr-defined]
        sys.modules["google.adk.events.event"] = event_module
        setattr(events_module, "event", event_module)

    # google.adk.artifacts.GcsArtifactService
    if "google.adk.artifacts" not in sys.modules:
        artifacts_module = types.ModuleType("google.adk.artifacts")

        class GcsArtifactService:  # type: ignore[override]
            def __init__(self, bucket_name: str):
                self.bucket_name = bucket_name

        artifacts_module.GcsArtifactService = GcsArtifactService  # type: ignore[attr-defined]
        sys.modules["google.adk.artifacts"] = artifacts_module
        setattr(adk_module, "artifacts", artifacts_module)

    # google.adk.tools.VertexAiSearchTool
    if "google.adk.tools" not in sys.modules:
        tools_module = types.ModuleType("google.adk.tools")

        class VertexAiSearchTool:  # type: ignore[override]
            def __init__(self, search_engine_id: str):
                self.search_engine_id = search_engine_id

        tools_module.VertexAiSearchTool = VertexAiSearchTool  # type: ignore[attr-defined]
        sys.modules["google.adk.tools"] = tools_module
        setattr(adk_module, "tools", tools_module)

    if "google.adk.tools.agent_tool" not in sys.modules:
        agent_tool_module = types.ModuleType("google.adk.tools.agent_tool")

        class AgentTool:  # type: ignore[override]
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        agent_tool_module.AgentTool = AgentTool  # type: ignore[attr-defined]
        sys.modules["google.adk.tools.agent_tool"] = agent_tool_module
        setattr(sys.modules["google.adk.tools"], "agent_tool", agent_tool_module)

    if "google.adk.runners" not in sys.modules:
        runners_module = types.ModuleType("google.adk.runners")

        class Runner:  # type: ignore[override]
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def run(self, *_args, **_kwargs):
                return {"status": "ok"}

        runners_module.Runner = Runner  # type: ignore[attr-defined]
        sys.modules["google.adk.runners"] = runners_module
        setattr(adk_module, "runners", runners_module)

    if "google.adk.sessions" not in sys.modules:
        sessions_module = types.ModuleType("google.adk.sessions")

        class InMemorySessionService:  # type: ignore[override]
            def __init__(self, *args, **kwargs):
                self.sessions: Dict[str, Dict[str, Any]] = {}

            def get(self, session_id: str) -> Dict[str, Any]:
                return self.sessions.setdefault(session_id, {})

        sessions_module.InMemorySessionService = InMemorySessionService  # type: ignore[attr-defined]
        sys.modules["google.adk.sessions"] = sessions_module
        setattr(adk_module, "sessions", sessions_module)


_ensure_dotenv_stub()
_ensure_google_adk_stubs()

# Configure asyncio for tests
pytest_plugins = ('pytest_asyncio',)


# ========== SESSION-LEVEL FIXTURES ==========

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def project_path() -> Path:
    """Get project root path."""
    return project_root


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Get test data directory."""
    data_dir = Path(__file__).parent / "test_data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


# ========== FUNCTION-LEVEL FIXTURES ==========

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_file(temp_dir) -> Generator[Path, None, None]:
    """Create a temporary file for testing."""
    temp_file_path = temp_dir / "test_file.txt"
    temp_file_path.write_text("test content")
    yield temp_file_path


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables for each test."""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def clean_imports():
    """Clean imports to ensure test isolation."""
    modules_to_clean = [
        'app', 'app.tools', 'app.tools.generators',
        'app.tools.validators', 'app.tools.utilities'
    ]
    original_modules = sys.modules.copy()

    yield

    # Restore original modules
    for module in modules_to_clean:
        if module in sys.modules:
            del sys.modules[module]

    for key, value in original_modules.items():
        if key not in sys.modules:
            sys.modules[key] = value


# ========== MOCK FIXTURES ==========

@pytest.fixture
def mock_llm() -> Mock:
    """Create a mock LLM for testing."""
    mock = MagicMock()
    mock.model_name = "test-model"
    mock.temperature = 0.7
    mock.max_tokens = 1000

    # Mock generate_content method
    mock.generate_content = AsyncMock(return_value={
        "candidates": [{
            "content": {
                "parts": [{"text": "Generated C4 diagram content"}]
            },
            "finish_reason": "STOP",
            "safety_ratings": []
        }],
        "prompt_feedback": {"block_reason": None}
    })

    # Mock stream_generate_content method
    async def mock_stream():
        yield {
            "candidates": [{
                "content": {"parts": [{"text": "Streaming "}]}
            }]
        }
        yield {
            "candidates": [{
                "content": {"parts": [{"text": "content"}]}
            }]
        }

    mock.stream_generate_content = AsyncMock(side_effect=mock_stream)

    return mock


@pytest.fixture
def mock_diagram_generator() -> Mock:
    """Create a mock diagram generator."""
    mock = MagicMock()
    mock.generate = AsyncMock(return_value={
        "type": "context",
        "title": "System Context",
        "content": "@startuml\n!include C4_Context.puml\nPerson(user, \"User\")\nSystem(system, \"System\")\nRel(user, system, \"Uses\")\n@enduml",
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "version": "1.0",
            "author": "test"
        }
    })

    mock.generate_from_story = AsyncMock(return_value={
        "diagrams": ["context", "container", "component"],
        "status": "success"
    })

    return mock


@pytest.fixture
def mock_validator() -> Mock:
    """Create a mock validator."""
    mock = MagicMock()

    # Mock validate method
    mock.validate = Mock(return_value={
        "valid": True,
        "errors": [],
        "warnings": [],
        "score": 100
    })

    # Mock validate_schema method
    mock.validate_schema = Mock(return_value={
        "valid": True,
        "errors": [],
        "schema_version": "1.0"
    })

    # Mock validate_c4_compliance method
    mock.validate_c4_compliance = Mock(return_value={
        "compliant": True,
        "violations": [],
        "suggestions": []
    })

    # Mock validate_plantuml method
    mock.validate_plantuml = Mock(return_value={
        "valid": True,
        "syntax_errors": [],
        "line_count": 10
    })

    return mock


@pytest.fixture
def mock_file_handler() -> Mock:
    """Create a mock file handler."""
    mock = MagicMock()

    # Mock file operations
    mock.save_file = Mock(return_value=True)
    mock.load_file = Mock(return_value="file content")
    mock.file_exists = Mock(return_value=True)
    mock.delete_file = Mock(return_value=True)
    mock.list_files = Mock(return_value=["file1.txt", "file2.txt"])
    mock.get_file_size = Mock(return_value=1024)
    mock.get_file_metadata = Mock(return_value={
        "size": 1024,
        "created": datetime.now().isoformat(),
        "modified": datetime.now().isoformat()
    })

    return mock


@pytest.fixture
def mock_session_service() -> Mock:
    """Create a mock session service."""
    mock = MagicMock()

    mock.create_session = AsyncMock(return_value={
        "session_id": "test-session-123",
        "user_id": "test-user",
        "created_at": datetime.now().isoformat()
    })

    mock.get_session = AsyncMock(return_value={
        "session_id": "test-session-123",
        "user_id": "test-user",
        "data": {}
    })

    mock.update_session = AsyncMock(return_value=True)
    mock.delete_session = AsyncMock(return_value=True)

    return mock


# ========== TEST DATA FIXTURES ==========

@pytest.fixture
def sample_user_story() -> Dict[str, Any]:
    """Create a sample user story for testing."""
    return {
        "id": "US001",
        "title": "User Authentication",
        "description": "As a user, I want to authenticate to access the system securely",
        "acceptance_criteria": [
            "User can login with email and password",
            "User receives error message on invalid credentials",
            "Session expires after 30 minutes of inactivity",
            "User can reset password via email"
        ],
        "priority": "high",
        "story_points": 8,
        "sprint": "Sprint 1",
        "assigned_to": "dev_team",
        "tags": ["security", "authentication", "user-management"]
    }


@pytest.fixture
def sample_c4_diagram() -> str:
    """Create a sample C4 diagram in PlantUML format."""
    return """@startuml
!include C4_Context.puml

LAYOUT_WITH_LEGEND()

title System Context diagram for Internet Banking System

Person(customer, "Banking Customer", "A customer of the bank, with personal bank accounts.")
System(banking_system, "Internet Banking System", "Allows customers to check their bank accounts.")
System_Ext(mail_system, "E-mail System", "The internal Microsoft Exchange e-mail system.")
System_Ext(mainframe, "Mainframe Banking System", "Stores all of the core banking information.")

Rel(customer, banking_system, "Uses")
Rel_Back(customer, mail_system, "Sends e-mails to")
Rel_Neighbor(banking_system, mail_system, "Sends e-mails", "SMTP")
Rel(banking_system, mainframe, "Gets account information from, and makes payments using")

@enduml"""


@pytest.fixture
def sample_c4_container_diagram() -> str:
    """Create a sample C4 container diagram."""
    return """@startuml
!include C4_Container.puml

LAYOUT_TOP_DOWN()
LAYOUT_WITH_LEGEND()

title Container diagram for Internet Banking System

Person(customer, "Banking Customer", "A customer of the bank")

System_Boundary(banking, "Internet Banking System") {
    Container(web_app, "Web Application", "Java and Spring MVC", "Delivers the static content")
    Container(single_page_app, "Single-Page Application", "JavaScript and Angular", "Provides banking functionality")
    Container(mobile_app, "Mobile App", "Xamarin", "Provides limited banking functionality")
    Container(api_app, "API Application", "Java and Spring Boot", "Provides banking functionality via JSON/HTTPS API")
    Container(database, "Database", "Oracle Database", "Stores user registration information")
}

System_Ext(mail_system, "E-mail System", "The internal Microsoft Exchange e-mail system")
System_Ext(mainframe, "Mainframe Banking System", "Stores all of the core banking information")

Rel(customer, web_app, "Visits", "HTTPS")
Rel(customer, single_page_app, "Uses", "HTTPS")
Rel(customer, mobile_app, "Uses", "HTTPS")

Rel(web_app, single_page_app, "Delivers to the customer's web browser")
Rel(single_page_app, api_app, "Makes API calls to", "JSON/HTTPS")
Rel(mobile_app, api_app, "Makes API calls to", "JSON/HTTPS")
Rel(api_app, database, "Reads from and writes to", "SQL/TCP")
Rel(api_app, mail_system, "Sends e-mail using", "SMTP")
Rel(api_app, mainframe, "Makes API calls to", "XML/HTTPS")

@enduml"""


@pytest.fixture
def sample_config() -> Dict[str, Any]:
    """Create sample configuration."""
    return {
        "llm": {
            "model": "gemini-pro",
            "temperature": 0.7,
            "max_tokens": 2000,
            "top_p": 0.9,
            "top_k": 40
        },
        "diagrams": {
            "output_format": "plantuml",
            "include_metadata": True,
            "auto_layout": True,
            "themes": ["default", "dark", "sketch"]
        },
        "validation": {
            "strict_mode": True,
            "check_compliance": True,
            "max_errors": 10,
            "validate_on_generate": True
        },
        "output": {
            "directory": "output/diagrams",
            "file_naming": "timestamp",
            "formats": ["png", "svg", "pdf"]
        }
    }


@pytest.fixture
def sample_api_request() -> Dict[str, Any]:
    """Create a sample API request."""
    return {
        "user_id": "user-123",
        "session_id": "session-456",
        "request_id": "req-789",
        "timestamp": datetime.now().isoformat(),
        "payload": {
            "action": "generate_diagram",
            "input": {
                "user_story": "As a user, I want to login",
                "diagram_type": "context",
                "options": {
                    "include_legend": True,
                    "auto_layout": True
                }
            }
        }
    }


@pytest.fixture
def sample_api_response() -> Dict[str, Any]:
    """Create a sample API response."""
    return {
        "request_id": "req-789",
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "data": {
            "diagram": "@startuml\n...\n@enduml",
            "metadata": {
                "type": "context",
                "generated_at": datetime.now().isoformat(),
                "processing_time_ms": 1250
            }
        },
        "errors": [],
        "warnings": []
    }


# ========== HELPER FIXTURES ==========

@pytest.fixture
def create_test_file():
    """Factory fixture to create test files."""
    created_files = []

    def _create_file(path: Path, content: str = "test content") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        created_files.append(path)
        return path

    yield _create_file

    # Cleanup
    for file_path in created_files:
        if file_path.exists():
            file_path.unlink()


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    mock = MagicMock()

    mock.get = AsyncMock(return_value={
        "status": 200,
        "data": {"message": "success"}
    })

    mock.post = AsyncMock(return_value={
        "status": 201,
        "data": {"id": "created-123"}
    })

    mock.put = AsyncMock(return_value={
        "status": 200,
        "data": {"updated": True}
    })

    mock.delete = AsyncMock(return_value={
        "status": 204,
        "data": None
    })

    return mock


@pytest.fixture
def capture_logs():
    """Capture log messages during tests."""
    import logging
    from io import StringIO

    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)

    # Get root logger
    logger = logging.getLogger()
    original_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    yield log_capture

    # Cleanup
    logger.removeHandler(handler)
    logger.setLevel(original_level)


# ========== PYTEST CONFIGURATION ==========

def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
    # Register custom markers
    config.addinivalue_line(
        "markers", "smoke: mark test as a smoke test for quick validation"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "asyncio: mark test as requiring asyncio"
    )
    config.addinivalue_line(
        "markers", "load: mark test as a load/performance test"
    )
    config.addinivalue_line(
        "markers", "skip_ci: mark test to skip in CI environment"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test location."""
    for item in items:
        # Add markers based on file location
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "load_test" in str(item.fspath):
            item.add_marker(pytest.mark.load)

        # Skip certain tests in CI
        if os.environ.get("CI") == "true":
            if item.get_closest_marker("skip_ci"):
                item.add_marker(pytest.mark.skip(reason="Skipped in CI"))


def pytest_sessionstart(session):
    """Called after the Session object has been created."""
    print("\n" + "=" * 60)
    print("Starting Architect Agent ADK Test Suite")
    print(f"Python version: {sys.version}")
    print(f"Pytest version: {pytest.__version__}")
    print(f"Project root: {project_root}")
    print("=" * 60 + "\n")


def pytest_sessionfinish(session, exitstatus):
    """Called after whole test run finished."""
    print("\n" + "=" * 60)
    print("Test Suite Completed")
    print(f"Exit status: {exitstatus}")

    # Print summary based on exit status
    if exitstatus == 0:
        print("✅ All tests passed!")
    elif exitstatus == 1:
        print("❌ Some tests failed")
    elif exitstatus == 2:
        print("⚠️ Test execution was interrupted")
    elif exitstatus == 3:
        print("⚠️ Internal error occurred")
    elif exitstatus == 4:
        print("⚠️ Pytest usage error")
    elif exitstatus == 5:
        print("⚠️ No tests were collected")

    print("=" * 60 + "\n")


# ========== ASYNC SUPPORT ==========

@pytest.fixture
def async_timeout():
    """Provide timeout for async tests."""
    return 30  # seconds


@pytest.fixture
async def async_client():
    """Create an async client for testing."""
    class AsyncClient:
        async def request(self, method: str, url: str, **kwargs):
            await asyncio.sleep(0.1)  # Simulate network delay
            return {"status": 200, "data": "test"}

    return AsyncClient()


# ========== TEST DATA GENERATORS ==========

@pytest.fixture
def generate_user_stories():
    """Generate multiple user stories for testing."""
    def _generate(count: int = 5) -> List[Dict[str, Any]]:
        stories = []
        for i in range(count):
            stories.append({
                "id": f"US{i:03d}",
                "title": f"User Story {i}",
                "description": f"As a user, I want feature {i}",
                "acceptance_criteria": [f"Criteria {j}" for j in range(3)],
                "priority": ["low", "medium", "high"][i % 3]
            })
        return stories
    return _generate


@pytest.fixture
def generate_diagrams():
    """Generate multiple diagram samples."""
    def _generate(count: int = 3) -> List[str]:
        diagrams = []
        for i in range(count):
            diagrams.append(f"@startuml\ntitle Diagram {i}\n@enduml")
        return diagrams
    return _generate

