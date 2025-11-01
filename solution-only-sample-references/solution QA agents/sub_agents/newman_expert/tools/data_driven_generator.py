"""Newman Data-Driven Test Generator - Generates data-driven test configurations."""

import json
from typing import Dict, Any, List


def generate_data_driven_tests(domain: str, endpoints: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate data-driven test configurations."""

    test_data = {
        "test_cases": [
            {
                "name": "Valid data test",
                "data": {
                    "name": "Test Item 1",
                    "status": "active",
                    "value": 100
                },
                "expected_status": 200
            },
            {
                "name": "Invalid data test",
                "data": {
                    "name": "",
                    "status": "invalid",
                    "value": -1
                },
                "expected_status": 400
            },
            {
                "name": "Boundary test",
                "data": {
                    "name": "A" * 255,
                    "status": "active",
                    "value": 999999
                },
                "expected_status": 200
            }
        ]
    }

    return {
        "data_file": f"{domain}-test-data.json",
        "data_content": json.dumps(test_data, indent=2),
        "usage_example": f"""
// Example: Data-driven test in Postman
const testData = pm.iterationData.get('test_cases');
pm.test('Data-driven test: ' + testData.name, function () {{
    pm.response.to.have.status(testData.expected_status);
}});
"""
    }
