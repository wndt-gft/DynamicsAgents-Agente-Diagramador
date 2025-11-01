"""Packaged solution templates installable via the CLI."""

from importlib import resources
from typing import Iterable


def iter_templates() -> Iterable[str]:
    """Yield available template names bundled with the package."""
    templates_root = resources.files(__package__)
    for entry in templates_root.iterdir():
        if entry.is_dir() and not entry.name.startswith("_"):
            yield entry.name


__all__ = ["iter_templates"]
