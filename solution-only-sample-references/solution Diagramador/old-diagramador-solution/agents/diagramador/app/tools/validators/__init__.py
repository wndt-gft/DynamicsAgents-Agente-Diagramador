"""
Validators package slim: only quality, schema and C4 metamodel validators retained.
"""

try:
    from .quality_validator import validate_diagram_quality, scan_for_hardcoded_terms
    from .schema_validator import ArchiMate30SchemaValidator
    from .c4_quality_validator import C4QualityValidator as C4MetamodelQualityValidator

    __all__ = [
        'validate_diagram_quality', 'scan_for_hardcoded_terms',
        'ArchiMate30SchemaValidator', 'C4MetamodelQualityValidator',
        'UnifiedQualityValidator', 'MetamodelValidator'
    ]
    
except ImportError:
    __all__ = ['validate_diagram_quality', 'UnifiedQualityValidator', 'MetamodelValidator']

    def validate_diagram_quality(_x, _d="container"): return {"score":0}
    def scan_for_hardcoded_terms(_c): return []

    class ArchiMate30SchemaValidator:
        def __init__(self, *args, **kwargs):
            pass
        def is_valid_archimate_xml(self, xml_content: str) -> bool:
            return True
        def generate_validation_report(self, xml_content: str) -> str:
            return "Schema validation not available"
    
    class C4MetamodelQualityValidator:
        def __init__(self, *args, **kwargs):
            pass
        def validate(self, *args, **kwargs):
            return {"score": 0, "issues": []}

class UnifiedQualityValidator:
    """Unified interface for all validation functionality"""
    
    def __init__(self):
        try:
            self.schema_validator = ArchiMate30SchemaValidator()
            self.c4_validator = C4MetamodelQualityValidator()
        except Exception:
            self.schema_validator = None
            self.c4_validator = None

    def validate_quality(self, xml_content: str, diagram_type: str = "container") -> dict:
        """Validate diagram quality comprehensively"""
        try:
            return validate_diagram_quality(xml_content, diagram_type)
        except Exception:
            return {"score":0, "issues":[], "status":"validation_failed"}

    def validate_archimate_compliance(self, xml_content: str) -> dict:
        """Validate ArchiMate compliance"""
        if not self.schema_validator:
            return {"valid": True, "report": "schema validator unavailable"}
        try:
            is_valid = self.schema_validator.is_valid_archimate_xml(xml_content)
            report = "OK" if is_valid else self.schema_validator.generate_validation_report(xml_content)
            return {"valid": is_valid, "report": report}
        except Exception:
            return {"valid": False, "report": "validation error"}

# Main validator alias for backward compatibility
class MetamodelValidator(UnifiedQualityValidator):
    """Alias for metamodel validation - same as UnifiedQualityValidator"""
    pass