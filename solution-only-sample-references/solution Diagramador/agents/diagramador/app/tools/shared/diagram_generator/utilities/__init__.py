"""Utility helpers used by the shared diagram generator."""

from .confirmation_handler import ConfirmationHandler
from .context_manager import DiagramContextManager
from .file_handler import FileHandler
from .message_processor import MessageProcessor
from .naming_conventions import NamingConventionApplier
from .template_layout_enforcer import TemplateLayoutEnforcer
from .xml_integrity_enforcer import XMLIntegrityEnforcer, enforce_xml_integrity

__all__ = [
    "ConfirmationHandler",
    "DiagramContextManager",
    "FileHandler",
    "MessageProcessor",
    "NamingConventionApplier",
    "TemplateLayoutEnforcer",
    "XMLIntegrityEnforcer",
    "enforce_xml_integrity",
]
