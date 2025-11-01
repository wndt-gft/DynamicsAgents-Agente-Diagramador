"""
Tools package simplified: removed unused enhanced analyzer exports.
"""

import sys
import os
import logging

logger = logging.getLogger(__name__)
current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from .analyzers import UnifiedStoryAnalyzer
    from .validators import UnifiedQualityValidator, MetamodelValidator, ArchiMate30SchemaValidator
    from .generators import UnifiedDiagramGenerator, NCNameIDGenerator, TemplateBasedContainerGenerator, GenericDiagramGenerator
    from .utilities import (
        OutputManager,
        AgentContext,
        NamingConventionApplier,
        XMLIntegrityEnforcer,
        TemplateLayoutEnforcer,
        MessageProcessor,
    )
    from . import diagram_service
    ORGANIZED_TOOLS_AVAILABLE = True
except ImportError:
    ORGANIZED_TOOLS_AVAILABLE = False
    class UnifiedStoryAnalyzer:  # stubs
        def analyze_story(self, *_a, **_k): return {"elements":[],"relationships":[]}
    class UnifiedQualityValidator:
        def validate_quality(self, *_a, **_k): return {"score":0}
    class MetamodelValidator(UnifiedQualityValidator): ...
    class ArchiMate30SchemaValidator: ...
    class UnifiedDiagramGenerator:
        def generate_container_diagram(self, *_a, **_k): return {"xml_content":""}
    class NCNameIDGenerator: ...
    class TemplateBasedContainerGenerator: ...
    class GenericDiagramGenerator: ...
    class OutputManager: ...
    class AgentContext: ...
    class NamingConventionApplier: ...
    class XMLIntegrityEnforcer: ...
    class TemplateLayoutEnforcer: ...
    class MessageProcessor: ...
    class diagram_service: ...

if ORGANIZED_TOOLS_AVAILABLE:
    __all__ = [
        'UnifiedStoryAnalyzer',
        'UnifiedQualityValidator', 'MetamodelValidator', 'ArchiMate30SchemaValidator',
        'UnifiedDiagramGenerator', 'NCNameIDGenerator', 'TemplateBasedContainerGenerator', 'GenericDiagramGenerator',
        'OutputManager', 'AgentContext', 'NamingConventionApplier', 'XMLIntegrityEnforcer', 'TemplateLayoutEnforcer', 'MessageProcessor',
        'diagram_service'
    ]
    def validate_diagram_quality(xml_content: str, diagram_type: str = "container") -> dict:
        return UnifiedQualityValidator().validate_quality(xml_content, diagram_type)
    def analyze_user_story(story_text: str, domain: str = "Banking") -> dict:
        return UnifiedStoryAnalyzer().analyze_story(story_text, domain)
    def generate_container_diagram(user_story: str = "", **kwargs) -> dict:
        return UnifiedDiagramGenerator().generate_container_diagram(user_story, **kwargs)
else:
    __all__ = ['UnifiedStoryAnalyzer','UnifiedQualityValidator','MetamodelValidator','UnifiedDiagramGenerator']
    def validate_diagram_quality(_x, _d="container"): return {"score":0}
    def analyze_user_story(_s, _d="Banking"): return {"elements":[],"relationships":[]}
    def generate_container_diagram(_u="", **_k): return {"xml_content":""}

__version__ = "3.1.1-slim"
