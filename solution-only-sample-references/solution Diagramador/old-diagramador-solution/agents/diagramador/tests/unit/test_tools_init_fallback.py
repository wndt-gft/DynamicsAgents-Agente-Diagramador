"""Tests covering fallback exports in app.tools and app.tools.utilities packages."""

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
for p in (PROJECT_ROOT, APP_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def test_tools_module_fallback_functions(monkeypatch):
    # Ensure modules are reloaded to exercise fallback branch
    monkeypatch.delitem(sys.modules, "app.tools", raising=False)
    tools_mod = importlib.import_module("app.tools")

    quality = tools_mod.validate_diagram_quality("<xml/>")
    assert isinstance(quality, dict)
    story = tools_mod.analyze_user_story("Como usuário quero autenticar")
    assert isinstance(story, dict)
    diagram = tools_mod.generate_container_diagram("Historia")
    assert isinstance(diagram, dict)


def test_utilities_module_fallback(monkeypatch):
    monkeypatch.delitem(sys.modules, "app.tools.utilities", raising=False)
    utilities_mod = importlib.import_module("app.tools.utilities")

    assert hasattr(utilities_mod, "get_current_context")
    context = utilities_mod.get_current_context()
    assert isinstance(context, dict)
    if hasattr(utilities_mod, "normalize_name"):
        assert utilities_mod.normalize_name("Hello World").replace("_", "").lower().startswith("helloworld")
