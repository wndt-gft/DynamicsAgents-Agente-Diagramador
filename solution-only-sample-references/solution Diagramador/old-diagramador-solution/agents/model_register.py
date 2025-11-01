"""Utility helpers for dynamically configuring LLM models for agents."""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional


try:
    _ADK_REGISTRY_SPEC = importlib.util.find_spec("google.adk.models.registry")
except ModuleNotFoundError:
    _ADK_REGISTRY_SPEC = None

if _ADK_REGISTRY_SPEC is not None:
    from google.adk.models.registry import LLMRegistry as _ADK_LLMRegistry

    class _RegistryAdapter:
        """Proxy that delegates registrations to the real ADK registry."""

        @staticmethod
        def register(model_class):
            _ADK_LLMRegistry.register(model_class)


else:

    class _RegistryAdapter:
        """Minimal in-memory registry used when Google ADK is unavailable."""

        _registered = set()

        @classmethod
        def register(cls, model_class):
            cls._registered.add(model_class)


LLMRegistry = _RegistryAdapter


@dataclass
class ModelConfig:
    """Configuration describing the model to be used by an agent."""

    name: str
    registry_path: Optional[str] = None


_REGISTERED_CLASSES: set[str] = set()


def _parse_model_string(raw_value: str) -> ModelConfig:
    """Parses raw environment string into a :class:`ModelConfig`.

    The parsing strategy is intentionally flexible to support different
    configuration formats:
    * JSON payload: ``{"model": "...", "registry": "module:Class"}``
    * ``model::module:Class`` or ``model|module:Class`` tokens
    * plain model name (assumes native ADK model, no registry needed)
    """

    raw_value = raw_value.strip()
    if not raw_value:
        return ModelConfig(name="")

    # Try JSON payload first
    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        decoded = None

    if isinstance(decoded, dict):
        model_name = str(
            decoded.get("model")
            or decoded.get("name")
            or decoded.get("id")
            or ""
        ).strip()
        registry_path = decoded.get("registry") or decoded.get("register")
        if registry_path:
            registry_path = str(registry_path).strip()
        return ModelConfig(name=model_name, registry_path=registry_path or None)

    # Support ``model::module:Class`` or ``model|module:Class`` syntaxes
    for delimiter in ("::", "|", ";"):
        if delimiter in raw_value:
            model_name, registry_path = raw_value.split(delimiter, 1)
            return ModelConfig(name=model_name.strip(), registry_path=registry_path.strip())

    # Default: treat raw string as native model identifier
    return ModelConfig(name=raw_value)


def _import_registry_class(path: str):
    """Imports and returns the registry class specified by ``path``."""

    if not path:
        raise ValueError("Empty registry path provided")

    module_path: str
    class_name: str
    if ":" in path:
        module_path, class_name = path.split(":", 1)
    else:
        module_path, _, class_name = path.rpartition(".")
        if not module_path:
            raise ValueError(
                "Registry path must include module and class, received %s" % path
            )

    module = importlib.import_module(module_path.strip())
    return getattr(module, class_name.strip())


def _register_model_class(registry_path: str, logger: Optional[logging.Logger] = None) -> None:
    """Registers the model class with the ADK ``LLMRegistry`` if needed."""

    if registry_path in _REGISTERED_CLASSES:
        return

    try:
        model_class = _import_registry_class(registry_path)
        LLMRegistry.register(model_class)
        _REGISTERED_CLASSES.add(registry_path)
        if logger:
            logger.info("✅ Modelo registrado: %s", registry_path)
    except Exception as exc:  # pylint: disable=broad-except
        if logger:
            logger.error("❌ Falha ao registrar modelo %s: %s", registry_path, exc)
        raise


def configure_model(
    *,
    env_var_name: str,
    env_registry_var_name: Optional[str] = None,
    default_model: str,
    default_registry_path: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> str:
    """Determines the model to be used and registers it when required.

    Args:
        env_var_name: Environment variable with the model configuration.
        env_registry_var_name: Optional environment variable that, when set,
            forces the registry path to import/register before using the model.
        default_model: Model identifier used when the environment variable is
            absent or empty.
        default_registry_path: Registry path for non-native models. Used when
            neither the environment configuration nor the default model specify
            a different class.
        logger: Optional logger for diagnostic messages.

    Returns:
        The resolved model identifier ready to be used by the agent.
    """

    raw_value = os.getenv(env_var_name, "").strip()

    registry_override: Optional[str] = None
    if env_registry_var_name:
        registry_override = os.getenv(env_registry_var_name, "").strip() or None

    if raw_value:
        config = _parse_model_string(raw_value)
    else:
        config = ModelConfig(name=default_model, registry_path=default_registry_path)

    if not config.name:
        config.name = default_model

    registry_path_candidate: Optional[str]
    if registry_override is not None:
        registry_path_candidate = registry_override
    elif config.registry_path is not None:
        registry_path_candidate = config.registry_path
    else:
        registry_path_candidate = default_registry_path

    registry_path = registry_path_candidate or None

    if registry_path:
        _register_model_class(registry_path, logger)
    elif logger:
        logger.info("ℹ️ Modelo %s considerado nativo, sem registro adicional.", config.name)

    return config.name


__all__ = ["configure_model", "ModelConfig"]
