"""Constantes globais utilizadas pelo agente Diagramador."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Sequence

__all__ = [
    "DEFAULT_MODEL",
    "OUTPUT_DIR",
    "DEFAULT_DATAMODEL_FILENAME",
    "DEFAULT_DIAGRAM_FILENAME",
    "DEFAULT_TEMPLATE",
    "DEFAULT_TEMPLATES_DIR",
    "DEFAULT_XSD_DIR",
    "ARCHIMATE_NS",
"XSI_ATTR",
"XML_LANG_ATTR",
]

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
PACKAGE_TEMPLATES_DIR = (PACKAGE_ROOT / "templates").resolve()
DEFAULT_MODEL = os.getenv("DIAGRAMADOR_MODEL", "gemini-2.5-pro")
OUTPUT_DIR = Path("outputs")
DEFAULT_DATAMODEL_FILENAME = "diagramador_datamodel.json"
DEFAULT_DIAGRAM_FILENAME = "diagramador_container_diagram.xml"


def _candidate_paths(value: str, extras: Sequence[Path] = ()) -> Iterable[Path]:
    """Generate plausible absolute paths for ``value``."""

    raw = Path(value)
    if raw.is_absolute():
        yield raw
        return

    bases = [
        Path.cwd(),
        PACKAGE_ROOT,
        REPO_ROOT,
        PACKAGE_TEMPLATES_DIR,
        *extras,
    ]
    for base in bases:
        yield (base / raw).resolve()


def _resolve_path(
    value: str | None,
    fallback: Path,
    *,
    extras: Sequence[Path] = (),
) -> Path:
    """Resolve ``value`` against several bases, falling back when missing."""

    if value:
        for candidate in _candidate_paths(value, extras):
            if candidate.exists():
                return candidate
    return fallback.resolve()


DEFAULT_TEMPLATES_DIR = _resolve_path(
    os.getenv("DIAGRAMADOR_TEMPLATES_DIR"),
    PACKAGE_TEMPLATES_DIR,
)

_packaged_default_template = (PACKAGE_TEMPLATES_DIR / "BV-C4-Model-SDLC/Layout - Visão de Container.xml").resolve()
_env_template = os.getenv("DIAGRAMADOR_TEMPLATE")
if _env_template:
    DEFAULT_TEMPLATE = _resolve_path(
        _env_template,
        _packaged_default_template,
        extras=[DEFAULT_TEMPLATES_DIR],
    )
else:
    candidate_template = (DEFAULT_TEMPLATES_DIR / "BV-C4-Model-SDLC/Layout - Visão de Container.xml").resolve()
    DEFAULT_TEMPLATE = candidate_template if candidate_template.exists() else _packaged_default_template

_packaged_xsd_dir = (PACKAGE_TEMPLATES_DIR / "BV-C4-Model-SDLC/schemas").resolve()
_env_xsd_dir = os.getenv("DIAGRAMADOR_XSD_DIR")
if _env_xsd_dir:
    DEFAULT_XSD_DIR = _resolve_path(
        _env_xsd_dir,
        _packaged_xsd_dir,
        extras=[DEFAULT_TEMPLATE.parent, DEFAULT_TEMPLATES_DIR],
    )
else:
    candidate_xsd_dir = (DEFAULT_TEMPLATE.parent / "schemas").resolve()
    DEFAULT_XSD_DIR = candidate_xsd_dir if candidate_xsd_dir.exists() else _packaged_xsd_dir

ARCHIMATE_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_ATTR = "{http://www.w3.org/2001/XMLSchema-instance}type"
XML_LANG_ATTR = "{http://www.w3.org/XML/1998/namespace}lang"
