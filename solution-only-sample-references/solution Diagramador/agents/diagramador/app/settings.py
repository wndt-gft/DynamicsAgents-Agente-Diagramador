from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

APP_ROOT = Path(__file__).resolve().parent


def _resolve(path, base: Optional[Path] = None) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        base_dir = base or APP_ROOT
        candidate = base_dir / candidate
    return candidate.resolve()


def get_template_directory() -> Path:
    """Return the directory that contains the C4 templates."""

    env_value = os.getenv("DIAGRAMADOR_TEMPLATE_DIR")
    if env_value:
        return _resolve(env_value)
    return (APP_ROOT / "templates" / "C4-Model").resolve()


def get_template_path(template_dir: Optional[Path] = None) -> Path:
    """Return the layout template path, allowing environment override."""

    env_value = os.getenv("DIAGRAMADOR_TEMPLATE_PATH")
    if env_value:
        return _resolve(env_value)
    base = template_dir or get_template_directory()
    return (base / "layout_sdlc.xml").resolve()


def get_metamodel_path(template_dir: Optional[Path] = None) -> Path:
    """Return the metamodel XML path, allowing environment override."""

    env_value = os.getenv("DIAGRAMADOR_METAMODEL_PATH")
    if env_value:
        return _resolve(env_value)
    base = template_dir or get_template_directory()
    return (base / "metamodel.xml").resolve()


def get_output_root() -> Path:
    """Return the base directory used to persist generated artifacts."""

    env_value = os.getenv("DIAGRAMADOR_OUTPUT_ROOT")
    if env_value:
        return _resolve(env_value)
    return (APP_ROOT / "outputs").resolve()
