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

"""Karate Test Data Generator - Domain-agnostic expert tool."""

from typing import Dict, Any, List
import json


def generate_test_data(domain: str, endpoints: List[Dict[str, Any]] = None) -> Dict[str, str]:
    """Generate test data for Karate API testing without domain dependencies."""

    # Basic configuration without domain_config dependency
    endpoints = endpoints or []

    test_data = _generate_api_test_data(domain, endpoints)

    return test_data


def _generate_api_test_data(domain: str, endpoints: List[Dict[str, Any]]) -> Dict[str, str]:
    """Generate API test data based on domain and endpoints."""

    # Generate basic test data without domain_config patterns
    return {
        "basic_data": f"""{{
    "domain": "{domain}",
    "test_environment": "test",
    "api_version": "v1"
}}"""
    }
