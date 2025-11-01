"""Unit tests for the dynamic model registration helper."""

import sys
import types
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents import model_register


class _RegistrySpy:
    """Simple registry spy used to capture registrations."""

    def __init__(self):
        self.registered = []

    def register(self, klass):
        self.registered.append(klass)


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch):
    spy = _RegistrySpy()
    monkeypatch.setattr(model_register, "LLMRegistry", spy)
    monkeypatch.setattr(model_register, "_REGISTERED_CLASSES", set())
    yield spy


def _install_dummy_class(monkeypatch, module_name="tests.dummy_registry", class_name="CustomModel"):
    module = types.ModuleType(module_name)

    class DummyModel:
        pass

    setattr(module, class_name, DummyModel)
    monkeypatch.setitem(sys.modules, module_name, module)
    return f"{module_name}:{class_name}", DummyModel


def test_configure_model_parses_json_and_registers(monkeypatch, reset_module_state):
    registry_path, expected_class = _install_dummy_class(monkeypatch)
    monkeypatch.setenv(
        "MODEL_UNDER_TEST",
        '{"model": "vendor/model-x", "registry": "%s"}' % registry_path,
    )

    resolved = model_register.configure_model(
        env_var_name="MODEL_UNDER_TEST",
        default_model="gemini-2.5-pro",
    )

    assert resolved == "vendor/model-x"
    assert reset_module_state.registered == [expected_class]
    assert registry_path in model_register._REGISTERED_CLASSES


def test_configure_model_registry_override_takes_precedence(monkeypatch, reset_module_state):
    registry_path, expected_class = _install_dummy_class(monkeypatch, module_name="tests.override", class_name="OverrideModel")
    monkeypatch.setenv("MODEL_OVERRIDE_LIB", registry_path)

    resolved = model_register.configure_model(
        env_var_name="MODEL_OVERRIDE",
        env_registry_var_name="MODEL_OVERRIDE_LIB",
        default_model="gemini-2.5-pro",
    )

    assert resolved == "gemini-2.5-pro"
    assert reset_module_state.registered == [expected_class]
    assert registry_path in model_register._REGISTERED_CLASSES
