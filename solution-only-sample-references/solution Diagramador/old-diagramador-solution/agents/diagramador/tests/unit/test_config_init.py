"""Tests for the lightweight app.config package initialization."""

import importlib
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
for p in (PROJECT_ROOT, APP_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def test_config_module_exports(monkeypatch):
    settings_stub = types.SimpleNamespace(Settings="settings", get_settings=lambda: {"env": "test"})
    prompts_stub = types.SimpleNamespace(ANALYSIS_PROMPTS={"welcome": "Olá"})
    patterns_stub = types.SimpleNamespace(BANKING_PATTERNS=["PIX"])

    monkeypatch.setitem(sys.modules, "app.config.settings", settings_stub)
    monkeypatch.setitem(sys.modules, "app.config.prompts", prompts_stub)
    monkeypatch.setitem(sys.modules, "app.config.patterns", patterns_stub)

    config = importlib.reload(importlib.import_module("app.config"))

    assert config.Settings == "settings"
    assert config.get_settings()["env"] == "test"
    assert config.ANALYSIS_PROMPTS["welcome"] == "Olá"
    assert config.BANKING_PATTERNS == ["PIX"]
    assert "Settings" in config.__all__
