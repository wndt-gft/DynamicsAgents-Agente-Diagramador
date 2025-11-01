# -*- coding: utf-8 -*-
"""Dynamic runtime for orchestrating catalog based multi-agent solutions.

This module intentionally keeps the implementation compact and explicit.  It is
responsible for four main tasks:

* Discover all workflows available on disk and merge them with their parent
  workflow definitions when present.
* Enrich workflow metadata with code artifacts (agents, tools and callbacks)
  that live next to the workflow files.
* Instantiate the agent hierarchy declared in the workflow, wiring tools and
  callbacks so the execution flow mirrors the workflow definition.
* Emit rich runtime events so pluggable extensions (metrics, logs, tracing,
  security checks, ... ) can observe or augment the execution.

The implementation favours readability over clever abstractions – everything is
kept in a single module and the control flow is linear.  The behaviour is
extensively covered by unit tests so refactors remain safe.
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import dataclasses
import enum
import importlib
import importlib.util
from importlib import import_module
import sys
import inspect
import io
import json
import logging
import os
import re
import shutil
import textwrap
import time
import types
import unicodedata
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
    Union,
    get_args,
    get_origin,
)
import traceback
from datetime import date

from .yaml_loader import safe_load as yaml_safe_load, safe_dump as yaml_safe_dump

logger = logging.getLogger("dynamic_agent")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))
    logger.addHandler(handler)
logger.setLevel(os.getenv("AGENT_ENGINE_LOG_LEVEL", "INFO"))
logger.propagate = False

ICON_ENGINE = "🧩"
ICON_AGENT = "🤖"
ICON_TOOL = "🛠️"
ICON_CALLBACK = "🔁"
ICON_EVENT = "🗓️"
ICON_STATE = "🗄️"
ICON_ERROR = "❌"
ICON_READY = "✅"
ICON_STEP = "⚙️"
ICON_SKIP = "⏭️"
ICON_WARNING = "⚠️"

RUNTIME_LOGGING_PLUGIN_NAME = "runtime.logging"

SESSION_REGISTRY_KEY = "sessions"


ASCII_BANNER = """██████╗ ██╗   ██╗███╗   ██╗ █████╗ ███╗   ███╗██╗ ██████╗███████╗
██╔══██╗╚██╗ ██╔╝████╗  ██║██╔══██╗████╗ ████║██║██╔════╝██╔════╝
██║  ██║ ╚████╔╝ ██╔██╗ ██║███████║██╔████╔██║██║██║     ███████╗
██║  ██║  ╚██╔╝  ██║╚██╗██║██╔══██║██║╚██╔╝██║██║██║     ╚════██║
██████╔╝   ██║   ██║ ╚████║██║  ██║██║ ╚═╝ ██║██║╚██████╗███████║
╚═════╝    ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝ ╚═════╝╚══════╝

        █████╗  ██████╗ ███████╗███╗   ██╗████████╗███████╗
       ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝██╔════╝
       ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ███████╗
       ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ╚════██║
       ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ███████║
       ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝  0.1.1"""


# --------------------------------------------------------------------------- #
# CLI banner helpers
# --------------------------------------------------------------------------- #


def render_cli_banner(today: Optional[date] = None) -> str:
    stamp = (today or date.today()).strftime("%Y-%m-%d")
    banner_lines = [
        ASCII_BANNER.rstrip("\n"),
        "---------------------------------------------------------------------",
        "Dynamics Agents  ::  Orquestração dinâmica de times de agentes inteligentes",
        f"v0.1.1 — {stamp} | Author: Willian Patrick dos Santos (superhitec@gmail.com)",
        "---------------------------------------------------------------------",
    ]
    return "\n".join(banner_lines)


def print_cli_banner(today: Optional[date] = None) -> None:
    print(render_cli_banner(today), file=sys.stderr)


# Global cache that keeps session states accessible across nested ADK tool
# invocations. Some host environments provide fresh tool contexts without the
# previously mutated state payload, so we retain a reference keyed by session
# identifier to restore the same mapping whenever `_ensure_session_container`
# is invoked again.
GLOBAL_SESSION_REGISTRY: Dict[str, Dict[str, Any]] = {}


@dataclass
class SessionRegistryMetadata:
    created_at: float
    last_access: float
    access_count: int = 0
    pinned: bool = False


_SESSION_REGISTRY_METADATA: Dict[str, SessionRegistryMetadata] = {}


def _session_registry_reset() -> None:
    GLOBAL_SESSION_REGISTRY.clear()
    _SESSION_REGISTRY_METADATA.clear()


def _register_session_registry_shutdown() -> None:
    def _cleanup() -> None:
        try:
            _session_registry_reset()
        except Exception:  # pragma: no cover - defensive
            logger.debug("%s Failed to reset session registry on exit", ICON_ERROR, exc_info=True)

    atexit.register(_cleanup)


_register_session_registry_shutdown()


def _resolve_int_env(var_name: str, default: int) -> int:
    raw_value = os.getenv(var_name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


SESSION_REGISTRY_TTL_SECONDS = _resolve_int_env("DA_SESSION_REGISTRY_TTL", 1800)
SESSION_REGISTRY_MAX_SIZE = _resolve_int_env("DA_SESSION_REGISTRY_MAX", 64)

DEFAULT_WORKFLOW_GLOB = "workflow.yaml"
WORKFLOW_ENV = "DA_WORKFLOW_SEARCH_PATHS"
AGENT_CODE_ENV = "DA_AGENT_CODE_PATHS"
TOOL_CODE_ENV = "DA_TOOL_CODE_PATHS"
PLUGIN_ENV = "DA_RUNTIME_PLUGINS"
# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fp:
        return yaml_safe_load(fp.read()) or {}


def dump_yaml(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        fp.write(yaml_safe_dump(payload, sort_keys=False))


def _session_registry_now() -> float:
    return time.time()


def _session_registry_is_expired(metadata: SessionRegistryMetadata, now: Optional[float] = None) -> bool:
    ttl = SESSION_REGISTRY_TTL_SECONDS
    if ttl <= 0:
        return False
    reference = now if now is not None else _session_registry_now()
    return reference - metadata.last_access > ttl


def _session_registry_remove(session_id: str) -> None:
    GLOBAL_SESSION_REGISTRY.pop(session_id, None)
    _SESSION_REGISTRY_METADATA.pop(session_id, None)


def _session_registry_prune(now: Optional[float] = None) -> None:
    reference = now if now is not None else _session_registry_now()

    if SESSION_REGISTRY_TTL_SECONDS > 0:
        for sid, metadata in list(_SESSION_REGISTRY_METADATA.items()):
            if _session_registry_is_expired(metadata, reference):
                _session_registry_remove(sid)

    max_size = SESSION_REGISTRY_MAX_SIZE
    if max_size <= 0 or len(GLOBAL_SESSION_REGISTRY) <= max_size:
        return

    entries = sorted(
        _SESSION_REGISTRY_METADATA.items(),
        key=lambda item: item[1].last_access,
    )

    # First discard non-pinned entries respecting LRU order.
    for sid, metadata in entries:
        if len(GLOBAL_SESSION_REGISTRY) <= max_size:
            return
        if metadata.pinned:
            continue
        _session_registry_remove(sid)

    if len(GLOBAL_SESSION_REGISTRY) <= max_size:
        return

    # As a last resort remove pinned entries (oldest first) to honour max size.
    for sid, _metadata in entries:
        if len(GLOBAL_SESSION_REGISTRY) <= max_size:
            return
        _session_registry_remove(sid)


def _session_registry_store(session_id: str, state: Dict[str, Any], *, pinned: bool = False) -> Dict[str, Any]:
    now = _session_registry_now()
    metadata = _SESSION_REGISTRY_METADATA.get(session_id)
    if metadata is None:
        metadata = SessionRegistryMetadata(created_at=now, last_access=now, access_count=1, pinned=pinned)
        _SESSION_REGISTRY_METADATA[session_id] = metadata
    else:
        metadata.last_access = now
        metadata.access_count += 1
        metadata.pinned = metadata.pinned or pinned
    GLOBAL_SESSION_REGISTRY[session_id] = state
    _session_registry_prune(now)
    return state


def _session_registry_get(session_id: str) -> Optional[Dict[str, Any]]:
    metadata = _SESSION_REGISTRY_METADATA.get(session_id)
    if metadata is None:
        return None
    state = GLOBAL_SESSION_REGISTRY.get(session_id)
    if state is None:
        _SESSION_REGISTRY_METADATA.pop(session_id, None)
        return None
    now = _session_registry_now()
    if _session_registry_is_expired(metadata, now):
        _session_registry_remove(session_id)
        return None
    metadata.last_access = now
    metadata.access_count += 1
    return state


def _ensure_project_root_on_sys_path(path: Path) -> None:
    if not path:
        return
    root = path if path.is_dir() else path.parent
    if root and str(root) not in sys.path:
        sys.path.insert(0, str(root))


def sanitize_tool_name(name: Optional[str]) -> str:
    if not name:
        return ""
    if not isinstance(name, str):
        return ""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").lower()
    return normalized


def _humanize_identifier(identifier: Optional[str]) -> str:
    if not identifier:
        return ""
    text = re.sub(r"[_\-.]+", " ", str(identifier)).strip()
    if not text:
        return str(identifier)
    return text[:1].upper() + text[1:]


def normalize_function_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    candidate = re.sub(r"[^0-9a-zA-Z_]+", "_", str(name).strip())
    candidate = candidate.strip("_")
    if not candidate:
        return None
    if not candidate[0].isalpha():
        candidate = f"f_{candidate}"
    if len(candidate) > 64:
        candidate = candidate[:64]
    return candidate or None


_WORKSPACE_SENTINELS = (
    ".env",
    ".env.local",
    "requirements.txt",
    "requirements.in",
    "pyproject.toml",
    "setup.cfg",
)


def _workspace_root_for(path: Optional[Path]) -> Optional[Path]:
    if path is None:
        return None
    try:
        current = Path(path).resolve()
    except FileNotFoundError:
        current = Path(path).absolute()
    for candidate in [current] + list(current.parents):
        for marker in _WORKSPACE_SENTINELS:
            if (candidate / marker).exists():
                return candidate
    return current


def resolve_with_root(root: Path, candidate: Optional[str]) -> Path:
    if not candidate:
        return root
    candidate_path = Path(candidate)
    if candidate_path.is_absolute():
        root_path = Path(root)
        workspace_root = _workspace_root_for(root_path)
        parts_without_anchor = candidate_path.parts[1:]
        if (
            workspace_root is not None
            and parts_without_anchor
            and (
                (candidate_path.anchor and candidate_path.anchor != workspace_root.anchor and not candidate_path.drive)
                or not candidate_path.exists()
            )
        ):
            return (workspace_root.joinpath(*parts_without_anchor)).resolve()
        return candidate_path
    return (root / candidate_path).resolve()


_PLACEHOLDER_PATTERN = re.compile(r"{{\s*(?:state\.)?([a-zA-Z0-9_.]+)\s*}}")


def _resolve_from_state(state: Dict[str, Any], dotted_path: str) -> Any:
    parts = dotted_path.split(".")
    current: Any = state
    for part in parts:
        if isinstance(current, MutableMapping) and part in current:
            current = current[part]
        else:
            return None
    return current


def resolve_placeholders(payload: Any, state: Dict[str, Any]) -> Any:
    if isinstance(payload, str):
        def _replace(match: re.Match[str]) -> str:
            value = _resolve_from_state(state, match.group(1))
            return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else ("" if value is None else str(value))

        return _PLACEHOLDER_PATTERN.sub(_replace, payload)

    if isinstance(payload, list):
        return [resolve_placeholders(item, state) for item in payload]

    if isinstance(payload, dict):
        return {key: resolve_placeholders(value, state) for key, value in payload.items()}

    return payload


def normalize_callbacks(raw_value: Any) -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    if not raw_value:
        return mapping
    if isinstance(raw_value, dict):
        for event, names in raw_value.items():
            if isinstance(names, list):
                mapping[event] = [str(name) for name in names if name]
            elif isinstance(names, str):
                mapping[event] = [names]
        return mapping
    for entry in raw_value:
        if not isinstance(entry, dict):
            continue
        for event, names in entry.items():
            if isinstance(names, list):
                mapping.setdefault(event, []).extend(str(name) for name in names if name)
            elif isinstance(names, str):
                mapping.setdefault(event, []).append(names)
    return mapping


def resolve_argument_template(template: Any, state: Dict[str, Any]) -> Any:
    if isinstance(template, str):
        match = _PLACEHOLDER_PATTERN.fullmatch(template.strip())
        if match:
            return _resolve_from_state(state, match.group(1))
    return resolve_placeholders(template, state)


def _resolve_session_id(source: Any) -> Optional[str]:
    if source is None:
        return None
    if isinstance(source, dict):
        for key in ("session_id", "sessionId", "sessionID", "id"):
            value = source.get(key)
            if isinstance(value, str) and value:
                return value
        nested = source.get("session") or source.get("context")
        if nested:
            return _resolve_session_id(nested)
        return None
    for attr in ("session_id", "sessionId", "sessionID", "id"):
        value = getattr(source, attr, None)
        if isinstance(value, str) and value:
            return value
    nested = getattr(source, "session", None) or getattr(source, "context", None)
    if nested:
        return _resolve_session_id(nested)
    return None


def _ensure_session_container(state: Optional[Dict[str, Any]], session_id: Optional[str]) -> Dict[str, Any]:
    if not isinstance(state, dict):
        state = {}
    if not session_id:
        return state

    registry = state.setdefault(SESSION_REGISTRY_KEY, {})
    if not isinstance(registry, dict):
        registry = {}
        state[SESSION_REGISTRY_KEY] = registry

    cached_state = _session_registry_get(session_id)
    existing = registry.get(session_id)

    if isinstance(existing, dict) and cached_state and existing is not cached_state:
        _deep_merge(cached_state, existing)
        registry[session_id] = cached_state
        session_state = cached_state
    elif isinstance(existing, dict):
        session_state = existing
    elif isinstance(cached_state, dict):
        registry[session_id] = cached_state
        session_state = cached_state
    else:
        session_state = {}
        registry[session_id] = session_state

    session_state.setdefault("session_id", session_id)
    _session_registry_store(session_id, session_state)
    return session_state


# --------------------------------------------------------------------------- #
# Runtime events and plugins
# --------------------------------------------------------------------------- #


@dataclass
class RuntimeEvent:
    name: str
    scope: str
    payload: Dict[str, Any]


class RuntimePlugin:
    """Base class for runtime plugins."""

    def handle_event(self, event: RuntimeEvent) -> None:  # pragma: no cover - default is noop
        pass


class RuntimeEventBus:
    def __init__(self, plugins: Optional[Iterable[RuntimePlugin]] = None):
        self._plugins: List[RuntimePlugin] = list(plugins or [])

    def register(self, plugin: RuntimePlugin) -> None:
        self._plugins.append(plugin)

    def emit(self, name: str, scope: str, payload: Optional[Dict[str, Any]] = None) -> None:
        event = RuntimeEvent(name=name, scope=scope, payload=dict(payload or {}))
        for plugin in list(self._plugins):
            try:
                plugin.handle_event(event)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("%s Plugin %s failed for event %s: %s", ICON_ERROR, plugin, name, exc)


class EventRecorder(RuntimePlugin):
    """Simple plugin that keeps a list of emitted events (useful for tests)."""

    def __init__(self):
        self.events: List[RuntimeEvent] = []

    def handle_event(self, event: RuntimeEvent) -> None:
        self.events.append(event)


def _log_plugin_error(plugin_path: Path, exc: BaseException) -> None:
    logger.warning("%s Failed to load plugin '%s': %s", ICON_ERROR, plugin_path, exc)


def _plugin_name(plugin: RuntimePlugin) -> Optional[str]:
    return getattr(plugin, "PLUGIN_NAME", None) or getattr(plugin, "name", None)


def _event_bus_has_plugin(event_bus: RuntimeEventBus, plugin_name: str) -> bool:
    return any(_plugin_name(plugin) == plugin_name for plugin in getattr(event_bus, "_plugins", []))


def _plugin_sort_key(root: Path, path: Path) -> Tuple[Any, ...]:
    relative = path.relative_to(root)
    folders = relative.parts[:-1]
    stem = Path(relative.name).stem
    segments = stem.split(".")
    order = 0
    plugin_name = segments[-1] if segments else stem
    event_name = ""
    if len(segments) >= 3:
        event_name = ".".join(segments[:-2])
        try:
            order = int(segments[-2])
        except ValueError:
            order = 0
    elif len(segments) == 2:
        event_name = segments[0]
        try:
            order = int(segments[1])
        except ValueError:
            plugin_name = segments[1]
    else:
        event_name = stem
    return (*folders, event_name, order, plugin_name)


def _module_name_for_plugin(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    sanitized_parts = [part.replace(".", "_").replace("-", "_") for part in relative.with_suffix("").parts]
    return f"{__name__}.plugins.{'.'.join(sanitized_parts)}"


def _load_plugin_module(path: Path, root: Path) -> Optional[types.ModuleType]:
    module_name = _module_name_for_plugin(path, root)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[call-arg]
    except Exception as exc:  # pragma: no cover - defensive
        _log_plugin_error(path, exc)
        return None
    return module


@lru_cache()
def _builtin_plugin_factories() -> Tuple[Callable[[], RuntimePlugin], ...]:
    root = Path(__file__).resolve().parent / "plugins"
    if not root.exists():
        return tuple()
    factories: List[Callable[[], RuntimePlugin]] = []
    for path in sorted(root.rglob("*.py"), key=lambda candidate: _plugin_sort_key(root, candidate)):
        if path.name == "__init__.py":
            continue
        module = _load_plugin_module(path, root)
        if module is None:
            continue
        factory = getattr(module, "build_plugin", None)
        if callable(factory):
            def _make_factory(
                callable_factory: Callable[[], RuntimePlugin], plugin_path: Path
            ) -> Callable[[], RuntimePlugin]:
                def _build() -> RuntimePlugin:
                    plugin = callable_factory()
                    if not isinstance(plugin, RuntimePlugin):
                        raise TypeError(
                            f"Factory for plugin '{plugin_path}' did not return a RuntimePlugin instance"
                        )
                    return plugin

                return _build

            factories.append(_make_factory(factory, path))
            continue
        plugin_instance = getattr(module, "PLUGIN", None)
        if isinstance(plugin_instance, RuntimePlugin):
            factories.append(lambda plugin=plugin_instance: plugin)
    return tuple(factories)


def _instantiate_builtin_plugins() -> List[RuntimePlugin]:
    return [factory() for factory in _builtin_plugin_factories()]


def _instantiate_builtin_plugin_by_name(name: str) -> Optional[RuntimePlugin]:
    for factory in _builtin_plugin_factories():
        plugin = factory()
        if _plugin_name(plugin) == name:
            return plugin
    return None


def _load_runtime_plugins(
    extra_plugins: Optional[Iterable[RuntimePlugin]] = None,
    *,
    search_root: Optional[Path] = None,
) -> List[RuntimePlugin]:
    builtin_plugins = _instantiate_builtin_plugins()
    plugins_from_env = _load_plugins_from_env(search_root=search_root)
    assembled = builtin_plugins + list(extra_plugins or []) + plugins_from_env
    return assembled


def _stringify_payload(payload: Dict[str, Any]) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return repr(payload)


def _stringify_object(value: Any) -> str:
    if isinstance(value, dict):
        return _stringify_payload(value)
    if isinstance(value, list):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except TypeError:
            return repr(value)
    return str(value)


def _extract_message(content: Any) -> Optional[str]:
    if content is None:
        return None
    if isinstance(content, str):
        stripped = content.strip()
        return stripped or None
    if isinstance(content, dict):
        for key in ("message", "result", "text", "request", "response", "content"):
            if key in content:
                candidate = _extract_message(content.get(key))
                if candidate:
                    return candidate
        for key in ("messages", "outputs", "choices", "parts"):
            value = content.get(key)
            candidate = _extract_message(value)
            if candidate:
                return candidate
        return _extract_message(list(content.values()))
    if isinstance(content, (list, tuple, set)):
        for item in content:
            candidate = _extract_message(item)
            if candidate:
                return candidate
        return None
    return None


def _exception_details(exc: BaseException) -> Dict[str, Any]:
    """Return a structured payload describing the given exception."""

    stacktrace = traceback.format_exc()
    details: Dict[str, Any] = {
        "message": str(exc),
        "details": {"type": exc.__class__.__name__, "repr": repr(exc)},
        "stacktrace": stacktrace,
    }
    return details


def _looks_like_plugin_path(entry: str) -> bool:
    if not entry:
        return False
    if entry.endswith(".py"):
        return True
    if entry.startswith(".") or entry.startswith("~"):
        return True
    separators = {os.sep}
    if os.altsep:
        separators.add(os.altsep)
    return any(sep and sep in entry for sep in separators)


def _extract_plugins_from_module(module: ModuleType, identifier: str) -> List[RuntimePlugin]:
    plugins: List[RuntimePlugin] = []
    candidate = getattr(module, "PLUGIN", None)
    if isinstance(candidate, RuntimePlugin):
        plugins.append(candidate)
    factory = getattr(module, "build_plugin", None)
    if callable(factory):
        try:
            plugin = factory()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("%s Plugin factory '%s' failed: %s", ICON_ERROR, identifier, exc)
        else:
            if isinstance(plugin, RuntimePlugin):
                plugins.append(plugin)
    return plugins


def _iter_candidate_plugin_paths(entry: str, search_root: Optional[Path]) -> Iterator[Path]:
    resolved_entry = Path(entry).expanduser()
    workspace_root = _workspace_root_for(search_root)
    seen: set[Path] = set()
    yield_queue: List[Path] = []

    def _push(candidate: Path) -> None:
        try:
            canonical = candidate.resolve()
        except FileNotFoundError:
            if candidate.is_absolute():
                canonical = candidate
            else:
                canonical = (search_root or Path.cwd()).joinpath(candidate)
        except RuntimeError:  # pragma: no cover - resolution loop
            canonical = candidate.absolute()
        if canonical not in seen:
            seen.add(canonical)
            yield_queue.append(candidate)

    if resolved_entry.is_absolute():
        _push(resolved_entry)
        parts_without_anchor = resolved_entry.parts[1:]
        if workspace_root is not None and parts_without_anchor:
            _push(workspace_root.joinpath(*parts_without_anchor))
        if parts_without_anchor and search_root is not None:
            anchors = [search_root] + list(search_root.parents)
            for anchor in anchors:
                _push(anchor.joinpath(*parts_without_anchor))
    else:
        if search_root is not None:
            anchors = [search_root] + list(search_root.parents)
            for anchor in anchors:
                _push(anchor / resolved_entry)
        _push(Path.cwd() / resolved_entry)

    while yield_queue:
        candidate = yield_queue.pop(0)
        yield candidate


def _load_plugins_from_path(path: Path) -> List[RuntimePlugin]:
    if path.is_file():
        module = _load_plugin_module(path, path.parent)
        if not module:
            return []
        return _extract_plugins_from_module(module, str(path))

    if path.is_dir():
        plugins: List[RuntimePlugin] = []
        for candidate in sorted(
            path.rglob("*.py"), key=lambda candidate: _plugin_sort_key(path, candidate)
        ):
            if candidate.name == "__init__.py":
                continue
            module = _load_plugin_module(candidate, path)
            if not module:
                continue
            plugins.extend(_extract_plugins_from_module(module, str(candidate)))
        return plugins

    return []


def _load_plugins_from_env(*, search_root: Optional[Path] = None) -> List[RuntimePlugin]:
    plugins: List[RuntimePlugin] = []
    raw = os.getenv(PLUGIN_ENV)
    if not raw:
        return plugins
    for entry in raw.split(os.pathsep):
        module_path = entry.strip()
        if not module_path:
            continue
        if _looks_like_plugin_path(module_path):
            loaded = False
            for candidate in _iter_candidate_plugin_paths(module_path, search_root):
                discovered = _load_plugins_from_path(candidate)
                if discovered:
                    plugins.extend(discovered)
                    loaded = True
                    break
            if not loaded:
                logger.warning("%s Caminho de plugin '%s' não encontrado", ICON_ERROR, module_path)
            continue
        try:
            module = importlib.import_module(module_path)
        except Exception as exc:  # pragma: no cover - invalid plugin configuration
            logger.warning("%s Failed to import plugin '%s': %s", ICON_ERROR, module_path, exc)
            continue
        plugins.extend(_extract_plugins_from_module(module, module_path))
    return plugins


# --------------------------------------------------------------------------- #
# Workflow interpretation
# --------------------------------------------------------------------------- #


def _deep_merge(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in extra.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        elif key in base and isinstance(base[key], list) and isinstance(value, list):
            base[key] = list(base[key]) + [item for item in value if item not in base[key]]
        else:
            base[key] = value
    return base


def _workflow_parent_chain(path: Path, root: Path) -> List[Path]:
    parents: List[Path] = []
    current = path.parent
    while root in current.parents or current == root:
        candidate = current / DEFAULT_WORKFLOW_GLOB
        if candidate.exists() and candidate != path:
            parents.append(candidate)
        if current == root:
            break
        current = current.parent
    parents.reverse()
    return parents


@dataclass
class StepSpec:
    name: str
    instructions: Optional[str]
    label: str = ""
    tools: List[Dict[str, Any]] = field(default_factory=list)
    agent_tools: List[Dict[str, Any]] = field(default_factory=list)
    agents: List[Dict[str, Any]] = field(default_factory=list)
    callbacks: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class AgentSpec:
    name: str
    label: str = ""
    description: str = ""
    system_instructions: Optional[str] = None
    assistant_instructions: Optional[str] = None
    model_settings: Dict[str, Any] = field(default_factory=dict)
    workflow: Dict[str, Any] = field(default_factory=dict)
    steps: List[StepSpec] = field(default_factory=list)


@dataclass
class ToolSpec:
    name: str
    label: str
    kind: str
    scope: str
    metadata: Dict[str, Any]
    module_path: Optional[Path] = None
    event_channel: Optional[str] = None
    _instance: Any = field(default=None, init=False, repr=False)

    def ensure_instance(self) -> Any:
        if self._instance is not None:
            return self._instance
        if not self.module_path:
            return None
        module_name = f"dynamic_tool_{self.name}_{abs(hash(self.module_path))}"
        _ensure_project_root_on_sys_path(self.module_path)
        spec = importlib.util.spec_from_file_location(module_name, self.module_path)
        if not spec or not spec.loader:
            raise ImportError(f"Cannot import tool module at {self.module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        if hasattr(module, "build_tool"):
            self._instance = module.build_tool(self.metadata)
        elif hasattr(module, "Tool"):
            self._instance = _instantiate_with_optional_metadata(module.Tool, self.metadata)
        elif hasattr(module, "Callback"):
            self._instance = _instantiate_with_optional_metadata(module.Callback, self.metadata)
        else:
            factory = getattr(module, "create", None)
            if callable(factory):
                self._instance = factory(self.metadata)
        if self._instance is None:
            raise AttributeError(
                f"Tool module '{self.module_path}' does not expose a Tool/Callback factory."
            )
        self._enrich_metadata_from_instance()
        return self._instance

    def _enrich_metadata_from_instance(self) -> None:
        if not self._instance:
            return
        meta = self.metadata.setdefault("metadata", {})
        if "name" not in meta:
            meta["name"] = getattr(self._instance, "__class__", type(self._instance)).__name__
        if "description" not in meta:
            description = inspect.getdoc(self._instance) or inspect.getdoc(self._instance.__class__)
            if description:
                meta["description"] = description
        methods_list = self.metadata.setdefault("methods", [])
        method_lookup: Dict[str, Tuple[str, Dict[str, Any]]] = {}
        for entry in methods_list:
            if not isinstance(entry, dict) or not entry:
                continue
            method_name, payload = next(iter(entry.items()))
            if not isinstance(payload, dict):
                payload = {} if payload is None else {"value": payload}
                entry[method_name] = payload
            sanitized = sanitize_tool_name(method_name)
            method_lookup[sanitized] = (method_name, payload)
        for name, member in inspect.getmembers(self._instance, predicate=inspect.ismethod):
            if name.startswith("_"):
                continue
            sanitized = sanitize_tool_name(name)
            existing = method_lookup.get(sanitized)
            if existing:
                method_name, payload = existing
            else:
                payload = {}
                methods_list.append({name: payload})
                method_lookup[sanitized] = (name, payload)
            if "description" not in payload or not payload.get("description"):
                doc = inspect.getdoc(member)
                if doc:
                    payload["description"] = doc
            try:
                signature = inspect.signature(member)
            except (TypeError, ValueError):
                signature = None
            if signature and not payload.get("input_schema"):
                schema = _build_input_schema_from_signature(signature)
                if schema:
                    payload["input_schema"] = schema
            if signature and not payload.get("output_schema"):
                output_schema = _python_type_to_schema(signature.return_annotation)
                if output_schema:
                    payload["output_schema"] = output_schema
        self.metadata["methods"] = methods_list


@dataclass
class SolutionDescriptor:
    name: str
    path: Path
    workflow_path: Path
    entrypoint_agent: Optional[str] = None
    workflow: Dict[str, Any] = field(default_factory=dict)
    agents: Dict[str, AgentSpec] = field(default_factory=dict)
    tools: Dict[str, ToolSpec] = field(default_factory=dict)
    callbacks: Dict[str, ToolSpec] = field(default_factory=dict)
    runtime_config: Dict[str, Any] = field(default_factory=dict)

    def configure(self, root: Path) -> None:
        logger.info("%s Configurando solução '%s'", ICON_ENGINE, self.name)
        interpreter = WorkflowInterpreter(self.workflow_path, root)
        self.workflow = interpreter.load()
        metadata = self.workflow.get("metadata") or {}
        if not self.entrypoint_agent:
            self.entrypoint_agent = metadata.get("entrypoint_agent")
        self._index_agents()
        self._discover_resources()
        self._augment_metadata()
        runtime_cfg = self.workflow.get("runtime") or {}
        if runtime_cfg:
            self.runtime_config = runtime_cfg

    # ------------------------------------------------------------------ #
    def _index_agents(self) -> None:
        catalog = self.workflow.get("catalog", {})
        if "catalog" not in self.workflow:
            self.workflow["catalog"] = catalog

        agents_section: List[Any] = []

        top_level_agents = self.workflow.get("agents")
        if isinstance(top_level_agents, list):
            agents_section.extend(top_level_agents)

        catalog_agents = catalog.get("agents")
        if isinstance(catalog_agents, list):
            agents_section.extend(catalog_agents)

        aggregated: Dict[str, Dict[str, Any]] = {}
        ordered_names: List[str] = []

        for entry in agents_section:
            if not isinstance(entry, dict) or not entry:
                continue
            name, payload = next(iter(entry.items()))
            payload = dict(payload or {})
            aggregated[name] = payload
            if name not in ordered_names:
                ordered_names.append(name)

        for name, payload in self._load_agent_workflows().items():
            existing = aggregated.get(name)
            if existing:
                merged = _deep_merge(dict(existing), payload)
                aggregated[name] = merged
            else:
                aggregated[name] = dict(payload)
            if name not in ordered_names:
                ordered_names.append(name)

        catalog["agents"] = [{name: aggregated[name]} for name in ordered_names if name in aggregated]

        for name in ordered_names:
            payload = aggregated.get(name)
            if payload is None:
                continue
            label = payload.get("label")
            if not label:
                label = payload.get("metadata", {}).get("label") or payload.get("name")
            if not label:
                label = payload.get("description")
            if not label:
                label = _humanize_identifier(name)
            payload["label"] = label
            model_settings = payload.get("model_settings")
            workflow_section = payload.get("workflow") if isinstance(payload.get("workflow"), dict) else {}
            if not model_settings and isinstance(workflow_section, dict):
                model_settings = workflow_section.get("model_settings")
            if isinstance(workflow_section, dict) and "model_settings" in workflow_section:
                workflow_section = dict(workflow_section)
                workflow_section.pop("model_settings", None)
                payload["workflow"] = workflow_section
            spec = AgentSpec(
                name=name,
                label=label,
                description=payload.get("description", ""),
                system_instructions=payload.get("system_instructions"),
                assistant_instructions=payload.get("assistant_instructions"),
                model_settings=model_settings or {},
                workflow=payload.get("workflow", {}) or {},
            )
            spec.steps = list(_build_steps(payload.get("workflow", {})))
            self.agents[name] = spec
        if not self.entrypoint_agent and self.agents:
            self.entrypoint_agent = next(iter(self.agents))

    def _discover_resources(self) -> None:
        tools_root = self.path / "tools"
        self._register_tools(tools_root, scope="global")
        for agent_dir in self._iter_agent_directories():
            agent_tools = agent_dir / "tools"
            if agent_tools.exists():
                self._register_tools(agent_tools, scope=f"agent:{agent_dir.name}")

    def _iter_agent_directories(self) -> Iterator[Path]:
        seen: set[Path] = set()
        agents_root = self.path / "agents"
        if agents_root.exists():
            for candidate in agents_root.iterdir():
                if candidate.is_dir():
                    resolved = candidate.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        yield candidate
        for candidate in self.path.iterdir():
            if not candidate.is_dir():
                continue
            if candidate.name in {"agents", "tools", "plugins", "__pycache__"}:
                continue
            if not ((candidate / "workflow.yaml").exists() or (candidate / "agent.py").exists()):
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield candidate

    def _load_agent_workflows(self) -> Dict[str, Dict[str, Any]]:
        definitions: Dict[str, Dict[str, Any]] = {}
        for agent_dir in self._iter_agent_directories():
            workflow_file = agent_dir / "workflow.yaml"
            if not workflow_file.exists():
                continue
            payload = load_yaml(workflow_file) or {}
            if not isinstance(payload, dict):
                continue
            definitions[agent_dir.name] = payload
        return definitions

    def _register_tools(self, root: Path, scope: str) -> None:
        interactions = root / "interactions"
        if interactions.exists():
            for metadata_file in interactions.rglob("metadata.yaml"):
                spec = _build_tool_spec(metadata_file, "interaction", scope)
                self.tools[spec.name] = spec
        callbacks_root = root / "callbacks"
        if callbacks_root.exists():
            for metadata_file in callbacks_root.rglob("metadata.yaml"):
                relative_parts = metadata_file.relative_to(callbacks_root).parts
                event_channel = sanitize_tool_name(relative_parts[0]) if relative_parts else None
                spec = _build_tool_spec(metadata_file, "callback", scope, event_channel=event_channel)
                self.callbacks[spec.name] = spec

    def _augment_metadata(self) -> None:
        metadata = self.workflow.setdefault("metadata", {})
        discovered = metadata.setdefault("discovered", {})
        discovered["agents"] = sorted(_discover_agent_modules(self.path))
        discovered["tools"] = sorted(_discover_tool_modules(self.path))


def _build_steps(workflow_payload: Dict[str, Any]) -> Iterator[StepSpec]:
    steps = workflow_payload.get("steps") if isinstance(workflow_payload, dict) else []
    for entry in steps or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("step_name") or entry.get("name") or "step"
        instructions = entry.get("instructions")
        tools = _normalize_tool_list(entry.get("tools"))
        agent_tools = _normalize_tool_list(entry.get("agentTools") or entry.get("agent_tools"))
        # Maintain compatibility with agent declarations embedded within "tools"
        carry_over: List[Dict[str, Any]] = []
        remaining_tools: List[Dict[str, Any]] = []
        for tool_entry in tools:
            tool_type = str(tool_entry.get("type") or tool_entry.get("kind") or "").lower()
            if tool_type == "agent":
                tool_entry["type"] = "agent_tool"
                carry_over.append(tool_entry)
            else:
                remaining_tools.append(tool_entry)
        agent_tools = carry_over + agent_tools
        agents = _normalize_agent_list(entry.get("agents"))
        normalized_agents: List[Dict[str, Any]] = []
        promoted_agent_tools: List[Dict[str, Any]] = []
        for agent_entry in agents:
            agent_type = _resolve_agent_type(agent_entry)
            agent_entry["type"] = agent_type
            if agent_type == "agent_tool":
                promoted = dict(agent_entry)
                promoted.setdefault("agent", promoted.get("name"))
                if not promoted.get("name"):
                    promoted["name"] = promoted.get("alias") or promoted.get("agent")
                promoted_agent_tools.append(promoted)
            else:
                normalized_agents.append(agent_entry)
        if promoted_agent_tools:
            agent_tools.extend(promoted_agent_tools)
        callbacks = normalize_callbacks(entry.get("callbacks"))
        label = entry.get("label")
        if not label and isinstance(instructions, str):
            first_line = instructions.strip().splitlines()[0] if instructions.strip() else ""
            label = first_line or None
        if not label:
            label = _humanize_identifier(name)
        entry["label"] = label
        yield StepSpec(
            name=name,
            instructions=instructions,
            label=label,
            tools=remaining_tools,
            agent_tools=agent_tools,
            agents=normalized_agents,
            callbacks=callbacks,
        )


def _normalize_tool_list(entries: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not entries:
        return normalized
    if isinstance(entries, dict):
        entries = [entries]
    for entry in entries:
        if isinstance(entry, str):
            tool_name, method = (entry.split(".", 1) + [None])[:2]
            normalized.append({"name": tool_name.strip(), "method": method})
            continue
        if isinstance(entry, dict):
            payload = dict(entry)
            payload.setdefault("name", payload.get("tool"))
            payload.setdefault("method", payload.get("function"))
            normalized.append(payload)
    return normalized


def _normalize_agent_list(entries: Any) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    if not entries:
        return result
    if isinstance(entries, (str, dict)):
        entries = [entries]
    for entry in entries:
        if isinstance(entry, str):
            result.append({"name": entry, "type": "automatic"})
        elif isinstance(entry, dict):
            payload = dict(entry)
            payload.setdefault("name", payload.get("agent"))
            payload.setdefault("type", payload.get("agent_type"))
            result.append(payload)
    return result


def _resolve_agent_type(entry: Dict[str, Any]) -> str:
    raw = str(entry.get("type") or entry.get("agent_type") or "automatic").strip().lower()
    if raw not in {"agent_transfer", "agent_tool", "automatic"}:
        raw = "automatic"
    if raw == "automatic":
        # Heuristic: explicit payload implies tool semantics.
        for key in ("input", "args", "alias", "skip_summarization", "handoff_payload"):
            if entry.get(key):
                return "agent_tool"
        return "agent_transfer"
    return raw


_UNION_ORIGINS: set[Any] = {Union}
_union_type = getattr(types, "UnionType", None)
if _union_type is not None:
    _UNION_ORIGINS.add(_union_type)


def _annotation_allows_none(annotation: Any) -> bool:
    if annotation is inspect.Signature.empty:
        return False
    if annotation is None:
        return True
    if annotation is type(None):
        return True
    origin = get_origin(annotation)
    if origin in _UNION_ORIGINS:
        return any(_annotation_allows_none(arg) for arg in get_args(annotation))
    return annotation is type(None)


def _schema_from_dataclass(cls: type) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for field in dataclasses.fields(cls):
        schema = _python_type_to_schema(field.type)
        if schema:
            properties[field.name] = schema
        if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
            required.append(field.name)
    schema: Dict[str, Any] = {"type": "OBJECT"}
    if properties:
        schema["properties"] = properties
    if required:
        schema["required"] = required
    return schema


def _python_type_to_schema(annotation: Any) -> Optional[Dict[str, Any]]:
    if annotation in (inspect.Signature.empty, None):
        return None
    if annotation is Any:
        return {"type": "OBJECT"}
    if annotation is type(None):
        return None
    origin = get_origin(annotation)
    if origin in _UNION_ORIGINS:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if not args:
            return None
        if len(args) == 1:
            return _python_type_to_schema(args[0])
        return {"type": "OBJECT"}
    if origin in {list, List, Iterable, tuple, Tuple, set, frozenset}:
        args = get_args(annotation)
        items_schema = _python_type_to_schema(args[0]) if args else None
        schema: Dict[str, Any] = {"type": "ARRAY"}
        if items_schema:
            schema["items"] = items_schema
        return schema
    if origin in {dict, Dict, Mapping, MutableMapping}:
        return {"type": "OBJECT"}
    if origin is Literal:
        values = list(get_args(annotation))
        if not values:
            return None
        base_schema = _python_type_to_schema(type(values[0])) or {"type": "STRING"}
        base_schema["enum"] = values
        return base_schema
    if inspect.isclass(annotation):
        if issubclass(annotation, str):
            return {"type": "STRING"}
        if issubclass(annotation, bool):
            return {"type": "BOOLEAN"}
        if issubclass(annotation, int):
            return {"type": "INTEGER"}
        if issubclass(annotation, float):
            return {"type": "NUMBER"}
        if issubclass(annotation, enum.Enum):
            return {"type": "STRING", "enum": [member.value for member in annotation]}
        if dataclasses.is_dataclass(annotation):
            return _schema_from_dataclass(annotation)
        if hasattr(annotation, "__annotations__") and hasattr(annotation, "__mro__") and dict in annotation.__mro__:
            return {"type": "OBJECT"}
    return {"type": "OBJECT"}


def _build_input_schema_from_signature(signature: inspect.Signature) -> Optional[Dict[str, Any]]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for name, param in signature.parameters.items():
        if name in {"self", "cls"}:
            continue
        if name in {"state", "tool_context", "toolContext"}:
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        schema = _python_type_to_schema(param.annotation) or {"type": "OBJECT"}
        properties[name] = schema
        is_required = param.default is inspect.Parameter.empty and not _annotation_allows_none(param.annotation)
        if is_required:
            required.append(name)
    if not properties:
        return None
    schema: Dict[str, Any] = {"type": "OBJECT", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _build_tool_spec(metadata_file: Path, kind: str, scope: str, event_channel: Optional[str] = None) -> ToolSpec:
    meta = load_yaml(metadata_file)
    metadata_section = meta.setdefault("metadata", {})
    name = sanitize_tool_name(metadata_section.get("name") or metadata_file.parent.name)
    label = metadata_section.get("label")
    if not label:
        label = metadata_section.get("display_name") or metadata_section.get("name")
    if not label:
        label = _humanize_identifier(metadata_file.parent.name)
    metadata_section["label"] = label
    module_name = "tool.py" if kind == "interaction" else "callback.py"
    module_path = metadata_file.with_name(module_name)
    if not module_path.exists():
        module_path = None
    return ToolSpec(
        name=name,
        label=label,
        kind=kind,
        scope=scope,
        metadata=meta,
        module_path=module_path,
        event_channel=event_channel,
    )


def _discover_agent_modules(solution_path: Path) -> List[str]:
    candidates: set[str] = set()
    patterns = ("agents.py", "agents/**/*.py", "**/agent.py")
    for root in _resolve_code_search_roots(solution_path, AGENT_CODE_ENV):
        if not root.exists():
            continue
        for pattern in patterns:
            for file in root.glob(pattern):
                if not file.is_file():
                    continue
                try:
                    record = str(file.relative_to(solution_path))
                except ValueError:
                    record = str(file.resolve())
                candidates.add(record)
    return sorted(candidates)


def _discover_tool_modules(solution_path: Path) -> List[str]:
    candidates: set[str] = set()
    patterns = ("tools/**/*.py",)
    for root in _resolve_code_search_roots(solution_path, TOOL_CODE_ENV):
        if not root.exists():
            continue
        for pattern in patterns:
            for file in root.glob(pattern):
                if not file.is_file():
                    continue
                try:
                    record = str(file.relative_to(solution_path))
                except ValueError:
                    record = str(file.resolve())
                candidates.add(record)
    return sorted(candidates)


def _instantiate_with_optional_metadata(factory: Callable[..., Any], metadata: Dict[str, Any]) -> Any:
    try:
        return factory(metadata)
    except TypeError:
        return factory()


class WorkflowInterpreter:
    def __init__(self, workflow_path: Path, root: Path):
        self.workflow_path = workflow_path
        self.root = root

    def load(self) -> Dict[str, Any]:
        payload = load_yaml(self.workflow_path)
        base: Dict[str, Any] = {}
        for parent in _workflow_parent_chain(self.workflow_path, self.root):
            base = _deep_merge(base, load_yaml(parent))
        return _deep_merge(base, payload)


# --------------------------------------------------------------------------- #
# Runtime execution
# --------------------------------------------------------------------------- #


class RuntimeToolError(RuntimeError):
    pass


class RuntimeCallbackError(RuntimeError):
    pass


def _resolve_awaitable(awaitable: Any) -> Any:
    if not inspect.isawaitable(awaitable):
        return awaitable

    if inspect.iscoroutine(awaitable):
        coroutine = awaitable
    else:
        async def _await_wrapper() -> Any:
            return await awaitable  # type: ignore[func-returns-value]

        coroutine = _await_wrapper()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    return loop.create_task(coroutine)


def invoke_tool(instance: Any, method_name: str, args: Dict[str, Any], state: Dict[str, Any]) -> Any:
    method = getattr(instance, method_name, None)
    if method is None:
        raise AttributeError(f"Tool '{instance}' has no method '{method_name}'")
    if inspect.ismethod(method) or inspect.isfunction(method):
        params = inspect.signature(method).parameters
        call_args = dict(args)
        if "state" in params and "state" not in call_args:
            call_args["state"] = state
        required: List[str] = []
        for name, param in params.items():
            if name in {"self", "cls"}:
                continue
            if name == "state":
                continue
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            if param.default is inspect.Parameter.empty and name not in call_args:
                required.append(name)
        if required:
            raise RuntimeToolError(
                "Parâmetros obrigatórios ausentes: " + ", ".join(sorted(required))
            )
        try:
            result = method(**call_args)
            if inspect.iscoroutinefunction(method) or inspect.isawaitable(result):
                return _resolve_awaitable(result)
            return result
        except TypeError as exc:
            raise RuntimeToolError(str(exc)) from exc
    raise AttributeError(f"Tool method '{method_name}' is not callable")


def invoke_callback(instance: Any, event: str, payload: Dict[str, Any], state: Dict[str, Any]) -> Any:
    handler = getattr(instance, event, None)
    if callable(handler):
        result = handler(payload, state)
        if inspect.iscoroutinefunction(handler) or inspect.isawaitable(result):
            return _resolve_awaitable(result)
        return result
    handler = getattr(instance, "handle_event", None)
    if callable(handler):
        result = handler(event, payload, state)
        if inspect.iscoroutinefunction(handler) or inspect.isawaitable(result):
            return _resolve_awaitable(result)
        return result
    raise AttributeError(f"Callback '{instance}' cannot handle event '{event}'")


@dataclass
class StepExecution:
    step: StepSpec
    agent: AgentSpec


class SolutionRuntime:
    def __init__(self, descriptor: SolutionDescriptor, payload: Optional[Dict[str, Any]] = None, event_bus: Optional[RuntimeEventBus] = None):
        self.descriptor = descriptor
        self.payload = payload or {}
        if event_bus is None:
            self.event_bus = RuntimeEventBus(
                _load_runtime_plugins(search_root=self.descriptor.path)
            )
        else:
            self.event_bus = event_bus
            if not _event_bus_has_plugin(self.event_bus, RUNTIME_LOGGING_PLUGIN_NAME):
                plugin = _instantiate_builtin_plugin_by_name(RUNTIME_LOGGING_PLUGIN_NAME)
                if plugin:
                    self.event_bus.register(plugin)
        raw_session_id = _resolve_session_id(self.payload)
        provided_state = self.payload.get("state")
        if raw_session_id is None and isinstance(provided_state, dict):
            raw_session_id = _resolve_session_id(provided_state)
        if raw_session_id is None:
            sessions_payload = self.payload.get(SESSION_REGISTRY_KEY)
            if isinstance(sessions_payload, dict) and sessions_payload:
                raw_session_id = next(iter(sessions_payload.keys()))
        self.session_id = raw_session_id or str(uuid.uuid4())
        self._persist_session = bool(self.payload.get("persist_session"))
        self._finalized = False
        if isinstance(provided_state, dict) and SESSION_REGISTRY_KEY in provided_state:
            root_state = provided_state
        elif isinstance(provided_state, dict):
            root_state = {SESSION_REGISTRY_KEY: {self.session_id: provided_state}}
        else:
            root_state = {}
        extra_sessions = self.payload.get(SESSION_REGISTRY_KEY)
        if isinstance(extra_sessions, dict):
            registry = root_state.setdefault(SESSION_REGISTRY_KEY, {})
            for sid, value in extra_sessions.items():
                if not isinstance(value, dict):
                    continue
                existing = registry.get(sid)
                if isinstance(existing, dict):
                    _deep_merge(existing, value)
                    value = existing
                registry[sid] = value
                _session_registry_store(sid, value, pinned=True)
        registry = root_state.setdefault(SESSION_REGISTRY_KEY, {})
        self.state = registry.setdefault(self.session_id, {})
        if not isinstance(self.state, dict):
            self.state = {}
            registry[self.session_id] = self.state
        cached_state = _session_registry_get(self.session_id)
        if isinstance(cached_state, dict) and cached_state is not self.state:
            _deep_merge(cached_state, self.state)
            self.state = cached_state
            registry[self.session_id] = self.state
        self.state.setdefault("session_id", self.session_id)
        _session_registry_store(self.session_id, self.state, pinned=self._persist_session)
        self.sessions = registry
        self._root_state = root_state
        reserved = {
            "state",
            SESSION_REGISTRY_KEY,
            "session",
            "session_id",
            "sessionId",
            "sessionID",
            "persist_session",
        }
        for key, value in self.payload.items():
            if key in reserved:
                continue
            self.state.setdefault(key, value)

    # ------------------------------------------------------------------ #
    def run(self, agent_name: Optional[str] = None) -> Dict[str, Any]:
        try:
            agent_key = agent_name or self.descriptor.entrypoint_agent
            if not agent_key:
                raise KeyError("No entrypoint agent configured for solution")
            agent = self.descriptor.agents.get(agent_key)
            if not agent:
                raise KeyError(f"Agent '{agent_key}' not found in solution '{self.descriptor.name}'")
            agent_label = agent.label or _humanize_identifier(agent.name)
            logger.info("%s Executando agente '%s'", ICON_AGENT, agent_label)
            self.event_bus.emit(
                "agent.start",
                agent.name,
                {
                    "solution": self.descriptor.name,
                    "session_id": self.session_id,
                    "agent": agent.name,
                    "agent_label": agent_label,
                },
            )
            for step in agent.steps:
                self._execute_step(StepExecution(step=step, agent=agent))
            self.event_bus.emit(
                "agent.end",
                agent.name,
                {
                    "solution": self.descriptor.name,
                    "session_id": self.session_id,
                    "agent": agent.name,
                    "agent_label": agent_label,
                },
            )
            return self.state
        finally:
            self._finalize_session()

    async def run_async(self, agent_name: Optional[str] = None) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.run(agent_name=agent_name))

    # ------------------------------------------------------------------ #
    def _execute_step(self, execution: StepExecution) -> None:
        step = execution.step
        agent_label = execution.agent.label or _humanize_identifier(execution.agent.name)
        step_label = step.label or _humanize_identifier(step.name)
        self.event_bus.emit(
            "step.start",
            execution.agent.name,
            {
                "step": step.name,
                "step_label": step_label,
                "instructions": step.instructions,
                "session_id": self.session_id,
                "agent": execution.agent.name,
                "agent_label": agent_label,
            },
        )
        if step.instructions:
            self.state.setdefault("journal", []).append({"step": step.name, "instructions": step.instructions})
        self._run_tools(execution)
        self._run_agents(execution)
        self.event_bus.emit(
            "step.end",
            execution.agent.name,
            {
                "step": step.name,
                "step_label": step_label,
                "session_id": self.session_id,
                "agent": execution.agent.name,
                "agent_label": agent_label,
            },
        )

    def _run_tools(self, execution: StepExecution) -> None:
        step = execution.step
        agent_name = execution.agent.name
        agent_label = execution.agent.label or _humanize_identifier(agent_name)
        step_label = step.label or _humanize_identifier(step.name)
        for entry in step.tools:
            tool_name = entry.get("name")
            method_name = entry.get("method") or "run"
            if not tool_name:
                continue
            lookup = sanitize_tool_name(tool_name)
            spec = self.descriptor.tools.get(lookup)
            if not spec:
                logger.warning("%s Tool '%s' não encontrado", ICON_TOOL, tool_name)
                continue
            instance = spec.ensure_instance()
            if instance is None:
                raise RuntimeToolError(f"Tool '{tool_name}' has no implementation")
            args = resolve_placeholders(entry.get("input") or entry.get("args") or {}, self.state)
            tool_label = spec.label or _humanize_identifier(spec.name)
            self.event_bus.emit(
                "tool.before",
                spec.name,
                {
                    "step": step.name,
                    "step_label": step_label,
                    "method": method_name,
                    "session_id": self.session_id,
                    "args": args,
                    "agent": agent_name,
                    "agent_label": agent_label,
                    "tool": spec.name,
                    "tool_label": tool_label,
                },
            )
            try:
                result = invoke_tool(instance, method_name, args, self.state)
            except RuntimeToolError as exc:
                exc_details = _exception_details(exc)
                error_payload = {
                    "step": step.name,
                    "step_label": step_label,
                    "method": method_name,
                    "session_id": self.session_id,
                    "error": exc_details["message"],
                    "agent": agent_name,
                    "agent_label": agent_label,
                    "tool": spec.name,
                    "tool_label": tool_label,
                    **exc_details,
                }
                self.event_bus.emit("tool.error", spec.name, error_payload)
                error_result = {
                    "error": exc_details["message"],
                }
                if exc_details.get("details"):
                    error_result["details"] = exc_details["details"]
                if exc_details.get("stacktrace"):
                    error_result["stacktrace"] = exc_details["stacktrace"]
                state_key = f"{spec.name}:{method_name}"
                self.state[state_key] = error_result
                self._emit_callbacks(
                    "tool_error",
                    step.callbacks,
                    {
                        "tool": spec.name,
                        "method": method_name,
                        "error": exc_details["message"],
                        "details": exc_details.get("details"),
                        "stacktrace": exc_details.get("stacktrace"),
                        "agent": agent_name,
                    },
                )
                continue
            except Exception as exc:  # pragma: no cover - bubbled to caller
                exc_details = _exception_details(exc)
                error_payload = {
                    "step": step.name,
                    "method": method_name,
                    "session_id": self.session_id,
                    "error": exc_details["message"],
                    "agent": agent_name,
                    "tool": spec.name,
                    **exc_details,
                }
                self.event_bus.emit("tool.error", spec.name, error_payload)
                self._emit_callbacks(
                    "tool_error",
                    step.callbacks,
                    {
                        "tool": spec.name,
                        "method": method_name,
                        "error": exc_details["message"],
                        "details": exc_details.get("details"),
                        "stacktrace": exc_details.get("stacktrace"),
                        "agent": agent_name,
                    },
                )
                raise RuntimeToolError(f"Error executing tool '{tool_name}': {exc}") from exc
            self.event_bus.emit(
                "tool.after",
                spec.name,
                {
                    "step": step.name,
                    "step_label": step_label,
                    "method": method_name,
                    "result": result,
                    "session_id": self.session_id,
                    "agent": agent_name,
                    "agent_label": agent_label,
                    "tool": spec.name,
                    "tool_label": tool_label,
                },
            )
            state_key = f"{spec.name}:{method_name}"
            self.state[state_key] = result
            self._emit_callbacks("after_tool_execution", step.callbacks, {
                "tool": spec.name,
                "tool_label": tool_label,
                "method": method_name,
                "result": result,
                "agent": agent_name,
                "agent_label": agent_label,
            })

    def _run_agents(self, execution: StepExecution) -> None:
        step = execution.step
        parent_agent = execution.agent.name
        parent_label = execution.agent.label or _humanize_identifier(parent_agent)
        step_label = step.label or _humanize_identifier(step.name)

        def _iter_agent_entries() -> Iterator[Tuple[str, Dict[str, Any]]]:
            for entry in step.agents:
                agent_name = entry.get("name") or entry.get("agent")
                if not agent_name:
                    continue
                yield agent_name, entry
            for entry in step.agent_tools:
                agent_name = entry.get("agent") or entry.get("name")
                if not agent_name:
                    continue
                yield agent_name, entry

        for agent_name, entry in _iter_agent_entries():
            child = self.descriptor.agents.get(agent_name)
            if not child:
                logger.warning("%s Sub agente '%s' não encontrado", ICON_AGENT, agent_name)
                continue
            child_label = child.label or _humanize_identifier(child.name)
            self.event_bus.emit(
                "agent.before",
                child.name,
                {
                    "step": step.name,
                    "step_label": step_label,
                    "session_id": self.session_id,
                    "parent_agent": parent_agent,
                    "parent_agent_label": parent_label,
                    "agent": child.name,
                    "agent_label": child_label,
                    "metadata": {key: entry.get(key) for key in entry if key != "agent"},
                },
            )
            runtime = SolutionRuntime(self.descriptor, {"state": self._root_state}, self.event_bus)
            runtime.state = self.state
            runtime.sessions = self.sessions
            runtime.session_id = self.session_id
            runtime._root_state = self._root_state
            runtime.run(agent_name=child.name)
            self.event_bus.emit(
                "agent.after",
                child.name,
                {
                    "step": step.name,
                    "step_label": step_label,
                    "session_id": self.session_id,
                    "parent_agent": parent_agent,
                    "parent_agent_label": parent_label,
                    "agent": child.name,
                    "agent_label": child_label,
                },
            )

    def _emit_callbacks(self, event: str, callbacks: Dict[str, List[str]], payload: Dict[str, Any]) -> None:
        for callback_name in callbacks.get(event, []):
            lookup = sanitize_tool_name(callback_name)
            spec = self.descriptor.callbacks.get(lookup)
            if not spec:
                logger.warning("%s Callback '%s' não encontrado", ICON_CALLBACK, callback_name)
                continue
            instance = spec.ensure_instance()
            if instance is None:
                raise RuntimeCallbackError(f"Callback '{callback_name}' missing implementation")
            callback_label = spec.label or _humanize_identifier(spec.name)
            self.event_bus.emit(
                "callback.before",
                spec.name,
                {
                    "event": event,
                    "payload": payload,
                    "session_id": self.session_id,
                    "callback": spec.name,
                    "callback_label": callback_label,
                },
            )
            try:
                response = invoke_callback(instance, event, payload, self.state)
            except Exception as exc:  # pragma: no cover - bubbled to caller
                self.event_bus.emit(
                    "callback.error",
                    spec.name,
                    {
                        "event": event,
                        "error": repr(exc),
                        "session_id": self.session_id,
                        "callback": spec.name,
                        "callback_label": callback_label,
                    },
                )
                raise RuntimeCallbackError(f"Callback '{callback_name}' failed: {exc}") from exc
            if response:
                self.state.setdefault("callback_responses", []).append({"callback": spec.name, "response": response})
            self.event_bus.emit(
                "callback.after",
                spec.name,
                {
                    "event": event,
                    "response": response,
                    "session_id": self.session_id,
                    "callback": spec.name,
                    "callback_label": callback_label,
                },
            )

    def _finalize_session(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        if self._persist_session:
            _session_registry_store(self.session_id, self.state, pinned=True)
            return
        _session_registry_remove(self.session_id)


# --------------------------------------------------------------------------- #
# Solution discovery and runtime facade
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Solution bootstrap helpers
# --------------------------------------------------------------------------- #


class SolutionBootstrapError(RuntimeError):
    """Raised when automatic solution bootstrap cannot resolve entrypoints."""


@dataclass
class StandaloneSolutionApp:
    """Lightweight representation of a Google ADK app.

    This object is returned when the host environment does not provide the
    ``google-adk`` package.  It mirrors the minimum surface required by the ADK
    templates (exposing a ``root_agent`` attribute) so tests and local
    invocations remain functional without the optional dependency.
    """

    name: str
    root_agent: str
    descriptor: "SolutionDescriptor"

    def __repr__(self) -> str:  # pragma: no cover - trivial representation
        return f"<StandaloneSolutionApp name={self.name!r} root_agent={self.root_agent!r}>"


def locate_solution_root(module_file: Union[str, os.PathLike[str]]) -> Path:
    """Return the solution root associated with ``module_file``."""

    path = Path(module_file).resolve()

    def _has_solution_markers(directory: Path) -> bool:
        if not directory.exists():
            return False
        return (directory / "runtime.yaml").exists() or (directory / "workflow.yaml").exists()

    def _iter_child_solution_dirs(directory: Path) -> List[Path]:
        matches: List[Path] = []
        try:
            for child in directory.iterdir():
                if not child.is_dir():
                    continue
                if _has_solution_markers(child):
                    matches.append(child)
        except FileNotFoundError:
            return []
        if len(matches) <= 1:
            return matches
        preferred_order: List[Path] = []
        reference_names = []
        if path.is_dir():
            reference_names.append(path.name)
        else:
            reference_names.append(path.parent.name)
        reference_names.append("app")
        for name in reference_names:
            for candidate in matches:
                if candidate.name == name and candidate not in preferred_order:
                    preferred_order.append(candidate)
        for candidate in matches:
            try:
                if path.is_relative_to(candidate) and candidate not in preferred_order:
                    preferred_order.append(candidate)
            except ValueError:
                continue
        for candidate in matches:
            if candidate not in preferred_order:
                preferred_order.append(candidate)
        return preferred_order

    candidates = [path] + list(path.parents)
    for candidate in candidates:
        if candidate.is_file():
            continue
        if _has_solution_markers(candidate):
            return candidate
        for child in _iter_child_solution_dirs(candidate):
            if _has_solution_markers(child):
                return child
    raise SolutionBootstrapError(
        "Não foi possível localizar 'runtime.yaml' ou 'workflow.yaml' para determinar a solução."
    )


def _iter_default_agent_module_candidates(package_root: Path, solution_root: Path) -> List[str]:
    candidates: List[str] = []

    if (package_root / "agent.py").exists():
        candidates.append("agent")

    try:
        relative_parts = solution_root.relative_to(package_root).parts
    except ValueError:
        relative_parts = ()

    if relative_parts:
        candidate = ".".join(relative_parts + ("agent",))
        if (solution_root / "agent.py").exists():
            candidates.append(candidate)

    if (package_root / "app" / "agent.py").exists():
        candidates.append("app.agent")

    if not candidates:
        candidates = ["agent", "app.agent"]

    seen: set[str] = set()
    ordered: List[str] = []
    for entry in candidates:
        if entry in seen:
            continue
        seen.add(entry)
        ordered.append(entry)
    return ordered


def _register_agent_module_alias(
    package_name: str,
    module: ModuleType,
    relative_name: str,
) -> None:
    """Expose the loaded module under canonical agent import paths."""

    canonical_name = f"{package_name}.agent"
    module_name = module.__name__

    if canonical_name not in sys.modules:
        sys.modules[canonical_name] = module
    elif sys.modules[canonical_name] is not module:
        sys.modules[canonical_name] = module

    qualified_name = f"{package_name}.{relative_name}" if relative_name else module_name
    if qualified_name and sys.modules.get(qualified_name) is not module:
        sys.modules[qualified_name] = module


def load_solution_app_module(
    package_name: str,
    module_file: Union[str, os.PathLike[str]],
    *,
    candidates: Optional[Iterable[str]] = None,
) -> ModuleType:
    """Import and return the module that exports the ADK application."""

    module_path = Path(module_file).resolve()
    package_root = module_path if module_path.is_dir() else module_path.parent
    solution_root = locate_solution_root(module_file)
    candidate_modules = list(
        candidates or _iter_default_agent_module_candidates(package_root, solution_root)
    )
    last_error: Optional[Exception] = None
    for relative_name in candidate_modules:
        try:
            module = import_module(f".{relative_name}", package_name)
            _register_agent_module_alias(package_name, module, relative_name)
            return module
        except ModuleNotFoundError as exc:  # pragma: no cover - fallback path
            last_error = exc
    if last_error is not None:  # pragma: no cover - defensive branch
        raise SolutionBootstrapError(str(last_error)) from last_error
    raise SolutionBootstrapError(
        "Nenhum módulo de agente encontrado para a solução; verifique a estrutura do pacote."
    )


def bootstrap_solution_entrypoints(
    module_file: Union[str, os.PathLike[str]],
    *,
    solution_name: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> Tuple[Any, Any, Callable[[Optional[Dict[str, Any]]], Dict[str, Any]]]:
    """Build Google ADK entrypoints for the solution associated with ``module_file``."""

    module_path = Path(module_file).resolve()
    package_root = module_path if module_path.is_dir() else module_path.parent
    solution_root = locate_solution_root(module_file)
    runtime_root = package_root if solution_root.is_relative_to(package_root) else solution_root

    runtime = DynamicAgentRuntime(runtime_root)

    candidate_names: List[str] = []
    if solution_name:
        candidate_names.append(solution_name)
    candidate_names.append(solution_root.name)
    package_name = package_root.name
    if package_name not in candidate_names:
        candidate_names.append(package_name)

    descriptor: SolutionDescriptor
    resolved_solution_name: str
    descriptor = None  # type: ignore[assignment]
    resolved_solution_name = ""
    for candidate in candidate_names:
        try:
            descriptor = runtime.get_solution(candidate)
        except KeyError:
            continue
        resolved_solution_name = descriptor.name
        break
    if descriptor is None:
        descriptor = runtime.get_solution()
        resolved_solution_name = descriptor.name

    def _is_google_adk_missing(error: RuntimeError) -> bool:
        cause = error.__cause__
        if isinstance(cause, ImportError):
            missing = getattr(cause, "name", "") or ""
            if missing.startswith("google"):
                return True
        return "Google ADK" in str(error)

    try:
        app = runtime.build_adk_app(resolved_solution_name)
        root_agent = getattr(app, "root_agent")
    except RuntimeError as exc:
        if not _is_google_adk_missing(exc):
            raise
        if not descriptor.entrypoint_agent:
            raise SolutionBootstrapError(
                "Solução não possui agente de entrada configurado; instale `google-adk` para criar o App."
            ) from exc
        root_agent_name = descriptor.entrypoint_agent
        app = StandaloneSolutionApp(
            name=resolved_solution_name,
            root_agent=root_agent_name,
            descriptor=descriptor,
        )
        root_agent = app.root_agent

    def _default_agent_name() -> str:
        if agent_name:
            return agent_name
        parent = module_path.parent
        if parent in (solution_root, package_root):
            return descriptor.entrypoint_agent or descriptor.name
        return parent.name

    resolved_agent_name = _default_agent_name()

    def _run(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return runtime.run(resolved_solution_name, agent_name=resolved_agent_name, payload=payload)

    return app, root_agent, _run


class WorkflowDiscovery:
    def __init__(self, root: Path):
        self.root = root

    def iter_solutions(self) -> Iterator[Tuple[str, Path, Path]]:
        for workflow_path in self._iter_workflows():
            solution_name = workflow_path.parent.name
            yield solution_name, workflow_path.parent, workflow_path

    def _iter_workflows(self) -> Iterator[Path]:
        search_paths = _resolve_search_paths(self.root, WORKFLOW_ENV)
        seen: set[Path] = set()
        for base in search_paths:
            for workflow in base.rglob(DEFAULT_WORKFLOW_GLOB):
                if workflow in seen:
                    continue
                seen.add(workflow)
                yield workflow


def _resolve_search_paths(root: Path, env_var: str) -> List[Path]:
    raw = os.getenv(env_var)
    paths: List[Path] = [root]
    if not raw:
        return paths
    for entry in raw.split(os.pathsep):
        candidate = entry.strip()
        if not candidate:
            continue
        resolved = resolve_with_root(root, candidate)
        if resolved not in paths:
            paths.append(resolved)
    return paths


def _resolve_code_search_roots(solution_path: Path, env_var: str) -> List[Path]:
    roots: List[Path] = [solution_path]
    raw = os.getenv(env_var)
    if not raw:
        return roots
    for entry in raw.split(os.pathsep):
        candidate = entry.strip()
        if not candidate:
            continue
        resolved = resolve_with_root(solution_path, candidate)
        if resolved not in roots:
            roots.append(resolved)
    return roots


class DynamicAgentRuntime:
    def __init__(self, root: Path, *, plugins: Optional[Iterable[RuntimePlugin]] = None):
        self.root = Path(root).resolve()
        plugin_instances = _load_runtime_plugins(plugins, search_root=self.root)
        self.event_bus = RuntimeEventBus(plugin_instances)
        self.solutions: Dict[str, SolutionDescriptor] = {}
        self._solution_aliases: Dict[str, str] = {}
        self._discover_solutions()

    # ------------------------------------------------------------------ #
    def _discover_solutions(self) -> None:
        discovery = WorkflowDiscovery(self.root)
        for name, solution_path, workflow_path in discovery.iter_solutions():
            parent = solution_path.parent
            if parent.name == "agents":
                logger.debug(
                    "%s Ignorando workflow aninhado de agente '%s' em %s",
                    ICON_SKIP,
                    name,
                    solution_path,
                )
                continue
            canonical_name = name
            parent_init = parent / "__init__.py"
            if (
                name == "app"
                and parent_init.exists()
                and parent.name not in self.solutions
            ):
                canonical_name = parent.name
            if canonical_name in self.solutions and canonical_name != name:
                logger.warning(
                    "%s Conflito de nome da solução '%s'; mantendo identificador original '%s'",
                    ICON_WARNING,
                    canonical_name,
                    name,
                )
                canonical_name = name
            descriptor = SolutionDescriptor(
                name=canonical_name, path=solution_path, workflow_path=workflow_path
            )
            self.solutions[canonical_name] = descriptor
            if canonical_name != name:
                self._solution_aliases[name] = canonical_name
        logger.info("%s %d solução(ões) encontrada(s)", ICON_READY, len(self.solutions))

    def list_solutions(self) -> List[str]:
        return sorted(self.solutions.keys())

    def get_solution(self, name: Optional[str] = None) -> SolutionDescriptor:
        if not self.solutions:
            raise KeyError("Nenhuma solução disponível")
        solution_name = name or next(iter(self.solutions))
        descriptor = self.solutions.get(solution_name)
        if descriptor is None and solution_name in self._solution_aliases:
            alias = self._solution_aliases[solution_name]
            descriptor = self.solutions.get(alias)
        if descriptor is None:
            raise KeyError(f"Solução '{solution_name}' não encontrada")
        if not descriptor.workflow:
            descriptor.configure(self.root)
        return descriptor

    def run(self, solution_name: Optional[str] = None, agent_name: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        solution = self.get_solution(solution_name)
        runtime = SolutionRuntime(solution, payload, self.event_bus)
        return runtime.run(agent_name=agent_name)

    # ------------------------------------------------------------------ #
    def build_adk_app(self, solution_name: Optional[str] = None):
        try:
            from google.adk.apps.app import App
            from google.adk.agents.llm_agent import LlmAgent
            from google.adk.tools.agent_tool import AgentTool
            from google.adk.tools.base_tool import BaseTool
            from google.adk.tools.tool_context import ToolContext
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Google ADK não está disponível. Instale `google-adk` para gerar o App."
            ) from exc

        solution = self.get_solution(solution_name)
        metadata = solution.workflow.get("metadata") or {}
        app_name = solution.name
        display_name = metadata.get("name")
        if display_name and display_name != app_name:
            logger.warning(
                "App metadata name '%s' diverge do identificador '%s'; usando identificador como nome ADK",
                display_name,
                app_name,
            )
        if not solution.entrypoint_agent:
            raise KeyError("Solução não possui agente de entrada configurado")

        def _normalize_instruction_block(block: Any) -> Optional[str]:
            if block is None:
                return None
            if isinstance(block, str):
                value = textwrap.dedent(block).strip()
                return value or None
            if isinstance(block, list):
                parts = [item for item in (_normalize_instruction_block(entry) for entry in block) if item]
                return "\n".join(parts) if parts else None
            if isinstance(block, dict):
                parts = []
                for key, value in block.items():
                    normalised = _normalize_instruction_block(value)
                    if normalised:
                        parts.append(f"{key}: {normalised}")
                return "\n".join(parts) if parts else None
            value = str(block).strip()
            return value or None

        def _normalise_tool_entry(entry: Any) -> Optional[Dict[str, Any]]:
            if isinstance(entry, str):
                raw = entry.strip()
                if not raw:
                    return None
                if "." in raw:
                    tool_part, method_part = raw.split(".", 1)
                    return {
                        "tool_key": sanitize_tool_name(tool_part),
                        "tool_name": tool_part.strip(),
                        "method_key": sanitize_tool_name(method_part),
                        "method_name": method_part.strip(),
                        "label": raw.strip(),
                    }
                return {"tool_key": sanitize_tool_name(raw), "tool_name": raw, "label": raw}

            if not isinstance(entry, dict):
                return None

            tool_name = entry.get("name") or entry.get("tool")
            method_name = entry.get("method") or entry.get("function")
            normalised = {
                "tool_key": sanitize_tool_name(tool_name),
                "tool_name": tool_name,
                "method_key": sanitize_tool_name(method_name),
                "method_name": method_name,
                "when_to_use": entry.get("when_to_use") or entry.get("whenToUse"),
                "examples": entry.get("examples"),
            }
            if entry.get("label"):
                normalised["label"] = entry["label"]
            if "usage" in entry:
                normalised["usage"] = entry["usage"]
            input_payload = entry.get("input") or entry.get("args")
            if isinstance(input_payload, dict):
                normalised["input"] = input_payload
            return normalised if normalised.get("tool_key") else None

        def _normalise_agent_tool_entry(entry: Any) -> Optional[Dict[str, Any]]:
            if isinstance(entry, str):
                raw = entry.strip()
                if not raw:
                    return None
                return {
                    "agent_key": sanitize_tool_name(raw),
                    "agent_name": raw,
                    "type": "agent_tool",
                    "label": raw,
                    "agent_label": raw,
                }
            if not isinstance(entry, dict):
                return None
            candidate_type = entry.get("type") or entry.get("kind")
            is_agent_tool = isinstance(candidate_type, str) and candidate_type.lower() == "agent"
            agent_name = entry.get("agent") or (entry.get("name") if is_agent_tool else None)
            if not agent_name:
                return None
            normalised: Dict[str, Any] = {
                "agent_key": sanitize_tool_name(agent_name),
                "agent_name": agent_name,
                "type": "agent_tool",
                "when_to_use": entry.get("when_to_use")
                or entry.get("whenToUse")
                or entry.get("description"),
                "skip_summarization": bool(entry.get("skip_summarization")),
            }
            if entry.get("label"):
                normalised["label"] = entry["label"]
                normalised.setdefault("agent_label", entry["label"])
            alias = entry.get("name")
            if alias and alias != agent_name:
                normalised["alias"] = alias
            if "handoff_payload" in entry:
                normalised["handoff_payload"] = entry["handoff_payload"]
            input_payload = entry.get("input") or entry.get("args")
            if isinstance(input_payload, dict):
                normalised["input"] = input_payload
            return normalised if normalised.get("agent_key") else None

        def _normalise_agent_entry(entry: Any) -> Optional[Dict[str, Any]]:
            if isinstance(entry, str):
                raw = entry.strip()
                if not raw:
                    return None
                return {
                    "agent_key": sanitize_tool_name(raw),
                    "agent_name": raw,
                    "type": "agent_transfer",
                    "label": raw,
                    "agent_label": raw,
                }
            if not isinstance(entry, dict):
                return None
            agent_name = entry.get("name") or entry.get("agent")
            agent_type = _resolve_agent_type(entry)
            normalised = {
                "agent_key": sanitize_tool_name(agent_name),
                "agent_name": agent_name,
                "type": agent_type,
                "when_to_use": entry.get("when_to_use") or entry.get("whenToUse"),
                "skip_summarization": bool(entry.get("skip_summarization")),
            }
            if entry.get("label"):
                normalised["label"] = entry["label"]
                normalised.setdefault("agent_label", entry["label"])
            if "handoff_payload" in entry:
                normalised["handoff_payload"] = entry["handoff_payload"]
            if entry.get("alias"):
                normalised["alias"] = entry["alias"]
            if normalised.get("type") == "agent_tool":
                input_payload = entry.get("input") or entry.get("args")
                if isinstance(input_payload, dict):
                    normalised["input"] = input_payload
            return normalised if normalised.get("agent_key") else None

        def _iter_step_entries(step: Dict[str, Any], *keys: str) -> Iterator[Any]:
            for key in keys:
                values = step.get(key)
                if not values:
                    continue
                if isinstance(values, (dict, str)):
                    values = [values]
                for value in values:
                    yield value

        def _collect_declared_tools(agent_spec: AgentSpec) -> Dict[str, set[str]]:
            declared: Dict[str, set[str]] = {}

            def _register(tool_key: Optional[str], method_key: Optional[str]) -> None:
                if not tool_key:
                    return
                declared.setdefault(tool_key, set())
                if method_key:
                    declared[tool_key].add(method_key)

            for step in agent_spec.workflow.get("steps", []) or []:
                for entry in _iter_step_entries(step, "tools", "agentTools", "agent_tools"):
                    if _normalise_agent_tool_entry(entry):
                        continue
                    normalised = _normalise_tool_entry(entry)
                    if not normalised:
                        continue
                    _register(normalised.get("tool_key"), normalised.get("method_key"))
            return declared

        def _collect_declared_sub_agents(agent_spec: AgentSpec) -> List[str]:
            declared: List[str] = []
            seen: set[str] = set()
            for step in agent_spec.workflow.get("steps", []) or []:
                entries = step.get("agents") or []
                if isinstance(entries, (dict, str)):
                    entries = [entries]
                for entry in entries:
                    normalised = _normalise_agent_entry(entry)
                    if not normalised:
                        continue
                    if normalised.get("type") == "agent_tool":
                        continue
                    agent_key = normalised.get("agent_key")
                    if agent_key and agent_key not in seen:
                        seen.add(agent_key)
                        declared.append(agent_key)
                for entry in _iter_step_entries(step, "tools", "agentTools", "agent_tools"):
                    normalised = _normalise_agent_tool_entry(entry)
                    if not normalised:
                        continue
                    agent_key = normalised.get("agent_key")
                    if agent_key and agent_key not in seen:
                        seen.add(agent_key)
                        declared.append(agent_key)
            return declared

        def _collect_tool_directives(agent_spec: AgentSpec) -> Dict[str, Dict[str, Dict[str, Any]]]:
            directives: Dict[str, Dict[str, Dict[str, Any]]] = {}
            for step in agent_spec.workflow.get("steps", []) or []:
                step_name = step.get("step_name") or step.get("name")
                step_label = step.get("label")
                for entry in _iter_step_entries(step, "tools", "agentTools", "agent_tools"):
                    if _normalise_agent_tool_entry(entry):
                        continue
                    normalised = _normalise_tool_entry(entry)
                    if not normalised:
                        continue
                    if step_name and "step" not in normalised:
                        normalised["step"] = step_name
                    if step_label and "step_label" not in normalised:
                        normalised["step_label"] = step_label
                    tool_key = normalised.get("tool_key")
                    method_key = normalised.get("method_key")
                    if not tool_key:
                        continue
                    directives.setdefault(tool_key, {})
                    if method_key:
                        directives[tool_key][method_key] = normalised
            return directives

        def _collect_sub_agent_directives(agent_spec: AgentSpec) -> Dict[str, Dict[str, Any]]:
            directives: Dict[str, Dict[str, Any]] = {}
            for step in agent_spec.workflow.get("steps", []) or []:
                step_label = step.get("label")
                entries = step.get("agents") or []
                if isinstance(entries, (dict, str)):
                    entries = [entries]
                for entry in entries:
                    normalised = _normalise_agent_entry(entry)
                    if not normalised:
                        continue
                    if normalised.get("type") == "agent_tool":
                        continue
                    agent_key = normalised.get("agent_key")
                    if agent_key and agent_key not in directives:
                        if step_label and "step_label" not in normalised:
                            normalised["step_label"] = step_label
                        directives[agent_key] = normalised
                for entry in _iter_step_entries(step, "tools", "agentTools", "agent_tools"):
                    normalised = _normalise_agent_tool_entry(entry)
                    if not normalised:
                        continue
                    agent_key = normalised.get("agent_key")
                    if agent_key and agent_key not in directives:
                        if step_label and "step_label" not in normalised:
                            normalised["step_label"] = step_label
                        directives[agent_key] = normalised
            return directives

        def _collect_agent_tool_entries(agent_spec: AgentSpec) -> List[Dict[str, Any]]:
            entries: Dict[str, Dict[str, Any]] = {}
            for step in agent_spec.workflow.get("steps", []) or []:
                step_name = step.get("step_name") or step.get("name")
                step_label = step.get("label")
                agent_entries = step.get("agents") or []
                if isinstance(agent_entries, (dict, str)):
                    agent_entries = [agent_entries]
                for entry in agent_entries:
                    normalised = _normalise_agent_entry(entry)
                    if not normalised:
                        continue
                    if normalised.get("type") != "agent_tool":
                        continue
                    agent_key = normalised.get("agent_key")
                    if not agent_key:
                        continue
                    if step_name and "step" not in normalised:
                        normalised["step"] = step_name
                    if step_label and "step_label" not in normalised:
                        normalised["step_label"] = step_label
                    current = entries.get(agent_key)
                    if current is None or normalised.get("alias"):
                        entries[agent_key] = normalised
                for entry in _iter_step_entries(step, "tools", "agentTools", "agent_tools"):
                    normalised = _normalise_agent_tool_entry(entry)
                    if not normalised:
                        continue
                    agent_key = normalised.get("agent_key")
                    if not agent_key:
                        continue
                    if step_name and "step" not in normalised:
                        normalised["step"] = step_name
                    if step_label and "step_label" not in normalised:
                        normalised["step_label"] = step_label
                    current = entries.get(agent_key)
                    if current is None or normalised.get("alias"):
                        entries[agent_key] = normalised
            return list(entries.values())

        declared_tool_usage: Dict[str, Dict[str, set[str]]] = {
            name: _collect_declared_tools(spec) for name, spec in solution.agents.items()
        }
        declared_sub_agents: Dict[str, List[str]] = {
            name: _collect_declared_sub_agents(spec) for name, spec in solution.agents.items()
        }
        tool_directives: Dict[str, Dict[str, Dict[str, Any]]] = {
            name: _collect_tool_directives(spec) for name, spec in solution.agents.items()
        }
        sub_agent_directives: Dict[str, Dict[str, Any]] = {
            name: _collect_sub_agent_directives(spec) for name, spec in solution.agents.items()
        }
        agent_tool_directives: Dict[str, List[Dict[str, Any]]] = {
            name: _collect_agent_tool_entries(spec) for name, spec in solution.agents.items()
        }

        sanitized_agent_lookup = {sanitize_tool_name(name): name for name in solution.agents}

        def _to_schema(schema_payload: Optional[Dict[str, Any]]):
            from google.genai import types

            if not schema_payload:
                return types.Schema(type=types.Type.OBJECT)

            schema_type = str(schema_payload.get("type", "OBJECT")).upper()
            type_enum = getattr(types.Type, schema_type, types.Type.OBJECT)
            schema = types.Schema(type=type_enum)
            if "description" in schema_payload:
                schema.description = schema_payload["description"]

            properties = schema_payload.get("properties")
            if isinstance(properties, dict):
                schema.properties = {
                    key: _to_schema(value) for key, value in properties.items()
                }

            required = schema_payload.get("required")
            if isinstance(required, list):
                schema.required = required

            if "items" in schema_payload:
                schema.items = _to_schema(schema_payload["items"])

            enum_values = schema_payload.get("enum")
            if isinstance(enum_values, list):
                schema.enum = enum_values

            return schema

        def _resolve_tool_payload(tool_spec: ToolSpec, method_key: str) -> Tuple[str, Dict[str, Any]]:
            methods = tool_spec.metadata.get("methods") or []
            for entry in methods:
                if isinstance(entry, dict) and entry:
                    method_name, payload = next(iter(entry.items()))
                    if sanitize_tool_name(method_name) == method_key:
                        return method_name, payload or {}
            method_name = method_key or "run"
            return method_name, {}

        def _build_generate_config(payload: Dict[str, Any]):
            if not payload:
                return None
            try:
                from google.genai import types
            except ImportError:  # pragma: no cover - optional dependency
                logger.warning("%s google.genai não disponível; ignorando generate_content_config.", ICON_ENGINE)
                return None

            kwargs: Dict[str, Any] = {}
            for key in (
                "temperature",
                "top_p",
                "top_k",
                "max_output_tokens",
                "candidate_count",
                "presence_penalty",
                "frequency_penalty",
                "response_mime_type",
            ):
                if key in payload:
                    kwargs[key] = payload[key]

            stop_sequences = payload.get("stop_sequences")
            if isinstance(stop_sequences, list):
                kwargs["stop_sequences"] = [str(item) for item in stop_sequences]

            safety_settings = payload.get("safety_settings")
            if isinstance(safety_settings, list):
                entries = []
                for item in safety_settings:
                    if not isinstance(item, dict):
                        continue
                    category = item.get("category")
                    threshold = item.get("threshold")
                    harm_category = getattr(types.HarmCategory, str(category).upper(), None)
                    harm_threshold = getattr(types.HarmBlockThreshold, str(threshold).upper(), None)
                    if harm_category is None or harm_threshold is None:
                        continue
                    entries.append(types.SafetySetting(category=harm_category, threshold=harm_threshold))
                if entries:
                    kwargs["safety_settings"] = entries

            thinking_payload = payload.get("thinking_config")
            if isinstance(thinking_payload, dict):
                thinking_kwargs = {}
                for key in ("include_thoughts", "thinking_budget", "thoughts_per_step"):
                    if key in thinking_payload:
                        thinking_kwargs[key] = thinking_payload[key]
                if thinking_kwargs:
                    kwargs["thinking_config"] = types.ThinkingConfig(**thinking_kwargs)

            if not kwargs:
                return None
            return types.GenerateContentConfig(**kwargs)

        def _build_planner(payload: Dict[str, Any]):
            if not payload:
                return None
            try:
                from google.adk.planners import BuiltInPlanner
                from google.genai import types
            except ImportError:  # pragma: no cover - optional dependency
                logger.warning("%s google.adk planners indisponíveis; ignorando configuração de planner.", ICON_ENGINE)
                return None

            thinking_payload = payload.get("thinking_config")
            thinking_config = None
            if isinstance(thinking_payload, dict):
                thinking_kwargs = {}
                for key in ("include_thoughts", "thinking_budget", "thoughts_per_step"):
                    if key in thinking_payload:
                        thinking_kwargs[key] = thinking_payload[key]
                if thinking_kwargs:
                    thinking_config = types.ThinkingConfig(**thinking_kwargs)
            return BuiltInPlanner(thinking_config=thinking_config)

        event_bus = self.event_bus

        class DynamicAdkTool(BaseTool):
            def __init__(
                self,
                tool_spec: ToolSpec,
                method_name: str,
                method_payload: Dict[str, Any],
                *,
                directive: Optional[Dict[str, Any]] = None,
                event_bus: RuntimeEventBus,
            ):
                directive = directive or {}
                description = (
                    directive.get("when_to_use")
                    or method_payload.get("description")
                    or tool_spec.metadata.get("metadata", {}).get("description")
                    or f"{tool_spec.name}.{method_name}"
                )
                function_name = normalize_function_name(directive.get("alias") or f"{tool_spec.name}_{method_name}")
                if not function_name:
                    function_name = normalize_function_name(tool_spec.name) or "tool"
                metadata: Dict[str, Any] = {
                    "tool": tool_spec.name,
                    "method": method_name,
                }
                for key in ("when_to_use", "examples"):
                    if directive.get(key):
                        metadata[key] = directive[key]
                super().__init__(name=function_name, description=description, custom_metadata=metadata)
                self.tool_spec = tool_spec
                self.method = method_name
                self.method_payload = method_payload or {}
                self._event_bus = event_bus
                self._default_args = dict(directive.get("input", {})) if isinstance(directive.get("input"), dict) else {}
                self._step = directive.get("step")
                self._step_label = directive.get("step_label")
                self._tool_label = directive.get("label") or tool_spec.label or _humanize_identifier(tool_spec.name)
                schema_payload = self.method_payload.get("input_schema") or {}
                properties = schema_payload.get("properties")
                if isinstance(properties, dict):
                    self.parameter_names = list(properties.keys())
                else:
                    self.parameter_names = []
                required = schema_payload.get("required")
                self.required_parameters = set(required) if isinstance(required, list) else set()

            def _get_declaration(self):
                from google.genai import types

                return types.FunctionDeclaration(
                    name=self.name,
                    description=self.description,
                    parameters=_to_schema(self.method_payload.get("input_schema")),
                )

            async def run_async(self, *, args: Dict[str, Any], tool_context: ToolContext):
                args = dict(args or {})
                state_root = getattr(tool_context, "state", {}) or {}
                session_id = _resolve_session_id(tool_context) or _resolve_session_id(args)
                state = _ensure_session_container(state_root, session_id)
                agent_context = getattr(tool_context, "agent", None)
                if not agent_context:
                    invocation_context = getattr(tool_context, "invocation_context", None)
                    agent_context = getattr(invocation_context, "agent", None) if invocation_context else None
                    if not agent_context and invocation_context:
                        agent_context = getattr(invocation_context, "agent_name", None)
                agent_name = None
                agent_label = None
                if isinstance(agent_context, MutableMapping):
                    agent_name = agent_context.get("id") or agent_context.get("name")
                    agent_label = (
                        agent_context.get("label")
                        or agent_context.get("display_name")
                        or agent_context.get("name")
                        or agent_context.get("id")
                    )
                else:
                    agent_label = getattr(agent_context, "label", None) or getattr(agent_context, "name", None)
                    if agent_label is None and isinstance(agent_context, str):
                        agent_label = agent_context
                    agent_name = getattr(agent_context, "name", None)
                if not agent_name and agent_label:
                    agent_name = sanitize_tool_name(agent_label) or agent_label
                if not agent_label and agent_name:
                    agent_label = agent_name
                step_label = self._step_label or (_humanize_identifier(self._step) if self._step else None)
                defaults: Dict[str, Any] = {}
                for key, value in self._default_args.items():
                    resolved = resolve_argument_template(value, state)
                    if resolved not in (None, ""):
                        defaults[key] = resolved
                base_args = dict(defaults)
                for key, value in args.items():
                    if value not in (None, ""):
                        base_args[key] = value
                trimmed_args: Dict[str, Any]
                if self.parameter_names:
                    trimmed_args = {
                        key: base_args[key]
                        for key in self.parameter_names
                        if key in base_args
                    }
                else:
                    trimmed_args = dict(base_args)
                missing = [
                    name
                    for name in self.required_parameters
                    if name not in trimmed_args or trimmed_args[name] in (None, "")
                ]
                event_args = dict(trimmed_args)
                event_payload = {
                    "session_id": session_id,
                    "method": self.method,
                    "args": event_args,
                    "scope": self.tool_spec.scope,
                    "tool": self.tool_spec.name,
                    "tool_label": self._tool_label,
                }
                if self._step:
                    event_payload["step"] = self._step
                if step_label:
                    event_payload["step_label"] = step_label
                if agent_name:
                    event_payload["agent"] = agent_name
                if agent_label:
                    event_payload["agent_label"] = agent_label
                if missing:
                    error_message = "Parâmetros obrigatórios ausentes: " + ", ".join(sorted(missing))
                    self._event_bus.emit("tool.before", self.tool_spec.name, event_payload)
                    tools_section = state.setdefault("tools", {}).setdefault(self.tool_spec.name, {})
                    tools_history = tools_section.setdefault("history", [])
                    tools_history.append({"args": event_args, "error": error_message})
                    tools_section[self.method] = {"error": error_message}
                    state[f"{self.tool_spec.name}:{self.method}"] = {"error": error_message}
                    error_payload = dict(event_payload)
                    error_payload["error"] = error_message
                    self._event_bus.emit("tool.error", self.tool_spec.name, error_payload)
                    return {"error": error_message}
                call_args = {key: value for key, value in trimmed_args.items() if value is not None}
                self._event_bus.emit("tool.before", self.tool_spec.name, event_payload)
                tools_section = state.setdefault("tools", {}).setdefault(self.tool_spec.name, {})
                tools_history = tools_section.setdefault("history", [])
                try:
                    instance = self.tool_spec.ensure_instance()
                    result = invoke_tool(instance, self.method, call_args, state)
                    if inspect.isawaitable(result):
                        result = await result
                except RuntimeToolError as exc:
                    exc_details = _exception_details(exc)
                    error_payload = dict(event_payload)
                    error_payload.update(exc_details)
                    error_payload["error"] = exc_details["message"]
                    self._event_bus.emit("tool.error", self.tool_spec.name, error_payload)
                    record = {"args": event_args, "error": exc_details["message"]}
                    if exc_details.get("details"):
                        record["details"] = exc_details["details"]
                    if exc_details.get("stacktrace"):
                        record["stacktrace"] = exc_details["stacktrace"]
                    tools_history.append(record)
                    error_result = {"error": exc_details["message"]}
                    if exc_details.get("details"):
                        error_result["details"] = exc_details["details"]
                    if exc_details.get("stacktrace"):
                        error_result["stacktrace"] = exc_details["stacktrace"]
                    tools_section[self.method] = error_result
                    state[f"{self.tool_spec.name}:{self.method}"] = error_result
                    return error_result
                except Exception as exc:  # pragma: no cover - defensive
                    exc_details = _exception_details(exc)
                    error_payload = dict(event_payload)
                    error_payload.update(exc_details)
                    error_payload["error"] = exc_details["message"]
                    self._event_bus.emit("tool.error", self.tool_spec.name, error_payload)
                    raise
                tools_history.append({"args": event_args, "result": result})
                tools_section[self.method] = result
                state[f"{self.tool_spec.name}:{self.method}"] = result
                after_payload = dict(event_payload)
                after_payload["result"] = result
                self._event_bus.emit("tool.after", self.tool_spec.name, after_payload)
                return result

        class DynamicAgentTool(AgentTool):
            def __init__(self, target_agent, entry: Dict[str, Any]):
                super().__init__(agent=target_agent, skip_summarization=bool(entry.get("skip_summarization")))
                self._event_bus = event_bus
                self._entry = dict(entry or {})
                self._agent_key = entry.get("agent_key") or sanitize_tool_name(getattr(target_agent, "name", ""))
                self._alias = entry.get("alias")
                self._step = entry.get("step")
                self._step_label = entry.get("step_label")
                self._tool_label = entry.get("label") or _humanize_identifier(self._entry.get("alias") or self._agent_key)
                self._agent_label = entry.get("agent_label")
                self.agent = target_agent
                normalized_name = normalize_function_name(self._alias or getattr(self, "name", None) or getattr(target_agent, "name", None))
                if normalized_name:
                    self.name = normalized_name
                if entry.get("when_to_use"):
                    self.description = entry["when_to_use"]
                metadata = getattr(self, "custom_metadata", None)
                if not isinstance(metadata, dict):
                    metadata = {}
                for key in ("when_to_use", "handoff_payload", "alias"):
                    if entry.get(key):
                        metadata[key] = entry[key]
                metadata.setdefault("agent", getattr(target_agent, "name", None))
                self.custom_metadata = metadata
                defaults = entry.get("input")
                self._default_args = dict(defaults) if isinstance(defaults, dict) else {}

            async def run_async(self, *, args: Dict[str, Any], tool_context: ToolContext):
                args = dict(args or {})
                state_root = getattr(tool_context, "state", {}) or {}
                session_id = _resolve_session_id(tool_context) or _resolve_session_id(args)
                state = _ensure_session_container(state_root, session_id)
                parent_context = getattr(tool_context, "agent", None)
                if not parent_context:
                    invocation_context = getattr(tool_context, "invocation_context", None)
                    if invocation_context:
                        parent_context = getattr(invocation_context, "agent", None) or getattr(
                            invocation_context, "agent_name", None
                        )
                parent_name = None
                parent_label = None
                if isinstance(parent_context, MutableMapping):
                    parent_name = parent_context.get("id") or parent_context.get("name")
                    parent_label = (
                        parent_context.get("label")
                        or parent_context.get("display_name")
                        or parent_context.get("name")
                        or parent_context.get("id")
                    )
                else:
                    parent_label = getattr(parent_context, "label", None) or getattr(parent_context, "name", None)
                    if parent_label is None and isinstance(parent_context, str):
                        parent_label = parent_context
                        parent_name = parent_context
                    else:
                        parent_name = getattr(parent_context, "name", None)
                if not parent_label and parent_name:
                    parent_label = parent_name
                defaults: Dict[str, Any] = {}
                for key, value in self._default_args.items():
                    resolved = resolve_argument_template(value, state)
                    if resolved not in (None, ""):
                        defaults[key] = resolved
                call_args = dict(defaults)
                for key, value in args.items():
                    if value not in (None, ""):
                        call_args[key] = value
                agent_name = getattr(self.agent, "name", "agent")
                agent_label = self._agent_label or getattr(self.agent, "label", None) or agent_name
                tool_label = self._tool_label or agent_label or _humanize_identifier(self.name)
                step_label = self._step_label or (_humanize_identifier(self._step) if self._step else None)
                metadata = {key: value for key, value in self._entry.items() if key not in {"type", "kind", "agent", "name"}}
                before_payload = {
                    "session_id": session_id,
                    "metadata": metadata,
                    "args": call_args,
                    "tool": self.name,
                    "tool_label": tool_label,
                    "agent": agent_name,
                    "agent_label": agent_label,
                }
                if self._step:
                    before_payload["step"] = self._step
                if step_label:
                    before_payload["step_label"] = step_label
                if parent_name:
                    before_payload["parent_agent"] = parent_name
                if parent_label:
                    before_payload["parent_agent_label"] = parent_label
                self._event_bus.emit("agent.before", agent_name, before_payload)
                self._event_bus.emit(
                    "tool.before",
                    self.name,
                    {
                        "session_id": session_id,
                        "agent": agent_name,
                        "agent_label": agent_label,
                        "args": call_args,
                        "tool": self.name,
                        "tool_label": tool_label,
                        "step": self._step,
                        "step_label": step_label,
                        "parent_agent": parent_name,
                        "parent_agent_label": parent_label,
                    },
                )
                specialists = state.setdefault("specialists", {}).setdefault(self._agent_key, {})
                specialists["agent"] = agent_name
                if call_args:
                    specialists.setdefault("inputs", {}).update(call_args)
                    for key, value in call_args.items():
                        if key not in state or state.get(key) in (None, ""):
                            state.setdefault(key, value)
                try:
                    parent_run = getattr(super(), "run_async", None)
                    if callable(parent_run):
                        result = parent_run(args=call_args, tool_context=tool_context)
                        if inspect.isawaitable(result):
                            result = await result
                    else:  # pragma: no cover - defensive fallback for stubs
                        result = None
                except Exception as exc:  # pragma: no cover - defensive
                    exc_details = _exception_details(exc)
                    error_payload = {
                        "session_id": session_id,
                        **exc_details,
                        "error": exc_details["message"],
                        "tool": self.name,
                        "tool_label": tool_label,
                        "agent": agent_name,
                        "agent_label": agent_label,
                    }
                    if self._step:
                        error_payload["step"] = self._step
                    if step_label:
                        error_payload["step_label"] = step_label
                    if parent_name:
                        error_payload["parent_agent"] = parent_name
                    if parent_label:
                        error_payload["parent_agent_label"] = parent_label
                    self._event_bus.emit("agent.error", agent_name, error_payload)
                    tool_error_payload = {
                        "session_id": session_id,
                        "agent": agent_name,
                        "agent_label": agent_label,
                        "tool": self.name,
                        "tool_label": tool_label,
                        "step": self._step,
                        "step_label": step_label,
                        "parent_agent": parent_name,
                        "parent_agent_label": parent_label,
                        **exc_details,
                        "error": exc_details["message"],
                    }
                    self._event_bus.emit("tool.error", self.name, tool_error_payload)
                    record = {"args": call_args, "error": exc_details["message"]}
                    if exc_details.get("details"):
                        record["details"] = exc_details["details"]
                    if exc_details.get("stacktrace"):
                        record["stacktrace"] = exc_details["stacktrace"]
                    specialists.setdefault("invocations", []).append(record)
                    specialists["error"] = exc_details["message"]
                    if exc_details.get("details"):
                        specialists.setdefault("details", {}).update(exc_details["details"])
                    if exc_details.get("stacktrace"):
                        specialists["stacktrace"] = exc_details["stacktrace"]
                    raise
                if self._alias:
                    specialists["alias"] = self._alias
                specialists.setdefault("invocations", []).append({"args": call_args, "result": result})
                specialists["result"] = result
                if metadata:
                    specialists.setdefault("metadata", {}).update(metadata)
                after_payload = {
                    "session_id": session_id,
                    "result": result,
                    "tool": self.name,
                    "tool_label": tool_label,
                    "agent": agent_name,
                    "agent_label": agent_label,
                }
                if self._step:
                    after_payload["step"] = self._step
                if step_label:
                    after_payload["step_label"] = step_label
                if parent_name:
                    after_payload["parent_agent"] = parent_name
                if parent_label:
                    after_payload["parent_agent_label"] = parent_label
                self._event_bus.emit("agent.after", agent_name, after_payload)
                self._event_bus.emit(
                    "tool.after",
                    self.name,
                    {
                        "session_id": session_id,
                        "agent": agent_name,
                        "agent_label": agent_label,
                        "result": result,
                        "tool": self.name,
                        "tool_label": tool_label,
                        "step": self._step,
                        "step_label": step_label,
                        "parent_agent": parent_name,
                        "parent_agent_label": parent_label,
                    },
                )
                return result

        def _compose_instruction(spec: AgentSpec) -> Optional[str]:
            sections: List[str] = []
            system_block = _normalize_instruction_block(spec.system_instructions)
            if system_block:
                sections.append(system_block)
            assistant_block = _normalize_instruction_block(spec.assistant_instructions)
            if assistant_block:
                sections.append(assistant_block)
            runtime_directive = sub_agent_directives.get(spec.name) or {}
            when_to_use = runtime_directive.get("when_to_use")
            if when_to_use:
                sections.append(f"Delegação: {when_to_use}")
            step_notes: List[str] = []
            for entry in spec.workflow.get("steps", []) or []:
                if not isinstance(entry, dict):
                    continue
                step_name = entry.get("step_name") or entry.get("name")
                instructions = _normalize_instruction_block(entry.get("instructions"))
                if instructions:
                    label = f"{step_name}: {instructions}" if step_name else instructions
                    step_notes.append(f"- {label}")
            if step_notes:
                sections.append("Workflow guidance:\n" + "\n".join(step_notes))
            if not sections:
                return None
            return "\n\n".join(sections)

        def _build_model_arguments(agent_spec: AgentSpec) -> Dict[str, Any]:
            settings = agent_spec.model_settings or {}
            kwargs: Dict[str, Any] = {}
            model_name = settings.get("model")
            if model_name:
                kwargs["model"] = model_name
            generation_payload = settings.get("generate_content_config") or settings.get("generation")
            if isinstance(generation_payload, dict):
                config = _build_generate_config(generation_payload)
                if config is not None:
                    kwargs["generate_content_config"] = config
            planner_payload = settings.get("planner")
            if isinstance(planner_payload, dict):
                planner = _build_planner(planner_payload)
                if planner is not None:
                    kwargs["planner"] = planner
            output_key = settings.get("output_key")
            if output_key:
                kwargs["output_key"] = output_key
            return kwargs

        agents: Dict[str, LlmAgent] = {}
        for name, spec in solution.agents.items():
            instruction = _compose_instruction(spec)
            agent_kwargs: Dict[str, Any] = {
                "name": name,
                "description": spec.description or None,
                "instruction": instruction,
                "tools": [],
                "sub_agents": [],
            }
            agent_kwargs.update(_build_model_arguments(spec))
            clean_kwargs = {key: value for key, value in agent_kwargs.items() if value not in (None, [])}
            agents[name] = LlmAgent(**clean_kwargs)

        for agent_name, agent in agents.items():
            tool_objects: List[BaseTool] = []
            declared = declared_tool_usage.get(agent_name, {})
            directives_for_agent = tool_directives.get(agent_name, {})
            for tool_key, methods in declared.items():
                spec = solution.tools.get(tool_key)
                if not spec:
                    continue
                method_keys = methods or {sanitize_tool_name("run")}
                for method_key in sorted(method_keys):
                    method_name, method_payload = _resolve_tool_payload(spec, method_key)
                    directive = directives_for_agent.get(tool_key, {}).get(method_key)
                    tool_objects.append(
                        DynamicAdkTool(
                            spec,
                            method_name,
                            method_payload,
                            directive=directive,
                            event_bus=event_bus,
                        )
                    )
            for entry in agent_tool_directives.get(agent_name, []):
                agent_key = entry.get("agent_key")
                target_name = sanitized_agent_lookup.get(agent_key) or entry.get("agent_name")
                target_agent = agents.get(target_name)
                if not target_agent:
                    continue
                tool_objects.append(DynamicAgentTool(target_agent, entry))
                if target_agent not in agent.sub_agents:
                    agent.sub_agents.append(target_agent)
                    if getattr(target_agent, "parent_agent", None) is None:
                        target_agent.parent_agent = agent
            if tool_objects:
                agent.tools.extend(tool_objects)

        for parent_name, children in declared_sub_agents.items():
            parent_agent = agents.get(parent_name)
            if not parent_agent:
                continue
            seen_names: set[str] = set()
            for child_key in children:
                target_name = sanitized_agent_lookup.get(child_key) or child_key
                child_agent = agents.get(target_name)
                if not child_agent or target_name in seen_names:
                    continue
                seen_names.add(target_name)
                parent_agent.sub_agents.append(child_agent)
                if getattr(child_agent, "parent_agent", None) is None:
                    child_agent.parent_agent = parent_agent

        root_agent = agents.get(solution.entrypoint_agent)
        if not root_agent:
            raise KeyError(f"Agente raiz '{solution.entrypoint_agent}' não encontrado")
        root_agent.parent_agent = None
        return App(name=app_name, root_agent=root_agent)


# --------------------------------------------------------------------------- #
# CLI helpers
# --------------------------------------------------------------------------- #


ENV_SAMPLE_LINES: Tuple[str, ...] = (
    "# Exemplo de configuração de ambiente para Dynamic Agents e Google ADK",
    "",
    "# Credenciais e modelos Google GenAI / ADK",
    "GOOGLE_API_KEY=",
    "GOOGLE_APPLICATION_CREDENTIALS=",
    "GOOGLE_VERTEX_PROJECT=",
    "GOOGLE_VERTEX_LOCATION=",
    "GOOGLE_VERTEX_REGION=",
    "GOOGLE_VERTEX_MODEL=",
    "",
    "# Configurações do runtime Dynamic Agents",
    "AGENT_ENGINE_LOG_LEVEL=INFO",
    "DA_WORKFLOW_SEARCH_PATHS=",
    "DA_AGENT_CODE_PATHS=",
    "DA_TOOL_CODE_PATHS=",
    "DA_RUNTIME_PLUGINS=",
    "DA_SESSION_REGISTRY_TTL=1800",
    "DA_SESSION_REGISTRY_MAX=64",
    "",
    "# Variáveis específicas das soluções de exemplo",
    "TRAVEL_PLANNER_DEFAULT_ORIGIN=",
    "TRAVEL_PLANNER_DEFAULT_DESTINATION=",
    "TRAVEL_PLANNER_DATA_DIR=",
    "SELF_TEST_LAB_FIXTURES_ROOT=",
)

RUNTIME_CORE_REQUIREMENTS: Tuple[str, ...] = (
    "dynamics-agents",
    "google-adk>=1.14.1",
    "google-genai>=1.38.0",
    "pyyaml>=6.0",
)


def ensure_env_sample(root: Path, *, force: bool = False) -> Tuple[Path, bool]:
    """Ensure a ``.env.sample`` scaffold exists with the recommended variables."""

    env_path = Path(root).resolve() / ".env.sample"
    payload = "\n".join(ENV_SAMPLE_LINES) + "\n"

    if force or not env_path.exists():
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(payload, encoding="utf-8")
        return env_path, True

    existing_lines = env_path.read_text(encoding="utf-8").splitlines()
    normalized_existing = {line.strip() for line in existing_lines if line.strip()}
    missing = [line for line in ENV_SAMPLE_LINES if line and line not in normalized_existing]

    if not missing:
        return env_path, False

    updated_lines = list(existing_lines)
    if updated_lines and updated_lines[-1].strip():
        updated_lines.append("")
    updated_lines.extend(missing)
    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return env_path, True


def _normalize_requirement_entry(entry: str) -> str:
    """Normalize a requirement string for comparison purposes."""

    return entry.split("#", 1)[0].strip().lower()


def ensure_runtime_requirements(
    root: Path,
    *,
    additional: Optional[Iterable[str]] = None,
) -> Tuple[Path, bool]:
    """Ensure ``requirements.txt`` exists with the mandatory dependencies.

    The function creates the file when it does not exist and appends any missing
    dependency when the file is already present.  Returns the path to the
    ``requirements.txt`` file and a flag indicating whether the file changed.
    """

    requirements_path = Path(root).resolve() / "requirements.txt"
    base_requirements: List[str] = list(RUNTIME_CORE_REQUIREMENTS)
    if additional:
        for candidate in additional:
            if candidate:
                base_requirements.append(candidate)

    if not requirements_path.exists():
        payload = [
            "# Dependências essenciais para executar soluções baseadas em dynamics-agents",
            "",
            *dict.fromkeys(base_requirements),
        ]
        requirements_path.parent.mkdir(parents=True, exist_ok=True)
        requirements_path.write_text("\n".join(payload) + "\n", encoding="utf-8")
        return requirements_path, True

    existing_lines = requirements_path.read_text(encoding="utf-8").splitlines()
    existing_tokens = {
        _normalize_requirement_entry(line)
        for line in existing_lines
        if line.strip() and not line.lstrip().startswith("#")
    }

    missing = [
        requirement
        for requirement in dict.fromkeys(base_requirements)
        if _normalize_requirement_entry(requirement) not in existing_tokens
    ]

    if not missing:
        return requirements_path, False

    updated_lines = list(existing_lines)
    if updated_lines and updated_lines[-1].strip():
        updated_lines.append("")
    updated_lines.extend(missing)
    requirements_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return requirements_path, True


def available_templates() -> List[str]:
    package_root = Path(__file__).resolve().parent / "template_samples"
    templates: List[str] = []
    for path in package_root.iterdir():
        if path.name.startswith("__"):
            continue
        if path.is_dir():
            templates.append(path.name)
        elif path.suffix == ".zip":
            templates.append(path.stem)
    return sorted(templates)


def install_runtime_plugins(root: Path, *, force: bool = False) -> Path:
    source_plugins = Path(__file__).resolve().parent / "plugins"
    root_path = Path(root).resolve()
    destination = root_path / "plugins"
    ensure_env_sample(root_path)
    ensure_runtime_requirements(root_path)
    if not source_plugins.exists():
        return destination
    if destination.exists():
        if force:
            shutil.rmtree(destination)
        else:
            return destination
    shutil.copytree(source_plugins, destination)
    return destination


def install_solution_template(
    template_name: str,
    root: Path,
    *,
    force: bool = False,
    copy_plugins: bool = False,
) -> Path:
    templates_dir = Path(__file__).resolve().parent / "template_samples"
    root_path = Path(root).resolve()
    ensure_env_sample(root_path)
    destination = root_path / template_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    archive_path = templates_dir / f"{template_name}.zip"
    if archive_path.exists():
        if destination.exists():
            if not force:
                raise FileExistsError(f"Template '{template_name}' já instalado em {destination}")
            shutil.rmtree(destination)
        shutil.unpack_archive(str(archive_path), str(destination))
        if copy_plugins:
            install_runtime_plugins(root_path, force=force)
        ensure_runtime_requirements(root_path)
        return destination
    source_dir = templates_dir / template_name
    if source_dir.is_dir():
        source_payload = source_dir
        entries = [child for child in source_dir.iterdir() if not child.name.startswith("__")]
        if len(entries) == 1 and entries[0].is_dir():
            source_payload = entries[0]
        if destination.exists():
            if not force:
                raise FileExistsError(f"Template '{template_name}' já instalado em {destination}")
            shutil.rmtree(destination)
        shutil.copytree(source_payload, destination)
        if copy_plugins:
            install_runtime_plugins(root_path, force=force)
        ensure_runtime_requirements(root_path)
        return destination
    raise FileNotFoundError(f"Template '{template_name}' não encontrado")
    return destination


def install_all_solution_templates(
    root: Path,
    *,
    force: bool = False,
    copy_plugins: bool = False,
) -> Dict[str, Path]:
    root_path = Path(root).resolve()
    ensure_env_sample(root_path)
    destinations: Dict[str, Path] = {}
    for template in available_templates():
        destinations[template] = install_solution_template(
            template,
            root_path,
            force=force,
            copy_plugins=copy_plugins,
        )
    ensure_runtime_requirements(root_path)
    return destinations


@dataclass
class ParsedArguments:
    command: str
    sample: Optional[str] = None
    root: Path = Path.cwd()
    force: bool = False


def parse_arguments(argv: Optional[List[str]] = None) -> ParsedArguments:
    parser = argparse.ArgumentParser(description="Dynamic Agents template manager")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Destino dos arquivos instalados")
    parser.add_argument("--force", action="store_true", help="Sobrescreve diretórios já existentes")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list-samples", action="store_true", help="Lista exemplos de soluções disponíveis")
    group.add_argument("--install-samples", action="store_true", help="Instala todos os exemplos de soluções")
    group.add_argument(
        "--install-sample",
        dest="sample",
        help="Instala apenas o exemplo indicado",
    )
    group.add_argument("--init", action="store_true", help="Copia plugins padrão para o workspace informado")

    args = parser.parse_args(argv)

    if args.list_samples:
        command = "list_samples"
    elif args.install_samples:
        command = "install_samples"
    elif args.sample:
        command = "install_sample"
    else:
        command = "init"

    return ParsedArguments(command=command, sample=getattr(args, "sample", None), root=args.root, force=args.force)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_arguments(argv)
    print_cli_banner()
    runtime = DynamicAgentRuntime(args.root)

    if args.command == "list_samples":
        for name in available_templates():
            print(name)
        return 0
    if args.command == "install_samples":
        env_before = (Path(args.root).resolve() / ".env.sample").exists()
        destinations = install_all_solution_templates(args.root, force=args.force, copy_plugins=False)
        for name, destination in destinations.items():
            print(f"Sample '{name}' copiado para {destination}")
        requirements_path, updated = ensure_runtime_requirements(args.root)
        if updated:
            print(f"Dependências essenciais registradas em {requirements_path}")
        else:
            print(f"Dependências essenciais já estavam registradas em {requirements_path}")
        env_path, env_updated = ensure_env_sample(args.root)
        if env_updated or not env_before:
            print(f"Arquivo de ambiente de exemplo disponível em {env_path}")
        else:
            print(f"Arquivo de ambiente de exemplo já existia em {env_path}")
        return 0
    if args.command == "install_sample":
        if not args.sample:
            raise SystemExit("--install-sample requer o nome de um exemplo")
        env_before = (Path(args.root).resolve() / ".env.sample").exists()
        destination = install_solution_template(args.sample, args.root, force=args.force, copy_plugins=False)
        print(f"Sample '{args.sample}' copiado para {destination}")
        requirements_path, updated = ensure_runtime_requirements(args.root)
        if updated:
            print(f"Dependências essenciais registradas em {requirements_path}")
        else:
            print(f"Dependências essenciais já estavam registradas em {requirements_path}")
        env_path, env_updated = ensure_env_sample(args.root)
        if env_updated or not env_before:
            print(f"Arquivo de ambiente de exemplo disponível em {env_path}")
        else:
            print(f"Arquivo de ambiente de exemplo já existia em {env_path}")
        return 0
    env_before = (Path(args.root).resolve() / ".env.sample").exists()
    plugins_destination = install_runtime_plugins(args.root, force=args.force)
    if plugins_destination.exists():
        print(f"Plugins padrão disponíveis em {plugins_destination}")
    else:
        print("Nenhum plugin foi copiado; verifique se o pacote inclui plugins")
    requirements_path, updated = ensure_runtime_requirements(args.root)
    if updated:
        print(f"Dependências essenciais registradas em {requirements_path}")
    else:
        print(f"Dependências essenciais já estavam registradas em {requirements_path}")
    env_path, env_updated = ensure_env_sample(args.root)
    if env_updated or not env_before:
        print(f"Arquivo de ambiente de exemplo disponível em {env_path}")
    else:
        print(f"Arquivo de ambiente de exemplo já existia em {env_path}")
    return 0


try:  # pragma: no cover - alias preserved for backwards compatibility
    _logging_plugin_instance_for_alias = _instantiate_builtin_plugin_by_name(RUNTIME_LOGGING_PLUGIN_NAME)
    if _logging_plugin_instance_for_alias is not None:
        RuntimeLoggingPlugin = type(_logging_plugin_instance_for_alias)
    else:  # pragma: no cover - defensive fallback
        raise RuntimeError("Runtime logging plugin not available")
except Exception:  # pragma: no cover - defensive fallback
    class RuntimeLoggingPlugin(RuntimePlugin):
        PLUGIN_NAME = RUNTIME_LOGGING_PLUGIN_NAME

        def handle_event(self, event: RuntimeEvent) -> None:
            pass


__all__ = [
    "AgentSpec",
    "SolutionBootstrapError",
    "DynamicAgentRuntime",
    "EventRecorder",
    "RuntimeLoggingPlugin",
    "RuntimeCallbackError",
    "RuntimeEvent",
    "RuntimeEventBus",
    "RuntimePlugin",
    "RuntimeToolError",
    "SESSION_REGISTRY_KEY",
    "SolutionDescriptor",
    "SolutionRuntime",
    "StepSpec",
    "ToolSpec",
    "available_templates",
    "dump_yaml",
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
]
