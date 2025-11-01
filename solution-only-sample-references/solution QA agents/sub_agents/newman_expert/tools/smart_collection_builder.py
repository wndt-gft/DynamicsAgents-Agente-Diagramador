# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Smart Collection Builder - Builds Newman collections from OpenAPI + Zephyr scenarios.

This module intelligently parses OpenAPI specifications and Zephyr test scenarios
to create production-ready Postman collections with proper structure and assertions.
"""

import json
import yaml
import re
from copy import deepcopy
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse


def build_smart_newman_collection(
    openapi_spec: Optional[str] = None,
    zephyr_scenarios: Optional[str] = None,
    api_specification: Optional[str] = None,
    test_scenarios: Optional[List[str]] = None,
    domain: str = "API",
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build a smart Newman collection from OpenAPI and Zephyr inputs.

    Args:
        openapi_spec: OpenAPI YAML/JSON specification
        zephyr_scenarios: Zephyr test scenarios JSON
        api_specification: Alternative API specification text
        test_scenarios: Alternative test scenarios list
        domain: API domain name
        config: Additional configuration

    Returns:
        Complete Postman collection JSON
    """
    config = config or {}

    # Parse inputs with improved validation
    openapi_data = _parse_openapi(openapi_spec or api_specification)
    zephyr_data = _parse_zephyr(zephyr_scenarios, test_scenarios)

    # Extract base information with fallback protection
    collection_name = openapi_data.get("info", {}).get("title", f"{domain} API")
    collection_desc = openapi_data.get("info", {}).get("description", "API test collection")
    base_url = _extract_base_url(openapi_data)

    # Build collection structure
    collection = {
        "info": {
            "name": collection_name,
            "description": collection_desc,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "variable": [
            {
                "key": "base_url",
                "value": base_url,
                "type": "string"
            },
            {
                "key": "access_token",
                "value": "",
                "type": "string"
            }
        ],
        "auth": _build_collection_auth(openapi_data),
        "event": _build_collection_events(),
        "item": []
    }

    # Organize test cases by folder with improved structure
    folders = _organize_test_cases_by_folder(zephyr_data)

    # Sort folders to ensure Authentication comes first
    folder_order = ["Authentication", "Accounts", "Transfers", "E2E"]
    sorted_folders = sorted(
        folders.items(),
        key=lambda x: folder_order.index(x[0]) if x[0] in folder_order else 999
    )

    # Build requests for each folder
    for folder_name, test_cases in sorted_folders:
        folder_items = []

        for test_case in test_cases:
            # Find matching endpoint from OpenAPI with better matching
            endpoint_info = _find_endpoint_for_test_case(test_case, openapi_data)

            # Build request from test case with enhanced validation
            request_item = _build_request_from_test_case(
                test_case,
                endpoint_info,
                openapi_data
            )

            if request_item:  # Only add valid requests
                folder_items.append(request_item)

        # Add folder to collection only if it has items
        if folder_items:
            collection["item"].append({
                "name": folder_name,
                "item": folder_items,
                "description": f"Tests for {folder_name}"
            })

    return collection


def _parse_openapi(spec: Optional[str]) -> Dict[str, Any]:
    """Parse OpenAPI specification from YAML or JSON with robust error handling."""
    if not spec:
        return {}

    try:
        # Try YAML first (most common for OpenAPI)
        return yaml.safe_load(spec)
    except yaml.YAMLError:
        try:
            # Try JSON
            return json.loads(spec)
        except json.JSONDecodeError:
            # Return empty dict if parsing fails
            return {}


def _parse_zephyr(zephyr_json: Optional[str], test_list: Optional[List[str]]) -> Dict[str, Any]:
    """Parse Zephyr test scenarios with improved structure handling."""
    if zephyr_json:
        try:
            parsed = json.loads(zephyr_json)
            # Handle both direct array and nested structure
            if isinstance(parsed, dict) and "test_cases" in parsed:
                return _normalize_structured_test_suite(parsed)
            elif isinstance(parsed, list):
                return _normalize_structured_test_suite({"test_cases": parsed})
            else:
                return {"test_cases": []}
        except json.JSONDecodeError:
            return {"test_cases": []}

    if test_list:
        # Convert simple list to structured format
        return _normalize_structured_test_suite(
            {
                "test_cases": [
                    {
                        "id": f"TC-{i+1:03d}",
                        "name": scenario,
                        "folder": "General Tests",
                        "test_steps": [{"action": scenario}],
                        "expected_results": [],
                    }
                    for i, scenario in enumerate(test_list)
                ]
            }
        )

    return {"test_cases": []}


def _normalize_structured_test_suite(raw_suite: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure test cases expose the fields expected by the builder."""

    normalized_cases: List[Dict[str, Any]] = []
    for test_case in raw_suite.get("test_cases", []):
        if not isinstance(test_case, dict):
            continue

        case = deepcopy(test_case)

        if "id" not in case and case.get("key"):
            case["id"] = case["key"]

        request_def = case.get("request")
        if isinstance(request_def, dict):
            method = request_def.get("method", "GET").upper()
            path = request_def.get("path", "/")
            step: Dict[str, Any] = {"action": f"{method} {path}"}
            if request_def.get("body") is not None:
                step["data"] = request_def["body"]
            if request_def.get("headers"):
                step["headers"] = request_def["headers"]
            case.setdefault("test_steps", [])
            if step not in case["test_steps"]:
                case["test_steps"].insert(0, step)

        tests_def = case.get("tests")
        if isinstance(tests_def, dict):
            expected: List[str] = list(case.get("expected_results", []) or [])
            status = tests_def.get("status_code")
            if status is not None:
                expected.append(f"Status {status}")
            response_time = tests_def.get("response_time")
            if response_time is not None:
                expected.append(f"Response time < {response_time}ms")
            for snippet in tests_def.get("body_checks", []) or []:
                expected.append(str(snippet))
            for snippet in tests_def.get("header_checks", []) or []:
                expected.append(str(snippet))
            if tests_def.get("chaining"):
                expected.append("Chaining dynamic data")
            case["expected_results"] = expected

        normalized_cases.append(case)

    return {"test_cases": normalized_cases}


def _extract_base_url(openapi_data: Dict[str, Any]) -> str:
    """Extract base URL from OpenAPI servers with validation."""
    servers = openapi_data.get("servers", [])
    if servers and isinstance(servers, list) and len(servers) > 0:
        url = servers[0].get("url", "")
        if url and url.startswith("http"):
            return url

    # Fallback: construct from host and basePath (OpenAPI 2.0)
    host = openapi_data.get("host", "")
    base_path = openapi_data.get("basePath", "")
    schemes = openapi_data.get("schemes", ["https"])

    if host:
        return f"{schemes[0]}://{host}{base_path}"

    return "https://api.example.com"


def _build_collection_auth(openapi_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build collection-level authentication from OpenAPI security schemes."""
    security_schemes = openapi_data.get("components", {}).get("securitySchemes", {})

    # Look for bearer token auth (most common for modern APIs)
    for scheme_name, scheme_data in security_schemes.items():
        if scheme_data.get("type") == "http" and scheme_data.get("scheme") == "bearer":
            return {
                "type": "bearer",
                "bearer": [
                    {
                        "key": "token",
                        "value": "{{access_token}}",
                        "type": "string"
                    }
                ]
            }
        elif scheme_data.get("type") == "apiKey":
            return {
                "type": "apikey",
                "apikey": [
                    {"key": "key", "value": scheme_data.get("name", "Authorization"), "type": "string"},
                    {"key": "value", "value": "{{api_key}}", "type": "string"},
                    {"key": "in", "value": scheme_data.get("in", "header"), "type": "string"}
                ]
            }

    return {"type": "noauth"}


def _build_collection_events() -> List[Dict[str, Any]]:
    """Build collection-level pre-request and test scripts."""
    return [
        {
            "listen": "prerequest",
            "script": {
                "type": "text/javascript",
                "exec": [
                    "// Collection-level pre-request script",
                    "// Set timestamp for all requests",
                    "pm.collectionVariables.set('timestamp', new Date().toISOString());",
                    ""
                ]
            }
        },
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": [
                    "// Collection-level test script",
                    "// Log response time",
                    "console.log('Response time: ' + pm.response.responseTime + 'ms');",
                    ""
                ]
            }
        }
    ]


