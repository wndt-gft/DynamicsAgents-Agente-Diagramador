"""Simple configuration manager.
Loads YAML configuration files from the app/config directory and exposes helper accessors.
Refactored to replace the old flat tools.config_manager module path used in agent.py.
"""
from __future__ import annotations
import os
import threading
from typing import Any, Dict, Optional

try:
    import yaml  # type: ignore
except ImportError:  # Fallback minimal parser (very limited) if PyYAML missing
    yaml = None  # type: ignore

_CONFIG_FILENAMES = [
    'adk_config.yaml',
    'adk_config.yaml.backup',
    'mapping.yml',
    'vocabulary.yml'
]

class ConfigManager:
    _instance: Optional['ConfigManager'] = None
    _lock = threading.Lock()

    def __init__(self, base_path: Optional[str] = None):
        self.base_path = base_path or os.path.join(os.path.dirname(__file__), '..', 'config')
        self.base_path = os.path.abspath(self.base_path)
        self._data: Dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        for name in _CONFIG_FILENAMES:
            full = os.path.join(self.base_path, name)
            if not os.path.isfile(full):
                continue
            try:
                if yaml is None:
                    # Extremely naive fallback (not recommended) - skip non-critical files
                    continue
                with open(full, 'r', encoding='utf-8') as f:
                    parsed = yaml.safe_load(f)  # type: ignore
                if isinstance(parsed, dict):
                    # Merge shallowly; later files override earlier keys
                    for k, v in parsed.items():
                        self._data[k] = v
            except Exception:
                # Silently skip corrupt file to avoid blocking agent startup
                continue
        self._loaded = True

    def get(self, key: str, default: Any = None) -> Any:
        if not self._loaded:
            self.load()
        return self._data.get(key, default)

    def all(self) -> Dict[str, Any]:
        if not self._loaded:
            self.load()
        return dict(self._data)


def get_config_manager() -> ConfigManager:
    if ConfigManager._instance is None:
        with ConfigManager._lock:
            if ConfigManager._instance is None:
                ConfigManager._instance = ConfigManager()
    return ConfigManager._instance


def get_config(key: str, default: Any = None) -> Any:
    return get_config_manager().get(key, default)

__all__ = ['get_config_manager', 'get_config', 'ConfigManager']

