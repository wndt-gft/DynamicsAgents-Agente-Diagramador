from pathlib import Path
import importlib
import sys

import pytest

THIS_FILE = Path(__file__).resolve()
ROOT = next(parent for parent in THIS_FILE.parents if (parent / "pyproject.toml").exists())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dynamic_agents import (
    DynamicAgentRuntime,
    available_templates,
    RUNTIME_CORE_REQUIREMENTS,
    install_all_solution_templates,
    install_solution_template,
    load_yaml,
    main as runtime_main,
)


def test_available_templates_includes_travel_planner():
    assert "travel_planner" in available_templates()


def test_template_samples_root_workflow_lists_all_solutions() -> None:
    package = importlib.import_module("dynamic_agents.template_samples")
    templates_root = Path(package.__file__).resolve().parent
    workflow_path = templates_root / "workflow.yaml"
    assert workflow_path.exists()

    workflow = load_yaml(workflow_path)
    solutions = workflow.get("solutions")
    assert isinstance(solutions, dict)
    assert set(solutions) == set(available_templates())
    for name, descriptor in solutions.items():
        assert descriptor.get("workflow") == f"{name}/workflow.yaml"


def test_cli_lists_samples(capsys: pytest.CaptureFixture[str]) -> None:
    runtime_main(["--list-samples"])
    captured = capsys.readouterr()
    assert "travel_planner" in captured.out


