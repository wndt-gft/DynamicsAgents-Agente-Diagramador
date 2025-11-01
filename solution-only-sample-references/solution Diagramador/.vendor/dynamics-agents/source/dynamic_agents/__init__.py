"""Runtime utilities for orchestrating multi-agent workflows.

The :mod:`dynamic_agents` package exposes the dynamic runtime used by the
sample solutions in this repository. It can be reused by external projects to
bootstrap solutions that follow the same filesystem conventions and workflow
catalog format.
"""

from importlib import metadata as _importlib_metadata

try:  # pragma: no cover - trivial metadata access
    __version__ = _importlib_metadata.version("dynamics-agents")
except _importlib_metadata.PackageNotFoundError:  # pragma: no cover - local dev install
    __version__ = "0.0.0"

from . import yaml_loader
from .runtime import (
    AgentSpec,
    DynamicAgentRuntime,
    EventRecorder,
    ICON_AGENT,
    ICON_CALLBACK,
    ICON_ENGINE,
    ICON_ERROR,
    ICON_READY,
    ICON_STATE,
    ICON_STEP,
    ICON_TOOL,
    ICON_EVENT,
    available_templates,
    RuntimeCallbackError,
    RuntimeToolError,
    SESSION_REGISTRY_KEY,
    GLOBAL_SESSION_REGISTRY,
    SolutionDescriptor,
    SolutionRuntime,
    ToolSpec,
    SolutionBootstrapError,
    dump_yaml,
    install_all_solution_templates,
    install_runtime_plugins,
    install_solution_template,
    ensure_runtime_requirements,
    ensure_env_sample,
    RUNTIME_CORE_REQUIREMENTS,
    ENV_SAMPLE_LINES,
    invoke_callback,
    invoke_tool,
    load_yaml,
    main,
    normalize_callbacks,
    parse_arguments,
    resolve_placeholders,
    resolve_with_root,
    sanitize_tool_name,
    load_solution_app_module,
    bootstrap_solution_entrypoints,
    locate_solution_root,
)

__all__ = [
    "__version__",
    "AgentSpec",
    "DynamicAgentRuntime",
    "EventRecorder",
    "ICON_AGENT",
    "ICON_CALLBACK",
    "ICON_ENGINE",
    "ICON_ERROR",
    "ICON_READY",
    "ICON_STATE",
    "ICON_STEP",
    "ICON_TOOL",
    "ICON_EVENT",
    "available_templates",
    "RuntimeCallbackError",
    "RuntimeToolError",
    "SESSION_REGISTRY_KEY",
    "GLOBAL_SESSION_REGISTRY",
    "SolutionBootstrapError",
    "SolutionDescriptor",
    "SolutionRuntime",
    "ToolSpec",
    "install_all_solution_templates",
    "install_runtime_plugins",
    "install_solution_template",
    "ensure_runtime_requirements",
    "ensure_env_sample",
    "RUNTIME_CORE_REQUIREMENTS",
    "ENV_SAMPLE_LINES",
    "invoke_callback",
    "invoke_tool",
    "load_yaml",
    "load_solution_app_module",
    "bootstrap_solution_entrypoints",
    "locate_solution_root",
    "main",
    "normalize_callbacks",
    "parse_arguments",
    "resolve_placeholders",
    "resolve_with_root",
    "sanitize_tool_name",
    "yaml_loader",
    "dump_yaml",
]
