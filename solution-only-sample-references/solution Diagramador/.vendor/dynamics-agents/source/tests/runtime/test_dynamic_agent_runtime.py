import logging
import sys
import types
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict

import asyncio

import pytest

THIS_FILE = Path(__file__).resolve()
ROOT = next(parent for parent in THIS_FILE.parents if (parent / "pyproject.toml").exists())
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from dynamic_agents import runtime as runtime_module

from dynamic_agents import (
    DynamicAgentRuntime,
    EventRecorder,
    RuntimeCallbackError,
    RuntimeToolError,
    SolutionRuntime,
    ToolSpec,
    SESSION_REGISTRY_KEY,
    dump_yaml,
    invoke_tool,
    normalize_callbacks,
    resolve_placeholders,
    resolve_with_root,
)


class _GoogleModulesStub:
    def _fixture_function(self):
        def _generator():
            import types
            import sys

            def _module(name: str) -> types.ModuleType:
                module = types.ModuleType(name.rsplit(".", 1)[-1])
                module.__package__ = name
                module.__path__ = []  # type: ignore[attr-defined]
                return module

            module_google = _module("google")
            module_adk = _module("google.adk")
            module_google.adk = module_adk  # type: ignore[attr-defined]
            module_apps = _module("google.adk.apps")
            module_agents = _module("google.adk.agents")
            module_tools = _module("google.adk.tools")
            module_planners = _module("google.adk.planners")

            class App:  # pragma: no cover - simple container
                def __init__(self, name: str, root_agent):
                    self.name = name
                    self.root_agent = root_agent

            class LlmAgent:  # pragma: no cover - minimal stub
                def __init__(self, **kwargs):
                    self.name = kwargs.get("name")
                    self.description = kwargs.get("description")
                    self.instruction = kwargs.get("instruction")
                    self.tools = list(kwargs.get("tools", []))
                    self.sub_agents = list(kwargs.get("sub_agents", []))
                    self.parent_agent = kwargs.get("parent_agent")

            class BaseTool:  # pragma: no cover - metadata container
                def __init__(self, *, name: str, description: str | None = None, custom_metadata=None):
                    self.name = name
                    self.description = description
                    self.custom_metadata = custom_metadata or {}

            class AgentTool(BaseTool):  # pragma: no cover
                def __init__(self, agent, skip_summarization: bool = False):
                    super().__init__(name=agent.name if agent else "agent", description=getattr(agent, "description", None))
                    self.agent = agent
                    self.skip_summarization = skip_summarization

            class ToolContext:  # pragma: no cover
                def __init__(self, *args, **kwargs):
                    self.args = args
                    self.kwargs = kwargs

            class BuiltInPlanner:  # pragma: no cover
                def __init__(self, *args, **kwargs):
                    self.args = args
                    self.kwargs = kwargs

            module_app = _module("google.adk.apps.app")
            module_app.App = App  # type: ignore[attr-defined]
            module_apps.app = module_app  # type: ignore[attr-defined]

            module_llm_agent = _module("google.adk.agents.llm_agent")
            module_llm_agent.LlmAgent = LlmAgent  # type: ignore[attr-defined]
            module_agents.llm_agent = module_llm_agent  # type: ignore[attr-defined]

            module_agent_tool = _module("google.adk.tools.agent_tool")
            module_agent_tool.AgentTool = AgentTool  # type: ignore[attr-defined]
            module_tools.agent_tool = module_agent_tool  # type: ignore[attr-defined]

            module_base_tool = _module("google.adk.tools.base_tool")
            module_base_tool.BaseTool = BaseTool  # type: ignore[attr-defined]
            module_tools.base_tool = module_base_tool  # type: ignore[attr-defined]

            module_tool_context = _module("google.adk.tools.tool_context")
            module_tool_context.ToolContext = ToolContext  # type: ignore[attr-defined]
            module_tools.tool_context = module_tool_context  # type: ignore[attr-defined]

            module_planners.builtins = {}  # type: ignore[attr-defined]
            module_planners.BuiltInPlanner = BuiltInPlanner  # type: ignore[attr-defined]

            created_modules = {
                "google": module_google,
                "google.adk": module_adk,
                "google.adk.apps": module_apps,
                "google.adk.apps.app": module_app,
                "google.adk.agents": module_agents,
                "google.adk.agents.llm_agent": module_llm_agent,
                "google.adk.tools": module_tools,
                "google.adk.tools.agent_tool": module_agent_tool,
                "google.adk.tools.base_tool": module_base_tool,
                "google.adk.tools.tool_context": module_tool_context,
                "google.adk.planners": module_planners,
            }

            preserved = {name: sys.modules.get(name) for name in created_modules}
            sys.modules.update(created_modules)

            yield

            for name in created_modules:
                if preserved[name] is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = preserved[name]

        return _generator()


