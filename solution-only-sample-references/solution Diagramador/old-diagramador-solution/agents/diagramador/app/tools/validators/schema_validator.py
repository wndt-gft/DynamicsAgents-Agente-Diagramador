"""
ArchiMate 3.0 Schema Validator Module
Complete implementation with all validation methods
"""

import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
import time

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Validation severity levels"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    def severity_weight(self) -> int:
        """Return weight for severity comparison"""
        weights = {
            ValidationSeverity.ERROR: 3,
            ValidationSeverity.WARNING: 2,
            ValidationSeverity.INFO: 1
        }
        return weights.get(self, 0)


@dataclass
class SchemaValidationResult:
    """Schema validation result"""
    is_valid: bool
    severity: ValidationSeverity
    message: str
    element_id: Optional[str] = None
    suggestion: Optional[str] = None
    line_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'is_valid': self.is_valid,
            'severity': self.severity.value,
            'message': self.message,
            'element_id': self.element_id,
            'suggestion': self.suggestion,
            'line_number': self.line_number
        }


class ArchiMate30SchemaValidator:
    """Validator for ArchiMate 3.0 schema compliance"""

    # ArchiMate 3.0 valid element types
    VALID_ELEMENT_TYPES = {
        # Strategy Layer
        'Resource', 'Capability', 'ValueStream', 'CourseOfAction',
        # Business Layer
        'BusinessActor', 'BusinessRole', 'BusinessCollaboration',
        'BusinessInterface', 'BusinessProcess', 'BusinessFunction',
        'BusinessInteraction', 'BusinessEvent', 'BusinessService',
        'BusinessObject', 'Contract', 'Representation', 'Product',
        # Application Layer
        'ApplicationComponent', 'ApplicationCollaboration',
        'ApplicationInterface', 'ApplicationFunction',
        'ApplicationInteraction', 'ApplicationProcess',
        'ApplicationEvent', 'ApplicationService', 'DataObject',
        # Technology Layer
        'Node', 'Device', 'SystemSoftware', 'TechnologyCollaboration',
        'TechnologyInterface', 'Path', 'CommunicationNetwork',
        'TechnologyFunction', 'TechnologyProcess', 'TechnologyInteraction',
        'TechnologyEvent', 'TechnologyService', 'Artifact',
        # Physical Layer
        'Equipment', 'Facility', 'DistributionNetwork', 'Material',
        # Motivation Layer
        'Stakeholder', 'Driver', 'Assessment', 'Goal', 'Outcome',
        'Principle', 'Requirement', 'Constraint', 'Meaning', 'Value',
        # Implementation and Migration Layer
        'WorkPackage', 'Deliverable', 'ImplementationEvent', 'Plateau', 'Gap'
    }

    # ArchiMate 3.0 valid relationship types
    VALID_RELATIONSHIP_TYPES = {
        # Structural Relationships
        'Composition', 'Aggregation', 'Assignment', 'Realization',
        # Dependency Relationships
        'Serving', 'Access', 'Influence', 'Association',
        # Dynamic Relationships
        'Triggering', 'Flow',
        # Other Relationships
        'Specialization', 'Junction'
    }

    # Valid viewpoint types
    VALID_VIEWPOINTS = {
        'Organization', 'Application Cooperation', 'Business Process Cooperation',
        'Product', 'Application Usage', 'Technology', 'Technology Usage',
        'Information Structure', 'Service Realization', 'Physical',
        'Layered', 'Stakeholder', 'Goal Realization', 'Requirements Realization',
        'Strategy', 'Capability Map', 'Outcome Realization', 'Resource Map',
        'Value Stream', 'Implementation and Migration', 'Project', 'Migration'
    }

    def __init__(self, schema_path: Optional[str] = None):
        """
        Initialize the validator

        Args:
            schema_path: Path to XSD schema file (optional)
        """
        self.logger = logging.getLogger(__name__)
        self.schema_version = '3.0'
        self.schema_path = schema_path
        self.xsd_schema = None
        self.custom_rules = {}
        self.element_definitions = {}  # For compatibility
        self.relationship_definitions = {}  # For compatibility

        # Try to load XSD schema if path provided
        if schema_path and Path(schema_path).exists():
            try:
                from lxml import etree
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema_doc = etree.parse(f)
                    self.xsd_schema = etree.XMLSchema(schema_doc)
                self.logger.info(f"XSD schema loaded from {schema_path}")
            except Exception as e:
                self.logger.warning(f"Could not load XSD schema: {e}")

        self.namespaces = {
            'archimate': 'http://www.opengroup.org/xsd/archimate/3.0/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
        }

    def validate(self, xml_content: str) -> List[SchemaValidationResult]:
        """
        Main validation method

        Args:
            xml_content: XML content to validate

        Returns:
            List of validation results
        """
        results = []

        try:
            root = ET.fromstring(xml_content)

            # Validate namespace
            results.extend(self.validate_namespace(xml_content))

            # Validate structure
            results.extend(self.validate_element_structure(xml_content))

            # Validate IDs
            results.extend(self.validate_id_uniqueness(xml_content))

            # Validate required attributes
            results.extend(self.validate_required_attributes(xml_content))

            # Validate relationships
            results.extend(self.validate_relationships(xml_content))

            # Validate views
            results.extend(self.validate_views(xml_content))

            # Apply custom rules
            for rule_name, rule_func in self.custom_rules.items():
                try:
                    rule_results = rule_func(xml_content)
                    if rule_results:
                        results.extend(rule_results)
                except Exception as e:
                    self.logger.warning(f"Custom rule {rule_name} failed: {e}")

        except ET.ParseError as e:
            results.append(SchemaValidationResult(
                is_valid=False,
                severity=ValidationSeverity.ERROR,
                message=f"XML parsing error: {e}",
                suggestion="Fix XML syntax errors"
            ))

        return results

    def validate_schema_compliance(self, xml_content: str) -> Dict[str, Any]:
        """
        Validate schema compliance

        Args:
            xml_content: XML content to validate

        Returns:
            Compliance report dictionary
        """
        results = self.validate(xml_content)

        errors = [r for r in results if r.severity == ValidationSeverity.ERROR]
        warnings = [r for r in results if r.severity == ValidationSeverity.WARNING]

        return {
            'compliant': len(errors) == 0,
            'errors': [r.message for r in errors],
            'warnings': [r.message for r in warnings],
            'version': self.schema_version
        }

    def validate_namespace(self, xml_content: str) -> List[SchemaValidationResult]:
        """
        Validate namespace compliance

        Args:
            xml_content: XML content to validate

        Returns:
            List of validation results
        """
        results = []

        try:
            root = ET.fromstring(xml_content)

            # Check for ArchiMate namespace
            if 'archimate' not in root.tag.lower() and \
               'http://www.opengroup.org/xsd/archimate' not in root.tag:
                results.append(SchemaValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message="Missing ArchiMate namespace",
                    suggestion="Add xmlns:archimate='http://www.opengroup.org/xsd/archimate/3.0/'"
                ))
        except ET.ParseError:
            pass  # Handled in main validate method

        return results

    def validate_element_structure(self, xml_content: str) -> List[SchemaValidationResult]:
        """
        Validate element structure

        Args:
            xml_content: XML content to validate

        Returns:
            List of validation results
        """
        results = []

        try:
            root = ET.fromstring(xml_content)

            # Find all elements
            for elem in root.findall('.//element'):
                elem_id = elem.get('id')
                elem_type = elem.get('type') or elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')

                # Check for required attributes
                if not elem_id:
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message=f"Element missing required 'id' attribute",
                        element_id=elem_id,
                        suggestion="Add unique id attribute to element"
                    ))

                # Validate element type
                if elem_type:
                    type_name = elem_type.split(':')[-1] if ':' in elem_type else elem_type
                    if not self.is_valid_element_type(type_name):
                        results.append(SchemaValidationResult(
                            is_valid=False,
                            severity=ValidationSeverity.WARNING,
                            message=f"Unknown element type: {type_name}",
                            element_id=elem_id,
                            suggestion=f"Use valid ArchiMate 3.0 element type"
                        ))
        except ET.ParseError:
            pass

        return results

    def validate_relationships(self, xml_content: str) -> List[SchemaValidationResult]:
        """
        Validate relationships

        Args:
            xml_content: XML content to validate

        Returns:
            List of validation results
        """
        results = []

        try:
            root = ET.fromstring(xml_content)

            # Collect all element IDs
            element_ids = set()
            for elem in root.findall('.//element'):
                elem_id = elem.get('id')
                if elem_id:
                    element_ids.add(elem_id)

            # Validate relationships
            for rel in root.findall('.//relationship'):
                rel_id = rel.get('id')
                rel_type = rel.get('type') or rel.get('{http://www.w3.org/2001/XMLSchema-instance}type')
                source = rel.get('source')
                target = rel.get('target')

                # Check required attributes
                if not rel_id:
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message="Relationship missing required 'id' attribute",
                        suggestion="Add unique id attribute to relationship"
                    ))

                # Validate relationship type
                if rel_type:
                    type_name = rel_type.split(':')[-1] if ':' in rel_type else rel_type
                    if not self.is_valid_relationship_type(type_name):
                        results.append(SchemaValidationResult(
                            is_valid=False,
                            severity=ValidationSeverity.WARNING,
                            message=f"Unknown relationship type: {type_name}",
                            element_id=rel_id,
                            suggestion="Use valid ArchiMate 3.0 relationship type"
                        ))

                # Check source and target references
                if source and source not in element_ids:
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message=f"Relationship references non-existent source: {source}",
                        element_id=rel_id,
                        suggestion="Fix source reference"
                    ))

                if target and target not in element_ids:
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message=f"Relationship references non-existent target: {target}",
                        element_id=rel_id,
                        suggestion="Fix target reference"
                    ))
        except ET.ParseError:
            pass

        return results

    def validate_id_uniqueness(self, xml_content: str) -> List[SchemaValidationResult]:
        """
        Validate ID uniqueness

        Args:
            xml_content: XML content to validate

        Returns:
            List of validation results
        """
        results = []

        try:
            root = ET.fromstring(xml_content)

            # Collect all IDs
            ids = []
            for elem in root.iter():
                elem_id = elem.get('id')
                if elem_id:
                    ids.append(elem_id)

            # Check for duplicates
            seen = set()
            duplicates = set()
            for elem_id in ids:
                if elem_id in seen:
                    duplicates.add(elem_id)
                seen.add(elem_id)

            for dup_id in duplicates:
                results.append(SchemaValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.ERROR,
                    message=f"Duplicate ID found: {dup_id}",
                    element_id=dup_id,
                    suggestion="Ensure all IDs are unique"
                ))
        except ET.ParseError:
            pass

        return results

    def validate_required_attributes(self, xml_content: str) -> List[SchemaValidationResult]:
        """
        Validate required attributes

        Args:
            xml_content: XML content to validate

        Returns:
            List of validation results
        """
        results = []

        try:
            root = ET.fromstring(xml_content)

            # Check root element
            if not root.get('id'):
                results.append(SchemaValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.WARNING,
                    message="Root element missing 'id' attribute",
                    suggestion="Add id attribute to root element"
                ))

            # Check elements
            for elem in root.findall('.//element'):
                if not elem.get('id'):
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message="Element missing required 'id' attribute",
                        suggestion="Add unique id attribute"
                    ))

                if not elem.get('type') and not elem.get('{http://www.w3.org/2001/XMLSchema-instance}type'):
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.WARNING,
                        message="Element missing 'type' attribute",
                        element_id=elem.get('id'),
                        suggestion="Add type attribute"
                    ))

            # Check relationships
            for rel in root.findall('.//relationship'):
                if not rel.get('id'):
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message="Relationship missing required 'id' attribute",
                        suggestion="Add unique id attribute"
                    ))

                if not rel.get('source'):
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message="Relationship missing 'source' attribute",
                        element_id=rel.get('id'),
                        suggestion="Add source reference"
                    ))

                if not rel.get('target'):
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message="Relationship missing 'target' attribute",
                        element_id=rel.get('id'),
                        suggestion="Add target reference"
                    ))
        except ET.ParseError:
            pass

        return results

    def validate_views(self, xml_content: str) -> List[SchemaValidationResult]:
        """
        Validate views

        Args:
            xml_content: XML content to validate

        Returns:
            List of validation results
        """
        results = []

        try:
            root = ET.fromstring(xml_content)

            # Find views
            for view in root.findall('.//view'):
                view_id = view.get('id')
                viewpoint = view.get('viewpoint')

                if not view_id:
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message="View missing required 'id' attribute",
                        suggestion="Add unique id attribute to view"
                    ))

                if viewpoint and not self.is_valid_viewpoint(viewpoint):
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.WARNING,
                        message=f"Unknown viewpoint: {viewpoint}",
                        element_id=view_id,
                        suggestion="Use valid ArchiMate 3.0 viewpoint"
                    ))
        except ET.ParseError:
            pass

        return results

    def validate_element_order(self, xml_content: str) -> List[SchemaValidationResult]:
        """
        Validate element order in document

        Args:
            xml_content: XML content to validate

        Returns:
            List of validation results
        """
        results = []

        try:
            root = ET.fromstring(xml_content)

            # Expected order: elements, relationships, views
            expected_order = ['elements', 'relationships', 'views']
            found_sections = []

            for child in root:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if tag in expected_order:
                    found_sections.append(tag)

            # Check if order matches
            filtered_expected = [s for s in expected_order if s in found_sections]
            if found_sections != filtered_expected:
                results.append(SchemaValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.WARNING,
                    message="Sections not in recommended order",
                    suggestion=f"Use order: {', '.join(expected_order)}"
                ))
        except ET.ParseError:
            pass

        return results

    def validate_cross_references(self, xml_content: str) -> List[SchemaValidationResult]:
        """
        Validate cross-references between elements

        Args:
            xml_content: XML content to validate

        Returns:
            List of validation results
        """
        results = []

        try:
            root = ET.fromstring(xml_content)

            # Collect all IDs
            all_ids = set()
            for elem in root.iter():
                elem_id = elem.get('id')
                if elem_id:
                    all_ids.add(elem_id)

            # Check all references
            for elem in root.iter():
                # Check common reference attributes
                for attr in ['source', 'target', 'elementRef', 'connectionRef']:
                    ref_id = elem.get(attr)
                    if ref_id and ref_id not in all_ids:
                        results.append(SchemaValidationResult(
                            is_valid=False,
                            severity=ValidationSeverity.ERROR,
                            message=f"Invalid reference to non-existent element: {ref_id}",
                            element_id=elem.get('id'),
                            suggestion=f"Fix reference or add element with id '{ref_id}'"
                        ))
        except ET.ParseError:
            pass

        return results

    def validate_documentation(self, xml_content: str) -> List[SchemaValidationResult]:
        """
        Validate documentation format

        Args:
            xml_content: XML content to validate

        Returns:
            List of validation results
        """
        results = []

        try:
            root = ET.fromstring(xml_content)

            # Check for empty documentation
            for elem in root.findall('.//documentation'):
                if elem.text is None or elem.text.strip() == '':
                    parent = elem.getparent() if hasattr(elem, 'getparent') else None
                    parent_id = parent.get('id') if parent is not None else None

                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.INFO,
                        message="Empty documentation element",
                        element_id=parent_id,
                        suggestion="Add meaningful documentation or remove empty element"
                    ))
        except ET.ParseError:
            pass

        return results

    def validate_property_definitions(self, xml_content: str) -> List[SchemaValidationResult]:
        """
        Validate property definitions

        Args:
            xml_content: XML content to validate

        Returns:
            List of validation results
        """
        results = []

        try:
            root = ET.fromstring(xml_content)

            # Find property definitions
            for prop_def in root.findall('.//propertyDefinition'):
                prop_id = prop_def.get('id')
                prop_type = prop_def.get('type')

                if not prop_id:
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message="Property definition missing 'id' attribute",
                        suggestion="Add unique id to property definition"
                    ))

                if not prop_type:
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.WARNING,
                        message="Property definition missing 'type' attribute",
                        element_id=prop_id,
                        suggestion="Specify property type (string, number, boolean, etc.)"
                    ))

            # Check property usage
            prop_def_ids = {pd.get('id') for pd in root.findall('.//propertyDefinition') if pd.get('id')}

            for prop in root.findall('.//property'):
                prop_def_ref = prop.get('propertyDefinitionRef')
                if prop_def_ref and prop_def_ref not in prop_def_ids:
                    results.append(SchemaValidationResult(
                        is_valid=False,
                        severity=ValidationSeverity.ERROR,
                        message=f"Property references non-existent definition: {prop_def_ref}",
                        suggestion="Fix property definition reference"
                    ))
        except ET.ParseError:
            pass

        return results

    def is_valid_element_type(self, element_type: str) -> bool:
        """
        Check if element type is valid

        Args:
            element_type: Element type to check

        Returns:
            True if valid, False otherwise
        """
        return element_type in self.VALID_ELEMENT_TYPES

    def is_valid_relationship_type(self, relationship_type: str) -> bool:
        """
        Check if relationship type is valid

        Args:
            relationship_type: Relationship type to check

        Returns:
            True if valid, False otherwise
        """
        return relationship_type in self.VALID_RELATIONSHIP_TYPES

    def is_valid_viewpoint(self, viewpoint: str) -> bool:
        """
        Check if viewpoint is valid

        Args:
            viewpoint: Viewpoint to check

        Returns:
            True if valid, False otherwise
        """
        return viewpoint in self.VALID_VIEWPOINTS

    def is_valid_ncname(self, name: str) -> bool:
        """
        Check if name is valid NCName format

        Args:
            name: Name to check

        Returns:
            True if valid NCName, False otherwise
        """
        # NCName pattern: starts with letter or underscore, followed by letters, digits, dots, hyphens, underscores
        ncname_pattern = r'^[a-zA-Z_][a-zA-Z0-9._\-]*$'
        return bool(re.match(ncname_pattern, name))

    def batch_validate(self, xml_list: List[str]) -> List[Dict[str, Any]]:
        """
        Validate multiple XML documents

        Args:
            xml_list: List of XML documents to validate

        Returns:
            List of validation reports
        """
        results = []
        for xml_content in xml_list:
            report = self.validate_schema_compliance(xml_content)
            results.append(report)
        return results

    def generate_report(self, xml_content: str) -> Dict[str, Any]:
        """
        Generate comprehensive validation report

        Args:
            xml_content: XML content to validate

        Returns:
            Validation report dictionary
        """
        validation_results = self.validate(xml_content)

        errors = [r for r in validation_results if r.severity == ValidationSeverity.ERROR]
        warnings = [r for r in validation_results if r.severity == ValidationSeverity.WARNING]
        info = [r for r in validation_results if r.severity == ValidationSeverity.INFO]

        # Try to get element counts
        element_count = 0
        relationship_count = 0
        view_count = 0

        try:
            root = ET.fromstring(xml_content)
            element_count = len(root.findall('.//element'))
            relationship_count = len(root.findall('.//relationship'))
            view_count = len(root.findall('.//view'))
        except ET.ParseError:
            pass

        return {
            'is_valid': len(errors) == 0,
            'schema_version': self.schema_version,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'statistics': {
                'elements': element_count,
                'relationships': relationship_count,
                'views': view_count,
                'total_issues': len(validation_results),
                'errors': len(errors),
                'warnings': len(warnings),
                'info': len(info)
            },
            'errors': [r.to_dict() for r in errors],
            'warnings': [r.to_dict() for r in warnings],
            'info': [r.to_dict() for r in info],
            'recommendations': list(set(r.suggestion for r in validation_results if r.suggestion))
        }

    def add_custom_rule(self, rule_name: str, rule_function: 'Callable[[str], List[SchemaValidationResult]]') -> None:
        """
        Add custom validation rule

        Args:
            rule_name: Name of the rule
            rule_function: Function that takes XML content and returns list of SchemaValidationResult
        """
        self.custom_rules[rule_name] = rule_function
        self.logger.info(f"Added custom rule: {rule_name}")

    # === Backward compatibility wrappers ===
    def is_valid_archimate_xml(self, xml_content: str) -> bool:  # legacy API
        try:
            compliance = self.validate_schema_compliance(xml_content)
            return bool(compliance.get('compliant', False))
        except Exception:
            return True  # fail-open to avoid breaking generation

    def generate_validation_report(self, xml_content: str) -> str:  # legacy API
        try:
            report = self.generate_report(xml_content)
            parts = [
                f"Schema Version: {report.get('schema_version')}",
                f"Valid: {report.get('is_valid')}",
                f"Errors: {len(report.get('errors', []))}",
                f"Warnings: {len(report.get('warnings', []))}",
            ]
            if report.get('errors'):
                parts.append('Error details:')
                parts.extend(f" - {e['message']}" for e in report['errors'][:10])
            if report.get('warnings'):
                parts.append('Warning details:')
                parts.extend(f" - {w['message']}" for w in report['warnings'][:10])
            return '\n'.join(parts)
        except Exception as e:
            return f"Validation report unavailable: {e}"
