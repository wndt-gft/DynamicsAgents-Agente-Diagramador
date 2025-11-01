"""Tests for automatic solution bootstrap helpers."""

import importlib
import os
import shutil
import sys
from pathlib import Path

import dynamic_agents.template_samples.self_test_lab.agent as lab_agent
import dynamic_agents.template_samples.travel_planner.agent as travel_agent
from dynamic_agents import (
    DynamicAgentRuntime,
    bootstrap_solution_entrypoints,
    load_solution_app_module,
    locate_solution_root,
)


def test_locate_solution_root_points_to_solution_directory():
    module_file = Path(travel_agent.__file__)
    solution_root = locate_solution_root(module_file)
    assert solution_root.name == "travel_planner"
    assert (solution_root / "workflow.yaml").exists()
    assert (solution_root / "runtime.yaml").exists()


def test_load_solution_app_module_returns_agent_module():
    package_name = travel_agent.__package__
    module_file = Path(travel_agent.__file__)
    module = load_solution_app_module(package_name, module_file)
    assert hasattr(module, "app")
    assert hasattr(module, "root_agent")
    assert hasattr(module, "run")


def test_bootstrap_solution_entrypoints_returns_callable_runtime():
    module_file = Path(travel_agent.__file__)
    app, root_agent, run = bootstrap_solution_entrypoints(module_file)
    assert hasattr(app, "root_agent")
    assert root_agent is app.root_agent
    assert callable(run)


def test_bootstrap_handles_nested_app_layout(tmp_path, monkeypatch):
    sample_root = Path(travel_agent.__file__).resolve().parent
    nested_root = tmp_path / "travel_planner"
    app_dir = nested_root / "app"
    shutil.copytree(sample_root, app_dir)
    init_source = (sample_root / "__init__.py").read_text(encoding="utf-8")
    (nested_root / "__init__.py").write_text(init_source, encoding="utf-8")
    (app_dir / "__init__.py").write_text("", encoding="utf-8")

    monkeypatch.syspath_prepend(str(tmp_path))
    nested_module = importlib.import_module("travel_planner")

    module_file = Path(nested_module.__file__)
    solution_root = locate_solution_root(module_file)
    assert solution_root == app_dir

    runtime_app, root_agent, run = bootstrap_solution_entrypoints(module_file)
    assert hasattr(runtime_app, "root_agent")
    assert getattr(root_agent, "name", None) == getattr(nested_module.root_agent, "name", None)
    assert callable(run)

    agent_module = importlib.import_module("travel_planner.agent")
    assert agent_module is sys.modules["travel_planner.agent"]
    assert hasattr(agent_module, "root_agent")

    runtime = DynamicAgentRuntime(app_dir)
    assert "travel_planner" in runtime.list_solutions()
    assert runtime.get_solution("travel_planner").name == "travel_planner"
    assert runtime.get_solution("app").name == "travel_planner"

    for name in list(sys.modules):
        if name == "travel_planner" or name.startswith("travel_planner."):
            sys.modules.pop(name, None)


def test_runtime_indexes_top_level_agent_catalog():
    module_file = Path(lab_agent.__file__)
    runtime = DynamicAgentRuntime(module_file.parent)
    solution = runtime.get_solution()

    assert solution.entrypoint_agent == "test_conductor"
    assert "test_conductor" in solution.agents

    app, root_agent, _ = bootstrap_solution_entrypoints(module_file)
    root_name = getattr(root_agent, "name", root_agent)
    assert root_name == "test_conductor"
    assert hasattr(app, "root_agent")


def test_runtime_discovers_solution_with_invalid_search_env(tmp_path, monkeypatch):
    sample_root = Path(travel_agent.__file__).resolve().parent
    destination = tmp_path / "agents" / "travel_planner" / "app"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(sample_root, destination)

    monkeypatch.setenv("DA_WORKFLOW_SEARCH_PATHS", os.pathsep.join(["/caminho/inexistente"]))

    runtime = DynamicAgentRuntime(destination)

    solutions = runtime.list_solutions()
    assert solutions, "Nenhuma solução foi descoberta"

    descriptor = runtime.get_solution()
    assert descriptor.path == destination


def test_runtime_loads_plugins_from_filesystem_paths(tmp_path, monkeypatch):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()

    plugin_file = plugin_dir / "sample_plugin.py"
    plugin_file.write_text(
        "from dynamic_agents.runtime import RuntimePlugin\n\n"
        "class SamplePlugin(RuntimePlugin):\n"
        "    name = 'sample_plugin'\n\n"
        "    def handle_event(self, event):\n"
        "        event.payload.setdefault('sample_plugin', 0)\n"
        "        event.payload['sample_plugin'] += 1\n\n"
        "PLUGIN = SamplePlugin()\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DA_RUNTIME_PLUGINS", str(plugin_dir))

    runtime = DynamicAgentRuntime(Path(travel_agent.__file__).resolve().parent)
    plugin_names = {getattr(plugin, "name", type(plugin).__name__) for plugin in runtime.event_bus._plugins}

    assert "sample_plugin" in plugin_names