google_modules_stub = _GoogleModulesStub()


@pytest.fixture
def google_modules():
    generator = google_modules_stub._fixture_function()
    next(generator)
    try:
        yield
    finally:
        with suppress(StopIteration):
            next(generator)


def _write_yaml(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_yaml(path, payload)


def _write_module(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _basic_solution(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    (root / "app").mkdir(parents=True)
    dump_yaml(
        root / "workflow.yaml",
        {
            "version": 1,
            "metadata": {"entrypoint_agent": "orchestrator", "parent": True},
            "catalog": {"agents": []},
        },
    )
    solution = root / "app" / "travel"
    (solution / "tools" / "interactions" / "echo" ).mkdir(parents=True)
    dump_yaml(
        solution / "tools" / "interactions" / "echo" / "metadata.yaml",
        {"metadata": {"label": "Ferramenta de Eco"}},
    )
    _write_module(
        solution / "tools" / "interactions" / "echo" / "tool.py",
        '''
class Tool:
    """Echo tool used in tests."""

    def run(self, message: str, state=None):
        """Return message and register in state."""
        state = state or {}
        history = state.setdefault("messages", [])
        history.append(message)
        return {"message": message}
''',
    )
    (solution / "tools" / "interactions" / "ack" ).mkdir(parents=True)
    dump_yaml(
        solution / "tools" / "interactions" / "ack" / "metadata.yaml",
        {"metadata": {"label": "Ferramenta de Confirmação"}},
    )
    _write_module(
        solution / "tools" / "interactions" / "ack" / "tool.py",
        '''
class Tool:
    """Acknowledgement tool used by concierge agents."""

    def run(self, label: str, state=None):
        state = state or {}
        state.setdefault("acknowledgements", []).append(label)
        return {"ack": label}
''',
    )
    (solution / "tools" / "callbacks" / "after_tool" / "logger" ).mkdir(parents=True)
    dump_yaml(
        solution / "tools" / "callbacks" / "after_tool" / "logger" / "metadata.yaml",
        {"metadata": {"label": "Callback de Registro"}},
    )
    _write_module(
        solution / "tools" / "callbacks" / "after_tool" / "logger" / "callback.py",
        '''
class Callback:
    def handle_event(self, event, payload, state):
        state.setdefault("callback_events", []).append((event, payload))
''',
    )
    dump_yaml(
        solution / "workflow.yaml",
        {
            "version": 1,
            "metadata": {"name": "Travel", "description": "Test workflow"},
            "catalog": {
                "agents": [
                    {
                        "orchestrator": {
                            "label": "Orquestrador",
                            "description": "Main agent",
                            "workflow": {
                                "steps": [
                                    {
                                        "step_name": "greet",
                                        "label": "Saudar Usuário",
                                        "instructions": "Use the echo tool",
                                        "tools": [
                                            {
                                                "name": "echo",
                                                "label": "Ferramenta de Eco",
                                                "method": "run",
                                                "input": {"message": "{{ state.user_query }}"},
                                            }
                                        ],
                                        "callbacks": [
                                            {"after_tool_execution": ["logger"]},
                                        ],
                                    },
                                    {
                                        "step_name": "delegate",
                                        "label": "Delegar Validação",
                                        "instructions": "Acione o agente auxiliar para validar o retorno.",
                                        "agents": [
                                            {
                                                "type": "agent_tool",
                                                "agent": "concierge",
                                                "label": "Agente Concierge",
                                                "when_to_use": "Use para confirmar se o atendimento está completo.",
                                            }
                                        ],
                                    },
                                ]
                            },
                        }
                    },
                    {
                        "concierge": {
                            "label": "Concierge",
                            "description": "Auxiliary agent used to validate orchestration.",
                            "workflow": {
                                "steps": [
                                    {
                                        "step_name": "noop",
                                        "label": "Registrar Confirmação",
                                        "instructions": "Registre no estado que o concierge foi acionado.",
                                        "tools": [
                                            {
                                                "name": "ack",
                                                "label": "Ferramenta de Confirmação",
                                                "method": "run",
                                                "input": {"label": "concierge"},
                                            }
                                        ],
                                    }
                                ]
                            },
                        }
                    },
                ]
            },
        },
    )
    return root


def test_agent_workflows_are_loaded_from_filesystem(tmp_path: Path) -> None:
    root = tmp_path / "fs_agents"
    dump_yaml(
        root / "workflow.yaml",
        {"version": 1, "metadata": {"entrypoint_agent": "orchestrator"}, "catalog": {"agents": []}},
    )
    solution = root / "travel"
    dump_yaml(
        solution / "workflow.yaml",
        {
            "version": 1,
            "metadata": {"entrypoint_agent": "orchestrator"},
            "catalog": {"agents": [{"orchestrator": {"description": "Inline"}}]},
        },
    )
    orchestrator_agent = solution / "agents" / "orchestrator"
    orchestrator_agent.mkdir(parents=True)
    dump_yaml(
        orchestrator_agent / "workflow.yaml",
        {
            "description": "Filesystem orchestrator",
            "workflow": {
                "steps": [
                    {
                        "step_name": "greet",
                        "label": "Saudar Usuário",
                        "instructions": "Cumprimente o usuário e registre no estado.",
                    }
                ]
            },
        },
    )
    helper_agent = solution / "agents" / "helper"
    helper_agent.mkdir(parents=True)
    dump_yaml(
        helper_agent / "workflow.yaml",
        {
            "description": "Helper discovered on disk",
            "workflow": {"steps": []},
        },
    )

    runtime = DynamicAgentRuntime(root)
    descriptor = runtime.get_solution("travel")

    assert set(descriptor.agents) == {"orchestrator", "helper"}
    orchestrator_spec = descriptor.agents["orchestrator"]
    assert orchestrator_spec.description == "Filesystem orchestrator"
    assert orchestrator_spec.steps and orchestrator_spec.steps[0].name == "greet"
    helper_spec = descriptor.agents["helper"]
    assert helper_spec.description == "Helper discovered on disk"
    catalog_agents = descriptor.workflow["catalog"]["agents"]
    assert any("helper" in entry for entry in catalog_agents)


def test_workflow_inheritance_and_metadata_enrichment(tmp_path: Path) -> None:
    root = _basic_solution(tmp_path)
    runtime = DynamicAgentRuntime(root)
    solution = runtime.get_solution("travel")
    assert solution.entrypoint_agent == "orchestrator"
    assert "echo" in solution.tools
    # metadata is enriched with discovered code artifacts
    discovered = solution.workflow["metadata"]["discovered"]
    assert any(path.endswith("tool.py") for path in discovered["tools"])
    assert "agents" in discovered

    recorder = EventRecorder()
    runtime.event_bus.register(recorder)
    payload = {"user_query": "hello"}
    state = runtime.run("travel", payload=payload)
    assert state["echo:run"] == {"message": "hello"}
    assert state["ack:run"] == {"ack": "concierge"}
    assert any(
        name == "after_tool_execution"
        and event.get("tool") == "echo"
        and event.get("method") == "run"
        and event.get("agent") == "orchestrator"
        and event.get("result") == {"message": "hello"}
        for name, event in state["callback_events"]
    )
    event_names = [event.name for event in recorder.events]
    assert "agent.start" in event_names
    assert "agent.after" in event_names
    assert "tool.after" in event_names


def test_agent_hierarchy_executes_sub_agents(tmp_path: Path) -> None:
    root = tmp_path / "hierarchy"
    orchestrator = root / "solution"
    (orchestrator / "tools" / "interactions" / "mark" ).mkdir(parents=True)
    dump_yaml(
        orchestrator / "tools" / "interactions" / "mark" / "metadata.yaml",
        {"metadata": {"label": "Ferramenta de Marca"}},
    )
    _write_module(
        orchestrator / "tools" / "interactions" / "mark" / "tool.py",
        """
class Tool:
    def run(self, flag: str, state=None):
        state = state or {}
        state.setdefault("flags", []).append(flag)
        return {"flag": flag}
""",
    )
    dump_yaml(
        root / "workflow.yaml",
        {"version": 1, "metadata": {"entrypoint_agent": "main"}, "catalog": {"agents": []}},
    )
    dump_yaml(
        orchestrator / "workflow.yaml",
        {
            "version": 1,
            "catalog": {
                "agents": [
                    {
                        "main": {
                            "label": "Agente Principal",
                            "workflow": {
                                "steps": [
                                    {
                                        "step_name": "mark-main",
                                        "label": "Marcar Principal",
                                        "tools": [
                                            {
                                                "name": "mark",
                                                "label": "Marca Main",
                                                "method": "run",
                                                "input": {"flag": "main"},
                                            }
                                        ],
                                    },
                                    {
                                        "step_name": "delegate",
                                        "label": "Delegar para Worker",
                                        "agents": [
                                            {"name": "worker", "label": "Agente Worker"}
                                        ],
                                    },
                                ]
                            }
                        }
                    },
                    {
                        "worker": {
                            "label": "Agente Worker",
                            "workflow": {
                                "steps": [
                                    {
                                        "step_name": "mark-worker",
                                        "label": "Marcar Worker",
                                        "tools": [
                                            {
                                                "name": "mark",
                                                "label": "Marca Worker",
                                                "method": "run",
                                                "input": {"flag": "worker"},
                                            }
                                        ],
                                    }
                                ]
                            }
                        }
                    },
                ]
            },
        },
    )
    runtime = DynamicAgentRuntime(root)
    recorder = EventRecorder()
    runtime.event_bus.register(recorder)
    state = runtime.run("solution", payload={})
    assert state["mark:run"] == {"flag": "worker"}
    steps = [event.payload.get("step") for event in recorder.events if event.name == "step.start"]
    assert steps == ["mark-main", "delegate", "mark-worker"]


def test_agent_step_type_promotes_agent_tool(tmp_path: Path) -> None:
    root = tmp_path / "agent_types"
    dump_yaml(root / "workflow.yaml", {"version": 1, "metadata": {"entrypoint_agent": "main"}, "catalog": {"agents": []}})
    solution = root / "demo"
    dump_yaml(
        solution / "workflow.yaml",
        {
            "version": 1,
            "catalog": {
                "agents": [
                    {
                        "main": {
                            "label": "Agente Principal",
                            "workflow": {
                                "steps": [
                                    {
                                        "step_name": "delegate",
                                        "label": "Delegar para Helper",
                                        "agents": [
                                            {
                                                "name": "helper",
                                                "type": "agent_tool",
                                                "label": "Agente Helper",
                                                "input": {"payload": "value"},
                                            }
                                        ],
                                    }
                                ]
                            }
                        }
                    },
                    {
                        "helper": {"label": "Agente Helper", "workflow": {"steps": []}},
                    },
                ]
            },
        },
    )

    runtime = DynamicAgentRuntime(root)
    solution_descriptor = runtime.get_solution("demo")
    delegate_step = next(step for step in solution_descriptor.agents["main"].steps if step.name == "delegate")
    assert delegate_step.agents == []
    assert any(entry.get("agent") == "helper" for entry in delegate_step.agent_tools)
    promoted = next(entry for entry in delegate_step.agent_tools if entry.get("agent") == "helper")
    assert promoted.get("type") == "agent_tool"
    assert promoted.get("input") == {"payload": "value"}


def test_callback_errors_raise_runtime_callback_error(tmp_path: Path) -> None:
    root = _basic_solution(tmp_path)
    solution_dir = root / "app" / "travel"
    callback_module = solution_dir / "tools" / "callbacks" / "after_tool" / "logger" / "callback.py"
    _write_module(
        callback_module,
        """
class Callback:
    def handle_event(self, event, payload, state):
        raise ValueError('boom')
""",
    )
    runtime = DynamicAgentRuntime(root)
    with pytest.raises(RuntimeCallbackError):
        runtime.run("travel", payload={"user_query": "oops"})


def test_tool_errors_emit_events(tmp_path: Path) -> None:
    root = _basic_solution(tmp_path)
    solution_dir = root / "app" / "travel"
    tool_module = solution_dir / "tools" / "interactions" / "echo" / "tool.py"
    _write_module(
        tool_module,
        """
class Tool:
    def run(self, message: str, state=None):
        raise RuntimeError('fail')
""",
    )
    runtime = DynamicAgentRuntime(root)
    with pytest.raises(RuntimeToolError):
        runtime.run("travel", payload={"user_query": "hello"})


def test_placeholder_resolution_handles_nested_state() -> None:
    state = {"alpha": {"beta": "value"}}
    payload = {"message": "{{ state.alpha.beta }}"}
    resolved = resolve_placeholders(payload, state)
    assert resolved == {"message": "value"}


def test_placeholder_resolution_supports_shallow_state_keys() -> None:
    state = {"origin": "CWB"}
    payload = {"origin": "{{ origin }}"}
    assert resolve_placeholders(payload, state) == {"origin": "CWB"}


def test_normalize_callbacks_supports_multiple_formats() -> None:
    raw = [
        {"after": ["one", "two"]},
        {"before": "single"},
    ]
    mapping = normalize_callbacks(raw)
    assert mapping == {"after": ["one", "two"], "before": ["single"]}


def test_solution_runtime_reuses_existing_state(tmp_path: Path) -> None:
    root = _basic_solution(tmp_path)
    runtime = DynamicAgentRuntime(root)
    solution = runtime.get_solution("travel")
    state = {"sessions": {"abc": {"user_query": "hi"}}}
    runner = SolutionRuntime(solution, {"state": state, "session_id": "abc"}, runtime.event_bus)
    result = runner.run()
    assert result is state["sessions"]["abc"]


def test_solution_runtime_attaches_logging_plugin(tmp_path: Path) -> None:
    root = _basic_solution(tmp_path)
    runtime = DynamicAgentRuntime(root)
    solution = runtime.get_solution("travel")

    logger = logging.getLogger("dynamic_agent")
    captured: list[str] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - trivial
            captured.append(self.format(record))

    handler = _Collector()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    try:
        runner = SolutionRuntime(solution, {"user_query": "hello"})
        runner.run()
    finally:
        logger.removeHandler(handler)

    joined = "\n".join(captured)
    assert "agent.before" in joined
    assert "agent.after" in joined


def test_resolve_with_root_handles_workspace_absolute(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".env").write_text("", encoding="utf-8")
    solution_root = workspace / "agents" / "travel"
    solution_root.mkdir(parents=True)

    resolved = resolve_with_root(solution_root, "/plugins")

    assert resolved == workspace / "plugins"


def test_env_plugins_resolve_from_workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _basic_solution(tmp_path)
    (root / ".env").write_text("", encoding="utf-8")
    plugins_dir = root / "plugins"
    _write_module(
        plugins_dir / "collector.py",
        """
from dynamic_agents.runtime import RuntimePlugin


class _WorkspacePlugin(RuntimePlugin):
    PLUGIN_NAME = "workspace-marker"

    def handle_event(self, event):
        return None


PLUGIN = _WorkspacePlugin()
""",
    )

    monkeypatch.setenv(runtime_module.PLUGIN_ENV, "/plugins")
    runtime = DynamicAgentRuntime(root)

    assert any(getattr(plugin, "PLUGIN_NAME", "") == "workspace-marker" for plugin in runtime.event_bus._plugins)

    monkeypatch.delenv(runtime_module.PLUGIN_ENV, raising=False)


def test_invoke_tool_requires_named_arguments() -> None:
    class Sample:
        def run(self, foo: str, bar: str, state=None):  # pragma: no cover - simple helper
            return {"foo": foo, "bar": bar}

    with pytest.raises(RuntimeToolError) as exc:
        invoke_tool(Sample(), "run", {"foo": "alpha"}, {})

    assert "Parâmetros obrigatórios ausentes" in str(exc.value)


def test_invoke_tool_supports_async_methods_without_running_loop() -> None:
    class Sample:
        async def run(self, foo: str, state=None):  # pragma: no cover - simple helper
            await asyncio.sleep(0)
            return {"foo": foo}

    result = invoke_tool(Sample(), "run", {"foo": "beta"}, {})

    assert result == {"foo": "beta"}


@pytest.mark.asyncio
def test_invoke_tool_supports_async_methods_with_running_loop() -> None:
    class Sample:
        async def run(self, foo: str, state=None):  # pragma: no cover - simple helper
            await asyncio.sleep(0)
            return {"foo": foo}

    async def _runner() -> None:
        task = invoke_tool(Sample(), "run", {"foo": "gamma"}, {})

        assert isinstance(task, asyncio.Task)
        assert await task == {"foo": "gamma"}

    asyncio.run(_runner())


def test_invoke_callback_supports_async_handler_without_running_loop() -> None:
    class Sample:
        def __init__(self) -> None:
            self.calls: list[Dict[str, Any]] = []

        async def event_name(self, payload: Dict[str, Any], state: Dict[str, Any]) -> str:  # pragma: no cover - simple helper
            await asyncio.sleep(0)
            self.calls.append({"payload": payload, "state": dict(state)})
            state["handled"] = True
            return "ok"

    state: Dict[str, Any] = {}
    sample = Sample()

    result = runtime_module.invoke_callback(sample, "event_name", {"value": 1}, state)

    assert result == "ok"
    assert state["handled"] is True
    assert sample.calls


@pytest.mark.asyncio
def test_invoke_callback_supports_async_handler_with_running_loop() -> None:
    class Sample:
        async def event_name(self, payload: Dict[str, Any], state: Dict[str, Any]) -> str:  # pragma: no cover - simple helper
            await asyncio.sleep(0)
            state["handled"] = payload["value"]
            return "ok"

    state: Dict[str, Any] = {}
    sample = Sample()

    async def _runner() -> None:
        task = runtime_module.invoke_callback(sample, "event_name", {"value": 2}, state)

        assert isinstance(task, asyncio.Task)
        assert await task == "ok"
        assert state["handled"] == 2

    asyncio.run(_runner())


def test_tool_spec_infers_metadata_from_docstrings(tmp_path: Path) -> None:
    root = _basic_solution(tmp_path)
    solution = DynamicAgentRuntime(root).get_solution("travel")
    spec: ToolSpec = solution.tools["echo"]
    instance = spec.ensure_instance()
    assert spec.metadata["metadata"]["name"] == "Tool"
    descriptions = []
    input_schemas = []
    for entry in spec.metadata["methods"]:  # type: ignore[index]
        if isinstance(entry, dict):
            for payload in entry.values():
                descriptions.append(payload.get("description"))
                if payload.get("input_schema"):
                    input_schemas.append(payload["input_schema"])
    assert any("Return message" in (text or "") for text in descriptions)
    assert any(schema.get("properties", {}).get("message", {}).get("type") == "STRING" for schema in input_schemas)
    assert any("message" in schema.get("required", []) for schema in input_schemas)
    assert instance is not None


def test_build_adk_app_produces_llm_agents(tmp_path: Path) -> None:
    pytest.importorskip("google.adk")
    root = _basic_solution(tmp_path)
    runtime = DynamicAgentRuntime(root)
    app = runtime.build_adk_app("travel")

    from google.adk.apps.app import App  # type: ignore import-error
    from google.adk.agents.llm_agent import LlmAgent  # type: ignore import-error
    from google.adk.tools.agent_tool import AgentTool  # type: ignore import-error

    assert isinstance(app, App)
    assert isinstance(app.root_agent, LlmAgent)
    assert app.root_agent.name == "orchestrator"
    assert any(getattr(tool, "tool_spec", None) and getattr(tool.tool_spec, "name", "") == "echo" for tool in app.root_agent.tools)
    concierge_tool = next(
        (tool for tool in app.root_agent.tools if isinstance(tool, AgentTool) and getattr(tool.agent, "name", "") == "concierge"),
        None,
    )
    assert concierge_tool is not None
    concierge_agent = next((agent for agent in app.root_agent.sub_agents if agent.name == "concierge"), None)
    assert concierge_agent is not None
    assert any(getattr(tool, "tool_spec", None) and getattr(tool.tool_spec, "name", "") == "ack" for tool in concierge_agent.tools)


@pytest.mark.usefixtures("google_modules")
def test_agent_tool_defaults_seed_child_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "defaults"
    dump_yaml(
        root / "workflow.yaml",
        {"version": 1, "metadata": {"entrypoint_agent": "orchestrator"}, "catalog": {"agents": []}},
    )
    solution = root / "travel"
    dump_yaml(
        solution / "workflow.yaml",
        {
            "version": 1,
            "catalog": {
                "agents": [
                    {
                        "orchestrator": {
                            "workflow": {
                                "steps": [
                                    {
                                        "step_name": "delegate",
                                        "agents": [
                                            {
                                                "type": "agent_tool",
                                                "agent": "helper",
                                                "input": {
                                                    "origin": "{{ origin }}",
                                                    "destination": "{{ destination }}",
                                                },
                                            }
                                        ],
                                    }
                                ]
                            },
                        }
                    },
                    {
                        "helper": {
                            "workflow": {"steps": []},
                        }
                    },
                ]
            },
        },
    )

    runtime = DynamicAgentRuntime(root)
    app = runtime.build_adk_app("travel")
    root_agent = app.root_agent
    agent_tool = next(tool for tool in root_agent.tools if getattr(tool, "agent", None) is not None)
    assert getattr(agent_tool, "_default_args", {}) == {
        "origin": "{{ origin }}",
        "destination": "{{ destination }}",
    }

    captured: Dict[str, Any] = {}

    async def _fake_run_async(self, *, args, tool_context):  # type: ignore[override]
        captured["args"] = dict(args)
        captured["tool_context"] = tool_context
        return {"status": "ok"}

    from google.adk.tools.agent_tool import AgentTool  # type: ignore import-error

    monkeypatch.setattr(AgentTool, "run_async", _fake_run_async, raising=False)

    state_root = {SESSION_REGISTRY_KEY: {"abc": {"origin": "CWB", "destination": "CDG"}}}
    tool_context = types.SimpleNamespace(state=state_root, session_id="abc")

    asyncio.run(agent_tool.run_async(args={}, tool_context=tool_context))

    assert captured["args"] == {"origin": "CWB", "destination": "CDG"}
    session_state = state_root[SESSION_REGISTRY_KEY]["abc"]
    assert session_state["origin"] == "CWB"
    assert session_state["destination"] == "CDG"
    specialists = session_state["specialists"]["helper"]
    assert specialists["inputs"] == {"origin": "CWB", "destination": "CDG"}
    assert specialists["result"] == {"status": "ok"}


def test_ensure_session_container_reuses_cached_state() -> None:
    session_id = "sess-123"

    first_root: Dict[str, Any] = {}
    first_state = runtime_module._ensure_session_container(first_root, session_id)
    first_state.setdefault("specialists", {}).setdefault("flight_specialist", {}).setdefault("inputs", {})[
        "request"
    ] = "Saindo de Curitiba para Paris"

    second_root: Dict[str, Any] = {}
    second_state = runtime_module._ensure_session_container(second_root, session_id)

    assert second_state is first_state
    assert second_root[SESSION_REGISTRY_KEY][session_id] is first_state


def test_metadata_discovery_honours_env_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = _basic_solution(tmp_path)
    extra_agents = tmp_path / "shared" / "agents"
    extra_tools = tmp_path / "shared" / "tooling"
    _write_module(extra_agents / "helper" / "agent.py", "class Helper:\n    pass\n")
    _write_module(extra_tools / "tools" / "extra" / "tool.py", "class Tool:\n    pass\n")
    monkeypatch.setenv("DA_AGENT_CODE_PATHS", str(extra_agents))
    monkeypatch.setenv("DA_TOOL_CODE_PATHS", str(extra_tools))

    runtime = DynamicAgentRuntime(root)
    solution = runtime.get_solution("travel")
    discovered = solution.workflow["metadata"]["discovered"]
    assert any("helper" in path for path in discovered["agents"])
    assert any("extra" in path for path in discovered["tools"])


def test_runtime_discards_session_after_run_when_not_persisted(tmp_path: Path) -> None:
    root = _basic_solution(tmp_path)
    runtime = DynamicAgentRuntime(root)

    session_id = "cleanup-test"
    payload = {"session_id": session_id, "user_query": "hello"}

    state = runtime.run("travel", payload=payload)

    assert state["user_query"] == "hello"
    assert session_id not in runtime_module.GLOBAL_SESSION_REGISTRY
    assert session_id not in runtime_module._SESSION_REGISTRY_METADATA


def test_persisted_sessions_are_pruned_by_ttl_and_lru(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runtime_module, "SESSION_REGISTRY_MAX_SIZE", 2, raising=False)
    monkeypatch.setattr(runtime_module, "SESSION_REGISTRY_TTL_SECONDS", 0, raising=False)

    current_time = 0.0

    def _fake_now() -> float:
        return current_time

    monkeypatch.setattr(runtime_module, "_session_registry_now", _fake_now, raising=False)

    root = _basic_solution(tmp_path)
    runtime = DynamicAgentRuntime(root)

    current_time = 0.0
    runtime.run(
        "travel",
        payload={"session_id": "persist-1", "persist_session": True, "user_query": "first"},
    )
    assert "persist-1" in runtime_module.GLOBAL_SESSION_REGISTRY

    current_time = 2.0
    runtime.run(
        "travel",
        payload={"session_id": "persist-2", "persist_session": True, "user_query": "second"},
    )
    assert set(runtime_module.GLOBAL_SESSION_REGISTRY) == {"persist-1", "persist-2"}

    restored_state = runtime_module._ensure_session_container({}, "persist-1")
    assert restored_state["user_query"] == "first"

    current_time = 2.0
    runtime.run(
        "travel",
        payload={"session_id": "persist-3", "persist_session": True, "user_query": "third"},
    )

    assert "persist-1" not in runtime_module.GLOBAL_SESSION_REGISTRY
    assert set(runtime_module.GLOBAL_SESSION_REGISTRY) == {"persist-2", "persist-3"}
    assert runtime_module.GLOBAL_SESSION_REGISTRY["persist-2"]["user_query"] == "second"

    # Enable TTL and ensure the least recently touched session expires when time advances.
    monkeypatch.setattr(runtime_module, "SESSION_REGISTRY_TTL_SECONDS", 5, raising=False)

    current_time = 3.0
    runtime_module._ensure_session_container({}, "persist-3")

    current_time = 8.0
    runtime.run(
        "travel",
        payload={"session_id": "persist-4", "persist_session": True, "user_query": "fourth"},
    )

    assert "persist-2" not in runtime_module.GLOBAL_SESSION_REGISTRY
    assert set(runtime_module.GLOBAL_SESSION_REGISTRY) == {"persist-3", "persist-4"}
    assert runtime_module.GLOBAL_SESSION_REGISTRY["persist-3"]["user_query"] == "third"


