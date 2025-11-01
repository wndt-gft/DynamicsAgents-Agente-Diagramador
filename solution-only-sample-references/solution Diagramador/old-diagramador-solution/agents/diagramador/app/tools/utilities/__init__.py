"""
Utilities package - Helper files with reusable and generic functions
Contains shared utilities and helper functionality
"""

try:
    from .context_manager import AgentContext, get_current_context, set_current_context
    from .file_handler import OutputManager, save_diagram_files, read_template_file
    from .message_processor import (
        MessageProcessor,
        process_user_message,
        is_user_story,
        extract_diagram_type_from_message
    )
    from .naming_conventions import NamingConventionApplier, apply_naming_conventions, normalize_name
    from .template_layout_enforcer import TemplateLayoutEnforcer, enforce_template_layout
    from .xml_integrity_enforcer import XMLIntegrityEnforcer, enforce_xml_integrity
    
    __all__ = [
        'AgentContext',
        'get_current_context',
        'set_current_context',
        'OutputManager',
        'save_diagram_files',
        'read_template_file',
        'MessageProcessor',
        'process_user_message',
        'is_user_story',
        'extract_diagram_type_from_message',
        'NamingConventionApplier',
        'apply_naming_conventions',
        'normalize_name',
        'TemplateLayoutEnforcer',
        'enforce_template_layout',
        'XMLIntegrityEnforcer',
        'enforce_xml_integrity'
    ]
    
except ImportError as e:
    # Fallback for missing dependencies
    __all__ = []
    
    def get_current_context():
        return {}
    
    def set_current_context(context):
        pass
    
    def save_diagram_files(content: str, output_dir: str):
        return []
    
    def read_template_file(template_path: str):
        return ""
    
    def process_user_message(message: str):
        return {"processed": False, "message": "Processor not available"}
    
    def apply_naming_conventions(name: str):
        return name
    
    def normalize_name(name: str):
        return name.replace(" ", "_").lower()
    
    def enforce_template_layout(xml_content: str):
        return xml_content
    
    def enforce_xml_integrity(xml_content: str):
        return True, xml_content, []
    
    def is_user_story(message: str) -> bool:
        return False

    def extract_diagram_type_from_message(message: str):
        return None

    class AgentContext:
        def __init__(self, *args, **kwargs):
            self.data = {}
        def get(self, key, default=None):
            return self.data.get(key, default)
        def set(self, key, value):
            self.data[key] = value
    
    class OutputManager:
        def __init__(self, *args, **kwargs):
            pass
        def save(self, *args, **kwargs):
            return []
        def organize_output(self, *args, **kwargs):
            return []
    
    class MessageProcessor:
        def __init__(self, *args, **kwargs):
            pass
        def process(self, *args, **kwargs):
            return {"processed": False}
    
    class NamingConventionApplier:
        def __init__(self, *args, **kwargs):
            pass
        def apply(self, *args, **kwargs):
            return args[0] if args else ""
        def normalize(self, name: str):
            return normalize_name(name)
    
    class TemplateLayoutEnforcer:
        def __init__(self, *args, **kwargs):
            pass
        def apply_layout_from_existing_xml(self, xml_content: str, *args, **kwargs):
            return xml_content
    
    class XMLIntegrityEnforcer:
        def __init__(self, *args, **kwargs):
            pass
        def enforce_integrity(self, xml_content: str, *args, **kwargs):
            return True, xml_content, []