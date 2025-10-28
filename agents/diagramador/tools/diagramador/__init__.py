"""Pacote com as operações principais do agente Diagramador."""

from __future__ import annotations

from .constants import (
    ARCHIMATE_NS,
    DEFAULT_DATAMODEL_FILENAME,
    DEFAULT_DIAGRAM_FILENAME,
    DEFAULT_MODEL,
    DEFAULT_TEMPLATE,
    DEFAULT_TEMPLATES_DIR,
    DEFAULT_XSD_DIR,
    OUTPUT_DIR,
    XML_LANG_ATTR,
    XSI_ATTR,
)
from .operations import (
    describe_template,
    finalize_datamodel,
    generate_archimate_diagram,
    generate_mermaid_preview,
    list_templates,
    save_datamodel,
)
from .session import (
    BLUEPRINT_CACHE_KEY,
    SESSION_STATE_ROOT,
    get_cached_blueprint,
    get_session_bucket,
    store_blueprint,
)

__all__ = [
    "ARCHIMATE_NS",
    "DEFAULT_DATAMODEL_FILENAME",
    "DEFAULT_DIAGRAM_FILENAME",
    "DEFAULT_MODEL",
    "DEFAULT_TEMPLATE",
    "DEFAULT_TEMPLATES_DIR",
    "DEFAULT_XSD_DIR",
    "OUTPUT_DIR",
    "XML_LANG_ATTR",
    "XSI_ATTR",
    "describe_template",
    "finalize_datamodel",
    "generate_archimate_diagram",
    "generate_mermaid_preview",
    "list_templates",
    "save_datamodel",
    "BLUEPRINT_CACHE_KEY",
    "SESSION_STATE_ROOT",
    "get_cached_blueprint",
    "get_session_bucket",
    "store_blueprint",
]
