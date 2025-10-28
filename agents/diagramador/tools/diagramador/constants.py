"""Constantes globais utilizadas pelo agente Diagramador."""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "DEFAULT_MODEL",
    "OUTPUT_DIR",
    "DEFAULT_DATAMODEL_FILENAME",
    "DEFAULT_DIAGRAM_FILENAME",
    "DEFAULT_TEMPLATE",
    "DEFAULT_TEMPLATES_DIR",
    "DEFAULT_XSD_DIR",
    "DEFAULT_KROKI_URL",
    "FETCH_MERMAID_IMAGES",
    "ARCHIMATE_NS",
    "XSI_ATTR",
    "XML_LANG_ATTR",
]

DEFAULT_MODEL = os.getenv("DIAGRAMADOR_MODEL", "gemini-2.5-pro")
OUTPUT_DIR = Path("outputs")
DEFAULT_DATAMODEL_FILENAME = "diagramador_datamodel.json"
DEFAULT_DIAGRAM_FILENAME = "diagramador_container_diagram.xml"
DEFAULT_TEMPLATE = Path("templates/BV-C4-Model-SDLC/layout_template.xml")
DEFAULT_TEMPLATES_DIR = Path(os.getenv("DIAGRAMADOR_TEMPLATES_DIR", "templates"))
DEFAULT_XSD_DIR = Path(
    os.getenv("DIAGRAMADOR_XSD_DIR", "templates/BV-C4-Model-SDLC/schemas")
)
DEFAULT_KROKI_URL = os.getenv("DIAGRAMADOR_KROKI_URL", "https://kroki.io")
FETCH_MERMAID_IMAGES = os.getenv("DIAGRAMADOR_FETCH_MERMAID_IMAGES", "0").lower() in (
    "1",
    "true",
    "yes",
)

ARCHIMATE_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_ATTR = "{http://www.w3.org/2001/XMLSchema-instance}type"
XML_LANG_ATTR = "{http://www.w3.org/XML/1998/namespace}lang"
