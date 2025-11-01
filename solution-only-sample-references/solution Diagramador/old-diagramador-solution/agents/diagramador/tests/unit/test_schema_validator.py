#!/usr/bin/env python
"""
Simple test to verify Schema Validator is working
"""

import sys
import os
from pathlib import Path
import unittest

# Setup paths
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "app"))

print("=" * 60)
print("Simple Schema Validator Test")
print("=" * 60)

# Import the validator
try:
    from app.tools.validators.schema_validator import (
        ArchiMate30SchemaValidator,
        SchemaValidationResult,
        ValidationSeverity
    )
    print("✅ Successfully imported Schema Validator")
except ImportError as e:
    print(f"❌ Failed to import: {e}")
    sys.exit(1)


class TestBasicSchemaValidator(unittest.TestCase):
    """Basic tests for Schema Validator"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.validator = ArchiMate30SchemaValidator()
        
    def test_initialization(self):
        """Test validator initialization"""
        self.assertIsNotNone(self.validator)
        self.assertEqual(self.validator.schema_version, '3.0')
        print("  ✅ test_initialization passed")
    
    def test_validate_valid_xml(self):
        """Test validation of valid XML"""
        valid_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <archimate:model xmlns:archimate="http://www.opengroup.org/xsd/archimate/3.0/">
            <elements>
                <element id="elem1" type="ApplicationComponent">
                    <n>Test Component</n>
                </element>
            </elements>
        </archimate:model>"""
        
        results = self.validator.validate(valid_xml)
        errors = [r for r in results if r.severity == ValidationSeverity.ERROR]
        
        self.assertEqual(len(errors), 0, f"Should have no errors, but got: {[e.message for e in errors]}")
        print("  ✅ test_validate_valid_xml passed")
    
    def test_validate_invalid_xml(self):
        """Test validation of invalid XML"""
        invalid_xml = "not valid xml"
        
        results = self.validator.validate(invalid_xml)
        errors = [r for r in results if r.severity == ValidationSeverity.ERROR]
        
        self.assertGreater(len(errors), 0, "Should have errors for invalid XML")
        print("  ✅ test_validate_invalid_xml passed")
    
    def test_batch_validate(self):
        """Test batch validation"""
        xml_list = [
            """<?xml version="1.0" encoding="UTF-8"?>
            <archimate:model xmlns:archimate="http://www.opengroup.org/xsd/archimate/3.0/">
                <elements>
                    <element id="elem1" type="ApplicationComponent">
                        <n>Component 1</n>
                    </element>
                </elements>
            </archimate:model>""",
            """<?xml version="1.0" encoding="UTF-8"?>
            <archimate:model xmlns:archimate="http://www.opengroup.org/xsd/archimate/3.0/">
                <elements>
                    <element id="elem2" type="BusinessActor">
                        <n>Actor 1</n>
                    </element>
                </elements>
            </archimate:model>"""
        ]
        
        results = self.validator.batch_validate(xml_list)
        
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r['compliant'] for r in results))
        print("  ✅ test_batch_validate passed")
    
    def test_is_valid_element_type(self):
        """Test element type validation"""
        valid_types = ['ApplicationComponent', 'BusinessActor', 'DataObject']
        invalid_types = ['InvalidType', 'Random', '']
        
        for valid_type in valid_types:
            self.assertTrue(self.validator.is_valid_element_type(valid_type))
        
        for invalid_type in invalid_types:
            self.assertFalse(self.validator.is_valid_element_type(invalid_type))
        
        print("  ✅ test_is_valid_element_type passed")
    
    def test_generate_report(self):
        """Test report generation"""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <archimate:model xmlns:archimate="http://www.opengroup.org/xsd/archimate/3.0/">
            <elements>
                <element id="elem1" type="ApplicationComponent">
                    <n>Component</n>
                </element>
            </elements>
            <relationships>
                <relationship id="rel1" type="Flow" source="elem1" target="elem1"/>
            </relationships>
        </archimate:model>"""
        
        report = self.validator.generate_report(xml)
        
        self.assertIsInstance(report, dict)
        self.assertIn('is_valid', report)
        self.assertIn('statistics', report)
        self.assertEqual(report['statistics']['elements'], 1)
        self.assertEqual(report['statistics']['relationships'], 1)
        print("  ✅ test_generate_report passed")
    
    def test_custom_rule(self):
        """Test adding custom rule"""
        def custom_rule(xml_content):
            results = []
            if 'TEST' not in xml_content:
                results.append(SchemaValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.WARNING,
                    message="Missing TEST keyword",
                    suggestion="Add TEST keyword"
                ))
            return results
        
        self.validator.add_custom_rule('test_rule', custom_rule)
        
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <archimate:model xmlns:archimate="http://www.opengroup.org/xsd/archimate/3.0/">
            <elements>
                <element id="elem1" type="ApplicationComponent">
                    <n>Component</n>
                </element>
            </elements>
        </archimate:model>"""
        
        results = self.validator.validate(xml)
        warnings = [r for r in results if r.severity == ValidationSeverity.WARNING]
        
        self.assertTrue(any('TEST' in w.message for w in warnings))
        print("  ✅ test_custom_rule passed")
    
    def test_severity_weight(self):
        """Test severity weight method"""
        self.assertEqual(ValidationSeverity.ERROR.severity_weight(), 3)
        self.assertEqual(ValidationSeverity.WARNING.severity_weight(), 2)
        self.assertEqual(ValidationSeverity.INFO.severity_weight(), 1)
        print("  ✅ test_severity_weight passed")


if __name__ == '__main__':
    print("\nRunning tests...")
    print("-" * 40)
    
    # Run tests
    suite = unittest.TestLoader().loadTestsFromTestCase(TestBasicSchemaValidator)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("-" * 40)
    print(f"\n✅ Tests run: {result.testsRun}")
    print(f"❌ Failures: {len(result.failures)}")
    print(f"❌ Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n🎉 All tests passed!")
    else:
        print("\n❌ Some tests failed")
        if result.failures:
            print("\nFailures:")
            for test, trace in result.failures:
                print(f"  - {test}: {trace.split(chr(10))[0]}")
        if result.errors:
            print("\nErrors:")
            for test, trace in result.errors:
                print(f"  - {test}: {trace.split(chr(10))[0]}")