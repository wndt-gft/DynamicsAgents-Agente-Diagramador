"""
Generators package - Tools for creating and generating diagrams, artifacts, and outputs
Contains various generators for diagram creation and ID generation
"""

try:
    from .diagram_generator import (
        GenericDiagramGenerator, 
        generate_container_diagram, 
        DiagramGenerator,
        C4DiagramEngine,
        generate_archimate_container_diagram,
        xml_to_plantuml
    )
    from .id_generator import NCNameIDGenerator, generate_element_id, generate_relationship_id, generate_view_id, reset_id_generator
    from .template_based_generator import TemplateBasedContainerGenerator
    from .metamodel_compliant_generator import MetamodelCompliantC4Generator

    __all__ = [
        'GenericDiagramGenerator',
        'DiagramGenerator',  # Legacy alias
        'C4DiagramEngine',   # Legacy compatibility
        'generate_container_diagram',
        'generate_archimate_container_diagram',  # Legacy compatibility
        'xml_to_plantuml',   # Legacy compatibility
        'NCNameIDGenerator',
        'generate_element_id',
        'generate_relationship_id', 
        'generate_view_id',
        'reset_id_generator',
        'TemplateBasedContainerGenerator',
        'MetamodelCompliantC4Generator',
        'UnifiedDiagramGenerator'
    ]
    
except ImportError:
    # Fallback for missing dependencies
    __all__ = ['UnifiedDiagramGenerator']

    def generate_container_diagram(*args, **kwargs):
        return {"xml_content": "", "plantuml_content": "", "metadata": {}}
    
    def generate_element_id(base_name: str) -> str:
        return f"id_{base_name.replace(' ', '_').lower()}"
    
    def generate_relationship_id(source: str, target: str) -> str:
        return f"rel_{source}_{target}"
    
    def generate_view_id(view_name: str) -> str:
        return f"view_{view_name.replace(' ', '_').lower()}"
    
    def reset_id_generator():
        pass
    
    class GenericDiagramGenerator:
        def __init__(self, *args, **kwargs):
            pass
        def generate(self, *args, **kwargs):
            return {"error": "Generator not available"}
    
    class NCNameIDGenerator:
        def __init__(self, *args, **kwargs):
            pass
        def generate_id(self, *args, **kwargs):
            return "id_fallback"
    
    class TemplateBasedContainerGenerator:
        def __init__(self, *args, **kwargs):
            pass
        def generate(self, *args, **kwargs):
            return {"error": "Template generator not available"}
    
    class MetamodelCompliantC4Generator:
        def __init__(self, *args, **kwargs):
            pass
        def generate(self, *args, **kwargs):
            return {"error": "Metamodel generator not available"}

# Legacy compatibility - unified generator class
class UnifiedDiagramGenerator:
    """Unified interface for all diagram generation functionality"""
    
    def __init__(self):
        self.generic_generator = GenericDiagramGenerator() if 'GenericDiagramGenerator' in globals() else None
        self.template_generator = TemplateBasedContainerGenerator() if 'TemplateBasedContainerGenerator' in globals() else None
        self.id_generator = NCNameIDGenerator() if 'NCNameIDGenerator' in globals() else None

    def generate_diagram(self, elements: list, relationships: list, **kwargs) -> dict:
        """Generate diagram from elements and relationships"""
        try:
            return self.generic_generator.generate(elements, relationships, **kwargs) if self.generic_generator else {"error":"generator unavailable"}
        except Exception:
            return {"error": "generation failed", "xml_content": "", "plantuml_content": ""}

    def generate_container_diagram(self, user_story: str = "", **kwargs) -> dict:
        """Generate container diagram from user story"""
        return generate_container_diagram(user_story, **kwargs)