def _organize_test_cases_by_folder(zephyr_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Organize test cases into folders based on their folder path or labels."""
    folders = {}
    test_cases = zephyr_data.get("test_cases", [])

    for test_case in test_cases:
        # Extract folder name from folder field (remove leading slash)
        folder = test_case.get("folder", "").strip("/")

        if not folder:
            # Try to infer from labels
            labels = test_case.get("labels", [])
            if "auth" in labels or "authentication" in labels:
                folder = "Authentication"
            elif "account" in labels or "accounts" in labels:
                folder = "Accounts"
            elif "transfer" in labels or "transfers" in labels:
                folder = "Transfers"
            elif "e2e" in labels or "end-to-end" in labels:
                folder = "E2E"
            else:
                folder = "General Tests"

        if folder not in folders:
            folders[folder] = []

        folders[folder].append(test_case)

    return folders


def _find_endpoint_for_test_case(test_case: Dict[str, Any], openapi_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Find the matching OpenAPI endpoint for a test case with improved parsing."""
    test_steps = test_case.get("test_steps", [])
    if not test_steps:
        return None

    # Extract HTTP method and path from first test step
    first_step = test_steps[0]
    action = first_step.get("action", "")

    # Improved regex parsing for action
    method = None
    path = None

    # Match patterns like "Enviar POST /auth/login", "POST /auth/login", "GET /accounts/{id}"
    method_pattern = r'\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b'
    path_pattern = r'(/[a-zA-Z0-9\-\_/\{\}]*)'

    method_match = re.search(method_pattern, action, re.IGNORECASE)
    path_match = re.search(path_pattern, action)

    if method_match:
        method = method_match.group(1).upper()
    if path_match:
        path = path_match.group(1)

    if not method or not path:
        return None

    # Find in OpenAPI paths with flexible matching
    paths = openapi_data.get("paths", {})

    # Direct match first
    if path in paths:
        endpoint_data = paths[path].get(method.lower(), {})
        if endpoint_data:
            return {
                "method": method,
                "path": path,
                "operationId": endpoint_data.get("operationId"),
                "summary": endpoint_data.get("summary"),
                "parameters": endpoint_data.get("parameters", []),
                "requestBody": endpoint_data.get("requestBody"),
                "responses": endpoint_data.get("responses", {}),
                "security": endpoint_data.get("security", None)
            }

    # Try to match with path parameters (e.g., /accounts/{account_id} matches /accounts/12345-6)
    for openapi_path, path_data in paths.items():
        if method.lower() in path_data:
            # Convert OpenAPI path pattern to regex
            pattern = re.sub(r'\{[^}]+\}', r'[^/]+', openapi_path)
            if re.fullmatch(pattern, path):
                endpoint_data = path_data[method.lower()]
                return {
                    "method": method,
                    "path": openapi_path,  # Use OpenAPI path with {parameters}
                    "operationId": endpoint_data.get("operationId"),
                    "summary": endpoint_data.get("summary"),
                    "parameters": endpoint_data.get("parameters", []),
                    "requestBody": endpoint_data.get("requestBody"),
                    "responses": endpoint_data.get("responses", {}),
                    "security": endpoint_data.get("security", None)
                }

    return None


def _build_request_from_test_case(
    test_case: Dict[str, Any],
    endpoint_info: Optional[Dict[str, Any]],
    openapi_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Build a Postman request item from a test case and endpoint info."""

    test_id = test_case.get("id", "")
    test_name = test_case.get("name", "Test")
    test_steps = test_case.get("test_steps", [])
    expected_results = test_case.get("expected_results", [])
    preconditions = test_case.get("preconditions", [])

    # Determine method and path
    if endpoint_info:
        method = endpoint_info["method"]
        path = endpoint_info["path"]
    else:
        # Try to extract from test steps if endpoint not found
        if not test_steps:
            return None

        action = test_steps[0].get("action", "")
        method_match = re.search(r'\b(GET|POST|PUT|DELETE|PATCH)\b', action, re.IGNORECASE)
        path_match = re.search(r'(/[a-zA-Z0-9\-\_/\{\}]+)', action)

        if not method_match or not path_match:
            return None

        method = method_match.group(1).upper()
        path = path_match.group(1)

    request_def = test_case.get("request")
    if isinstance(request_def, dict):
        method = request_def.get("method", method).upper()
        path = request_def.get("path", path)

    # Build request
    request = {
        "name": f"{test_id}: {test_name}" if test_id else test_name,
        "request": {
            "method": method,
            "header": _build_request_headers(test_case, endpoint_info),
            "url": _build_request_url(path, request_def.get("query") if isinstance(request_def, dict) else None)
        },
        "event": []
    }

    # Add request body if POST/PUT/PATCH
    if method in ["POST", "PUT", "PATCH"]:
        body = _build_request_body(test_case, endpoint_info, openapi_data)
        if body:
            request["request"]["body"] = body

    # Configure auth for this specific request
    request["request"]["auth"] = _build_request_auth(test_case, endpoint_info)

    # Add pre-request script if needed
    pre_request = _build_pre_request_script(test_case, endpoint_info)
    if pre_request:
        request["event"].append({
            "listen": "prerequest",
            "script": {
                "type": "text/javascript",
                "exec": pre_request
            }
        })

    # Add test script with specific assertions
    if isinstance(test_case.get("tests"), dict):
        test_script = _build_structured_test_script(
            test_case,
            endpoint_info,
            openapi_data,
        )
    else:
        test_script = _build_test_script(
            test_case,
            endpoint_info,
            expected_results,
            openapi_data,
        )
    if test_script:
        request["event"].append({
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": test_script
            }
        })

    return request


def _build_request_url(path: str, query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build Postman URL object from path."""
    if not path:
        path = "/"

    raw_path = path.strip()
    if raw_path.startswith("http://") or raw_path.startswith("https://"):
        parsed = urlparse(raw_path)
        raw = raw_path
        host = [part for part in parsed.netloc.split(".") if part]
        path_segments = [seg for seg in parsed.path.strip("/").split("/") if seg]
    else:
        if raw_path.startswith("{{"):
            raw = raw_path
            stripped = raw_path.replace("{{base_url}}", "")
            path_segments = [seg for seg in stripped.strip("/").split("/") if seg]
        else:
            raw = "{{base_url}}" + (raw_path if raw_path.startswith("/") else f"/{raw_path}")
            path_segments = [seg for seg in raw_path.strip("/").split("/") if seg]
        host = ["{{base_url}}"]

    url: Dict[str, Any] = {"raw": raw, "host": host, "path": path_segments}

    if isinstance(query, dict) and query:
        url["query"] = [
            {"key": key, "value": str(value)}
            for key, value in query.items()
        ]

    return url


def _build_request_auth(
    test_case: Dict[str, Any],
    endpoint_info: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Determine if this request should override collection-level auth."""
    request_def = test_case.get("request") or {}
    auth_setting = str(request_def.get("auth", "")).lower()
    if auth_setting in {"none", "noauth"}:
        return {"type": "noauth"}

    if endpoint_info and endpoint_info.get("security") is not None:
        # If security is explicitly empty array in OpenAPI, no auth required
        if endpoint_info["security"] == []:
            return {"type": "noauth"}

    # Otherwise inherit from collection
    return {"type": "inherit"}


def _build_request_headers(test_case: Dict[str, Any], endpoint_info: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Build request headers with proper defaults."""
    headers: List[Dict[str, str]] = []

    request_def = test_case.get("request") or {}
    request_headers = request_def.get("headers")
    if isinstance(request_headers, dict):
        for key, value in request_headers.items():
            headers.append({
                "key": key,
                "value": str(value),
                "type": "text",
            })

    # Add Content-Type for requests with body
    test_steps = test_case.get("test_steps", [])
    has_body_data = bool(test_steps and "data" in test_steps[0])
    if not has_body_data and isinstance(request_def.get("body"), dict):
        has_body_data = True

    if has_body_data and not any(h["key"].lower() == "content-type" for h in headers):
        headers.append({
            "key": "Content-Type",
            "value": "application/json",
            "type": "text"
        })

    if not any(h["key"].lower() == "accept" for h in headers):
        headers.append({
            "key": "Accept",
            "value": "application/json",
            "type": "text",
        })

    # Check if test step specifies custom headers
    for step in test_steps:
        if "headers" in step and isinstance(step["headers"], dict):
            for key, value in step["headers"].items():
                # Use Postman variables if value looks like it should be dynamic
                value_str = str(value)
                if "guid" in value_str.lower() or "uuid" in value_str.lower():
                    value = "{{$guid}}"

                final_value = value if value == "{{$guid}}" else value_str

                headers.append({
                    "key": key,
                    "value": final_value,
                    "type": "text"
                })

    return headers


def _build_request_body(
    test_case: Dict[str, Any],
    endpoint_info: Optional[Dict[str, Any]],
    openapi_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Build request body from test case data with schema validation."""
    test_steps = test_case.get("test_steps", [])

    for step in test_steps:
        if "data" in step and step["data"]:
            body_data = step["data"]

            # Format as pretty JSON
            return {
                "mode": "raw",
                "raw": json.dumps(body_data, indent=2),
                "options": {
                    "raw": {
                        "language": "json"
                    }
                }
            }

    # If no data in test steps, inspect request definition directly
    request_def = test_case.get("request") or {}
    if isinstance(request_def.get("body"), (dict, list)):
        return {
            "mode": "raw",
            "raw": json.dumps(request_def["body"], indent=2),
            "options": {"raw": {"language": "json"}},
        }

    # If no data in test steps, try to get example from OpenAPI
    if endpoint_info and endpoint_info.get("requestBody"):
        request_body_spec = endpoint_info["requestBody"]
        content = request_body_spec.get("content", {})
        json_content = content.get("application/json", {})

        if "example" in json_content:
            return {
                "mode": "raw",
                "raw": json.dumps(json_content["example"], indent=2),
                "options": {"raw": {"language": "json"}}
            }

        # Try to get example from examples
        examples = json_content.get("examples", {})
        if examples:
            first_example = next(iter(examples.values()))
            if "value" in first_example:
                return {
                    "mode": "raw",
                    "raw": json.dumps(first_example["value"], indent=2),
                    "options": {"raw": {"language": "json"}}
                }

    return None


def _build_test_script(
    test_case: Dict[str, Any],
    endpoint_info: Optional[Dict[str, Any]],
    expected_results: List[str],
    openapi_data: Dict[str, Any]
) -> List[str]:
    """Build test script with specific assertions based on expected results - CRITICAL FOR ACCURACY."""
    script_lines = [
        f"// Test: {test_case.get('name', 'Test')}",
        f"// ID: {test_case.get('id', 'N/A')}",
        ""
    ]

    # Parse expected results for specific assertions
    status_code = None
    should_store_token = False
    required_fields = []
    field_value_checks = {}  # {field: expected_value}
    enum_checks = {}  # {field: [allowed_values]}
    error_validation = False
    schema_validation_needed = False

    for result in expected_results:
        result_lower = result.lower()

        # Extract status code with improved pattern matching
        status_match = re.search(r'\b(200|201|204|400|401|403|404|422|500|502|503)\b', result)
        if status_match:
            status_code = status_match.group(1)

        # Check for token storage requirement
        if "access_token" in result_lower or "bearer" in result_lower:
            should_store_token = True

        # Extract required fields: "Response contém X" or "Contains X"
        if "contém" in result_lower or "contains" in result_lower:
            # Extract field names in single quotes, property names, or known patterns
            field_patterns = [
                r"'([a-z_]+)'",
                r"contém\s+([a-z_]+)",
                r"contains\s+([a-z_]+)"
            ]
            for pattern in field_patterns:
                matches = re.findall(pattern, result_lower)
                required_fields.extend(matches)

        # Extract field value checks: "X é 'value'" or "X: 'value'"
        value_check_match = re.search(r"([a-z_]+)\s+(?:é|:)\s+'([^']+)'", result_lower)
        if value_check_match:
            field, value = value_check_match.groups()
            field_value_checks[field] = value

        # Extract enum checks: "X é Y ou Z"
        enum_match = re.search(r"([a-z_]+)\s+é\s+'?([a-z]+)'?\s+ou\s+'?([a-z]+)'?", result_lower)
        if enum_match:
            field, val1, val2 = enum_match.groups()
            enum_checks[field] = [val1, val2]

        # Check for error validation
        if "error" in result_lower or "erro" in result_lower:
            error_validation = True

        # Check for schema validation needs
        if "formato" in result_lower or "format" in result_lower or "type" in result_lower:
            schema_validation_needed = True

    # Generate status code assertion (ALWAYS FIRST)
    if status_code:
        script_lines.extend([
            f"pm.test('Status code is {status_code}', function () {{",
            f"    pm.response.to.have.status({status_code});",
            "});",
            ""
        ])
    else:
        # Default to checking for successful response
        script_lines.extend([
            "pm.test('Status code is successful', function () {",
            "    pm.response.to.be.success;",
            "});",
            ""
        ])

    # Validate response time (ALWAYS INCLUDE)
    script_lines.extend([
        "pm.test('Response time is acceptable', function () {",
        "    pm.expect(pm.response.responseTime).to.be.below(5000);",
        "});",
        ""
    ])

    # Validate Content-Type for success responses
    if status_code and status_code.startswith('2'):
        script_lines.extend([
            "pm.test('Content-Type is application/json', function () {",
            "    pm.expect(pm.response.headers.get('Content-Type')).to.include('application/json');",
            "});",
            ""
        ])

    # Store token if login/auth endpoint
    if should_store_token or "access_token" in required_fields:
        script_lines.extend([
            "pm.test('Access token received and stored', function () {",
            "    const jsonData = pm.response.json();",
            "    pm.expect(jsonData).to.have.property('access_token');",
            "    pm.expect(jsonData.access_token).to.be.a('string').and.not.empty;",
            "    pm.collectionVariables.set('access_token', jsonData.access_token);",
            "    console.log('✓ Access token stored successfully');",
            "});",
            ""
        ])

    # Validate required fields
    for field in set(required_fields):  # Remove duplicates
        if field and field not in ["access_token"]:  # Skip if already handled
            script_lines.extend([
                f"pm.test('Response contains {field}', function () {{",
                "    const jsonData = pm.response.json();",
                f"    pm.expect(jsonData).to.have.property('{field}');",
                "});",
                ""
            ])

    # Validate field values
    for field, expected_value in field_value_checks.items():
        script_lines.extend([
            f"pm.test('{field} equals {expected_value}', function () {{",
            "    const jsonData = pm.response.json();",
            f"    pm.expect(jsonData.{field}).to.eql('{expected_value}');",
            "});",
            ""
        ])

    # Validate enum fields
    for field, allowed_values in enum_checks.items():
        values_str = "', '".join(allowed_values)
        script_lines.extend([
            f"pm.test('{field} is valid enum value', function () {{",
            "    const jsonData = pm.response.json();",
            f"    pm.expect(jsonData.{field}).to.be.oneOf(['{values_str}']);",
            "});",
            ""
        ])

    # Error response validation
    if error_validation:
        script_lines.extend([
            "pm.test('Error response has proper structure', function () {",
            "    const jsonData = pm.response.json();",
            "    pm.expect(jsonData).to.have.property('error');",
            "    pm.expect(jsonData).to.have.property('message');",
            "    pm.expect(jsonData.error).to.be.a('string').and.not.empty;",
            "    pm.expect(jsonData.message).to.be.a('string').and.not.empty;",
            "});",
            ""
        ])

    # Add JSON schema validation if OpenAPI endpoint info available
    if endpoint_info and schema_validation_needed and status_code and status_code.startswith('2'):
        schema = _extract_response_schema(endpoint_info, status_code, openapi_data)
        if schema:
            schema_str = json.dumps(schema, indent=4).replace('\n', '\n    ')
            script_lines.extend([
                "pm.test('Response matches schema', function () {",
                f"    const schema = {schema_str};",
                "    pm.response.to.have.jsonSchema(schema);",
                "});",
                ""
            ])

    return script_lines


def _build_structured_test_script(
    test_case: Dict[str, Any],
    endpoint_info: Optional[Dict[str, Any]],
    openapi_data: Dict[str, Any],
) -> List[str]:
    """Build deterministic scripts from structured Newman scenario definitions."""

    tests_def: Dict[str, Any] = test_case.get("tests", {}) or {}

    script_lines: List[str] = [
        f"// Test: {test_case.get('name', 'Test')}",
        f"// ID: {test_case.get('id', 'N/A')}",
        "",
    ]

    status_code = tests_def.get("status_code")
    if status_code is not None:
        script_lines.extend([
            f"pm.test('Status code is {status_code}', function () {{",
            f"    pm.response.to.have.status({status_code});",
            "});",
            "",
        ])
    else:
        script_lines.extend([
            "pm.test('Status code is successful', function () {",
            "    pm.response.to.be.success;",
            "});",
            "",
        ])

    response_time = tests_def.get("response_time", 5000)
    if response_time:
        script_lines.extend([
            "pm.test('Response time is within threshold', function () {",
            f"    pm.expect(pm.response.responseTime).to.be.below({response_time});",
            "});",
            "",
        ])

    if status_code and str(status_code).startswith("2") and str(status_code) != "204":
        script_lines.extend([
            "pm.test('Response body is JSON', function () {",
            "    pm.response.to.be.json;",
            "});",
            "",
            "pm.test('Content-Type is application/json', function () {",
            "    pm.expect(pm.response.headers.get('Content-Type')).to.include('application/json');",
            "});",
            "",
        ])

    for header_check in tests_def.get("header_checks", []) or []:
        header_line = str(header_check)
        script_lines.append(header_line)
        if not header_line.endswith("\n"):
            script_lines.append("")

    for body_check in tests_def.get("body_checks", []) or []:
        body_line = str(body_check)
        script_lines.append(body_line)
        if not body_line.endswith("\n"):
            script_lines.append("")

    chaining = tests_def.get("chaining")
    if chaining:
        script_lines.extend([
            "pm.test('Capture chaining variables', function () {",
            "    try {",
            f"        {chaining}",
            "    } catch (error) {",
            "        console.warn('Chaining script falhou', error);",
            "        throw error;",
            "    }",
            "});",
            "",
        ])

    if tests_def.get("schema") and endpoint_info:
        schema = tests_def["schema"]
        schema_str = json.dumps(schema, indent=4).replace("\n", "\n    ")
        script_lines.extend([
            "pm.test('Response matches expected schema', function () {",
            f"    const schema = {schema_str};",
            "    pm.response.to.have.jsonSchema(schema);",
            "});",
            "",
        ])
    elif status_code and str(status_code).startswith("2") and endpoint_info:
        schema = _extract_response_schema(endpoint_info, str(status_code), openapi_data)
        if schema:
            schema_str = json.dumps(schema, indent=4).replace("\n", "\n    ")
            script_lines.extend([
                "pm.test('Response matches OpenAPI schema', function () {",
                f"    const schema = {schema_str};",
                "    pm.response.to.have.jsonSchema(schema);",
                "});",
                "",
            ])

    return script_lines


def _extract_response_schema(
    endpoint_info: Dict[str, Any],
    status_code: str,
    openapi_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Extract JSON schema from OpenAPI response definition."""
    responses = endpoint_info.get("responses", {})
    response_spec = responses.get(status_code, responses.get("default", {}))

    content = response_spec.get("content", {})
    json_content = content.get("application/json", {})

    if "schema" in json_content:
        schema = json_content["schema"]

        # Resolve $ref if present
        if "$ref" in schema:
            ref_path = schema["$ref"]
            schema = _resolve_schema_ref(ref_path, openapi_data)

        return schema

    return None


def _resolve_schema_ref(ref_path: str, openapi_data: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve $ref pointer to actual schema definition."""
    # ref_path format: "#/components/schemas/Account"
    if not ref_path.startswith("#/"):
        return {}

    parts = ref_path[2:].split("/")
    schema = openapi_data

    for part in parts:
        if isinstance(schema, dict) and part in schema:
            schema = schema[part]
        else:
            return {}

    return schema if isinstance(schema, dict) else {}


def _build_pre_request_script(test_case: Dict[str, Any], endpoint_info: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    """Build pre-request script for dynamic data and authentication checks."""
    preconditions = test_case.get("preconditions", [])
    test_steps = test_case.get("test_steps", [])

    script_lines = []

    # Check if test needs authentication
    needs_auth = any(
        "autenticado" in precond.lower() or "authenticated" in precond.lower()
        for precond in preconditions
    )

    if needs_auth:
        script_lines.extend([
            "// Verify authentication token is available",
            "const token = pm.collectionVariables.get('access_token');",
            "if (!token) {",
            "    console.error('⚠ No access token found. Please run authentication test first.');",
            "}",
            ""
        ])

    # Generate dynamic data if needed
    needs_idempotency = any(
        "idempotency" in step.get("action", "").lower() or
        "idempotência" in step.get("action", "").lower()
        for step in test_steps
    )

    if needs_idempotency:
        script_lines.extend([
            "// Generate unique idempotency key",
            "const idempotencyKey = pm.variables.replaceIn('{{$guid}}');",
            "pm.collectionVariables.set('idempotency_key', idempotencyKey);",
            "console.log('Generated idempotency key: ' + idempotencyKey);",
            ""
        ])

    # Generate unique identifiers for test data
    test_name_lower = test_case.get("name", "").lower()
    if "criar" in test_name_lower or "create" in test_name_lower:
        script_lines.extend([
            "// Generate unique test data",
            "pm.collectionVariables.set('unique_id', pm.variables.replaceIn('{{$guid}}'));",
            "pm.collectionVariables.set('timestamp', new Date().toISOString());",
            ""
        ])

    return script_lines if script_lines else None