def test_cli_installs_single_sample(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    destination = tmp_path / "workspace"
    runtime_main(["--install-sample", "travel_planner", "--root", str(destination)])

    captured = capsys.readouterr()
    assert "Sample 'travel_planner' copiado" in captured.out
    assert "Dependências essenciais" in captured.out
    assert "Arquivo de ambiente de exemplo" in captured.out

    workflow_file = destination / "workflow.yaml"
    assert not workflow_file.exists(), "Sample installation should keep solution-specific workflows"

    solution_workflow = destination / "travel_planner" / "workflow.yaml"
    assert solution_workflow.exists()

    env_file = destination / ".env.sample"
    assert env_file.exists()
    env_content = env_file.read_text(encoding="utf-8")
    assert "GOOGLE_API_KEY" in env_content
    assert "DA_WORKFLOW_SEARCH_PATHS" in env_content

    runtime = DynamicAgentRuntime(destination)
    assert "travel_planner" in runtime.list_solutions()

    solution = runtime.get_solution("travel_planner")
    assert solution.entrypoint_agent == "travel_receptionist"

    plugins_path = destination / "plugins"
    assert not plugins_path.exists(), "Plugins devem ser instalados via --init"

    requirements_file = destination / "requirements.txt"
    assert requirements_file.exists()
    content = requirements_file.read_text(encoding="utf-8")
    for requirement in RUNTIME_CORE_REQUIREMENTS:
        assert requirement in content


def test_cli_installs_all_samples(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    destination = tmp_path / "workspace"
    runtime_main(["--install-samples", "--root", str(destination)])

    captured = capsys.readouterr().out
    for name in available_templates():
        assert (destination / name).exists()
        assert f"Sample '{name}' copiado" in captured
    assert "Dependências essenciais" in captured
    assert "Arquivo de ambiente de exemplo" in captured

    requirements_file = destination / "requirements.txt"
    assert requirements_file.exists()
    content = requirements_file.read_text(encoding="utf-8")
    for requirement in RUNTIME_CORE_REQUIREMENTS:
        assert requirement in content

    env_file = destination / ".env.sample"
    assert env_file.exists()
    env_content = env_file.read_text(encoding="utf-8")
    assert "GOOGLE_VERTEX_PROJECT" in env_content


def test_install_sample_force_overwrites(tmp_path: Path) -> None:
    destination = tmp_path / "workspace"
    install_solution_template("travel_planner", destination)

    workflow_file = destination / "workflow.yaml"
    workflow_file.write_text("version: 1\nsolutions: {}\n", encoding="utf-8")

    install_solution_template("travel_planner", destination, force=True)

    runtime = DynamicAgentRuntime(destination)
    assert runtime.get_solution("travel_planner").entrypoint_agent == "travel_receptionist"

    requirements_file = destination / "requirements.txt"
    assert requirements_file.exists()
    content = requirements_file.read_text(encoding="utf-8")
    for requirement in RUNTIME_CORE_REQUIREMENTS:
        assert requirement in content

    env_file = destination / ".env.sample"
    assert env_file.exists()


def test_install_template_can_copy_plugins(tmp_path: Path) -> None:
    destination = tmp_path / "workspace"
    install_solution_template("travel_planner", destination, copy_plugins=True)

    plugins_destination = destination / "plugins"
    assert plugins_destination.exists()
    assert any(plugins_destination.rglob("*.py")), "Plugins devem ser copiados junto ao sample quando solicitado"

    requirements_file = destination / "requirements.txt"
    assert requirements_file.exists()
    content = requirements_file.read_text(encoding="utf-8")
    for requirement in RUNTIME_CORE_REQUIREMENTS:
        assert requirement in content

    env_file = destination / ".env.sample"
    assert env_file.exists()


def test_install_all_solution_templates_helper(tmp_path: Path) -> None:
    destination = tmp_path / "workspace"
    results = install_all_solution_templates(destination)

    assert set(results) == set(available_templates())
    for path in results.values():
        assert path.exists()

    requirements_file = destination / "requirements.txt"
    assert requirements_file.exists()
    content = requirements_file.read_text(encoding="utf-8")
    for requirement in RUNTIME_CORE_REQUIREMENTS:
        assert requirement in content

    env_file = destination / ".env.sample"
    assert env_file.exists()


def test_travel_template_copies_tooling(tmp_path: Path) -> None:
    destination = tmp_path / "workspace"
    install_solution_template("travel_planner", destination)

    expected_files = [
        destination
        / "travel_planner"
        / "workflow.yaml",
        destination
        / "travel_planner"
        / "agent.py",
        destination
        / "travel_planner"
        / "agents"
        / "tourism_specialist"
        / "workflow.yaml",
        destination
        / "travel_planner"
        / "agents"
        / "hotel_specialist"
        / "workflow.yaml",
        destination
        / "travel_planner"
        / "agents"
        / "flight_specialist"
        / "workflow.yaml",
        destination
        / "travel_planner"
        / "agents"
        / "itinerary_specialist"
        / "workflow.yaml",
        destination
        / "travel_planner"
        / "agents"
        / "itinerary_specialist"
        / "tools"
        / "interactions"
        / "trip_builder"
        / "tool.py",
        destination
        / "travel_planner"
        / "tools"
        / "interactions"
        / "web_travel_search"
        / "metadata.yaml",
        destination
        / "travel_planner"
        / "tools"
        / "callbacks"
        / "model_response"
        / "strip_internal_commands"
        / "callback.py",
    ]

    for path in expected_files:
        assert path.exists(), f"Missing expected template artifact: {path}"


def test_cli_init_installs_plugins(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    destination = tmp_path / "workspace"
    runtime_main(["--init", "--root", str(destination)])

    captured = capsys.readouterr().out
    plugins_destination = destination / "plugins"
    assert plugins_destination.exists()
    assert "Plugins padrão disponíveis" in captured
    assert "Dependências essenciais" in captured
    assert "Arquivo de ambiente de exemplo" in captured

    requirements_file = destination / "requirements.txt"
    assert requirements_file.exists()
    content = requirements_file.read_text(encoding="utf-8")
    for requirement in RUNTIME_CORE_REQUIREMENTS:
        assert requirement in content

    env_file = destination / ".env.sample"
    assert env_file.exists()


def test_travel_agent_import_does_not_mutate_sys_path(tmp_path: Path, monkeypatch):
    from tests.runtime import test_dynamic_agent_runtime as runtime_tests

    google_stub = runtime_tests.google_modules._fixture_function()
    next(google_stub)

    try:
        workspace = tmp_path / "workspace"
        install_solution_template("travel_planner", workspace)

        monkeypatch.syspath_prepend(str(workspace))

        original_sys_path = list(sys.path)
        module = importlib.import_module("travel_planner.agent")
        assert callable(getattr(module, "run", None)), "agent module should expose a run callable"
        assert sys.path == original_sys_path, "agent import should not modify sys.path dynamically"
    finally:
        google_stub.close()


def test_trip_builder_uses_state_name() -> None:
    from dynamic_agents.template_samples.travel_planner.agents.itinerary_specialist.tools.interactions.trip_builder.tool import (
        Tool,
    )

    tool = Tool(metadata={})
    state = {
        "profile": {"name": "Alex"},
        "web_travel_search:search_hotels": {"options": [{"title": "Hotel"}]},
        "web_travel_search:search_flights": {"itineraries": [{"title": "Flight"}]},
    }

    result = tool.compile_itinerary(state=state)
    assert "Alex" in result["summary"]


def test_trip_builder_defaults_to_generic_name() -> None:
    from dynamic_agents.template_samples.travel_planner.agents.itinerary_specialist.tools.interactions.trip_builder.tool import (
        Tool,
    )

    tool = Tool(metadata={})
    result = tool.compile_itinerary(state={})
    assert "Viajante" in result["summary"]


def test_travel_receptionist_specialists_are_sub_agents(tmp_path: Path) -> None:
    from tests.runtime import test_dynamic_agent_runtime as runtime_tests

    google_stub = runtime_tests.google_modules_stub._fixture_function()
    next(google_stub)
    try:
        destination = tmp_path / "workspace"
        install_solution_template("travel_planner", destination)

        runtime = DynamicAgentRuntime(destination)
        app = runtime.build_adk_app("travel_planner")
        root_agent = app.root_agent

        specialist_names = {
            "flight_specialist",
            "hotel_specialist",
            "tourism_specialist",
            "itinerary_specialist",
        }

        sub_agent_names = {getattr(agent, "name", None) for agent in root_agent.sub_agents}
        assert specialist_names.issubset(sub_agent_names)

        from google.adk.tools.agent_tool import AgentTool  # type: ignore import-error

        delegated_as_tools = {
            getattr(tool.agent, "name", None)
            for tool in root_agent.tools
            if isinstance(tool, AgentTool)
        }
        assert not (specialist_names & delegated_as_tools), "Especialistas devem ser delegados como agentes, não ferramentas"
    finally:
        google_stub.close()
