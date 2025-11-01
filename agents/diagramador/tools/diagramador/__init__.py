"""Superfície pública das rotinas de ferramenta do agente Diagramador."""

from __future__ import annotations

from .artifacts import (
    SESSION_ARTIFACT_ARCHIMATE_XML,
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
    SESSION_ARTIFACT_SAVED_DATAMODEL,
    SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
    SESSION_ARTIFACT_TEMPLATE_LISTING,
)
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
from .datamodel import finalize_datamodel, generate_archimate_diagram, save_datamodel
from .layouts import LayoutValidationError, generate_layout_preview
from .session import (
    ARTIFACTS_CACHE_KEY,
    BLUEPRINT_CACHE_KEY,
    SESSION_STATE_ROOT,
    get_cached_artifact,
    get_cached_blueprint,
    get_session_bucket,
    store_artifact,
    store_blueprint,
)
from .templates import describe_template, list_templates

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
    "SESSION_ARTIFACT_TEMPLATE_LISTING",
    "SESSION_ARTIFACT_TEMPLATE_GUIDANCE",
    "SESSION_ARTIFACT_FINAL_DATAMODEL",
    "SESSION_ARTIFACT_LAYOUT_PREVIEW",
    "SESSION_ARTIFACT_SAVED_DATAMODEL",
    "SESSION_ARTIFACT_ARCHIMATE_XML",
    "describe_template",
    "finalize_datamodel",
    "generate_archimate_diagram",
    "generate_layout_preview",
    "LayoutValidationError",
    "list_templates",
    "save_datamodel",
    "BLUEPRINT_CACHE_KEY",
    "ARTIFACTS_CACHE_KEY",
    "SESSION_STATE_ROOT",
    "get_cached_artifact",
    "get_cached_blueprint",
    "get_session_bucket",
    "store_artifact",
    "store_blueprint",
]
