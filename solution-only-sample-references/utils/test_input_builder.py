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
Input Specification Module for API Testing.

Provides unified interface for combining:
- OpenAPI specifications (from Bitbucket or local files)
- Test scenarios (from Zephyr Scale or text)
- Manual request data (URL, path, body, headers, etc.)
"""

import os
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from pathlib import Path
import logging

from .openapi_parser import OpenAPIParser, OpenAPISpec, load_openapi_spec
from .zephyr_parser import ZephyrParser, ZephyrExport, load_test_scenarios

logger = logging.getLogger(__name__)


@dataclass
class ManualRequestData:
    """Manual API request data when OpenAPI is not available."""
    base_url: str
    endpoints: List[Dict[str, Any]]
    authentication: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "base_url": self.base_url,
            "endpoints": self.endpoints,
            "authentication": self.authentication,
            "headers": self.headers
        }


@dataclass
class APITestInput:
    """
    Complete input specification for API test generation.

    Combines OpenAPI spec, test scenarios, and manual data into
    a unified structure for test generation.
    """
    openapi_spec: Optional[OpenAPISpec] = None
    test_scenarios: Optional[ZephyrExport] = None
    manual_data: Optional[ManualRequestData] = None
    environment: str = "development"

    def has_openapi(self) -> bool:
        """Check if OpenAPI spec is available."""
        return self.openapi_spec is not None

    def has_scenarios(self) -> bool:
        """Check if test scenarios are available."""
        return self.test_scenarios is not None

    def has_manual_data(self) -> bool:
        """Check if manual request data is available."""
        return self.manual_data is not None

    def get_base_url(self) -> str:
        """Get base URL from available sources."""
        if self.openapi_spec:
            return self.openapi_spec.get_base_url(self.environment)
        elif self.manual_data:
            return self.manual_data.base_url
        return ""

    def get_all_endpoints(self) -> List[Dict[str, Any]]:
        """
        Get all endpoints from available sources.

        Returns list of endpoint dictionaries with:
        - path: str
        - method: str
        - description: str
        - examples: dict
        """
        endpoints = []

        if self.openapi_spec:
            for endpoint in self.openapi_spec.endpoints:
                endpoints.append({
                    "path": endpoint.path,
                    "method": endpoint.method,
                    "operation_id": endpoint.operation_id,
                    "summary": endpoint.summary,
                    "description": endpoint.description,
                    "parameters": endpoint.parameters,
                    "request_body": endpoint.request_body,
                    "responses": endpoint.responses,
                    "examples": endpoint.examples
                })

        if self.manual_data:
            endpoints.extend(self.manual_data.endpoints)

        return endpoints

    def get_test_cases(self) -> List[Dict[str, Any]]:
        """Get all test cases from scenarios."""
        if not self.test_scenarios:
            return []

        return [tc.to_dict() for tc in self.test_scenarios.test_cases]

    def to_dict(self) -> Dict[str, Any]:
        """Convert complete input to dictionary for LLM processing."""
        return {
            "has_openapi": self.has_openapi(),
            "has_scenarios": self.has_scenarios(),
            "has_manual_data": self.has_manual_data(),
            "base_url": self.get_base_url(),
            "environment": self.environment,
            "endpoints": self.get_all_endpoints(),
            "test_cases": self.get_test_cases(),
            "openapi_info": self.openapi_spec.info if self.openapi_spec else None
        }


class APITestInputBuilder:
    """
    Builder for creating APITestInput from various sources.

    Provides fluent interface for combining OpenAPI specs,
    test scenarios, and manual data.
    """

    def __init__(self):
        self.openapi_spec: Optional[OpenAPISpec] = None
        self.test_scenarios: Optional[ZephyrExport] = None
        self.manual_data: Optional[ManualRequestData] = None
        self.environment: str = "development"
        self.bitbucket_token: Optional[str] = None

    def with_environment(self, environment: str) -> 'APITestInputBuilder':
        """Set target environment (development, staging, production)."""
        self.environment = environment
        return self

    def with_bitbucket_token(self, token: str) -> 'APITestInputBuilder':
        """Set Bitbucket access token for remote OpenAPI fetch."""
        self.bitbucket_token = token
        return self

    def with_openapi_file(self, file_path: Union[str, Path]) -> 'APITestInputBuilder':
        """Load OpenAPI spec from local file."""
        try:
            self.openapi_spec = load_openapi_spec(file_path, source_type="file")
            logger.info(f"Loaded OpenAPI spec from file: {file_path}")
        except Exception as e:
            logger.error(f"Failed to load OpenAPI spec from file: {e}")
            raise
        return self

    def with_openapi_url(self, url: str) -> 'APITestInputBuilder':
        """Load OpenAPI spec from URL."""
        try:
            self.openapi_spec = load_openapi_spec(url, source_type="url")
            logger.info(f"Loaded OpenAPI spec from URL: {url}")
        except Exception as e:
            logger.error(f"Failed to load OpenAPI spec from URL: {e}")
            raise
        return self

    def with_openapi_bitbucket(
        self,
        workspace: str,
        repo_slug: str,
        file_path: str,
        branch: str = "main"
    ) -> 'APITestInputBuilder':
        """Load OpenAPI spec from Bitbucket repository."""
        if not self.bitbucket_token:
            raise ValueError("Bitbucket token required. Use with_bitbucket_token() first.")

        try:
            self.openapi_spec = load_openapi_spec(
                file_path,
                source_type="bitbucket",
                bitbucket_token=self.bitbucket_token,
                workspace=workspace,
                repo_slug=repo_slug,
                branch=branch
            )
            logger.info(f"Loaded OpenAPI spec from Bitbucket: {workspace}/{repo_slug}/{file_path}")
        except Exception as e:
            logger.error(f"Failed to load OpenAPI spec from Bitbucket: {e}")
            raise
        return self

    def with_zephyr_file(self, file_path: Union[str, Path]) -> 'APITestInputBuilder':
        """Load test scenarios from Zephyr export file."""
        try:
            self.test_scenarios = load_test_scenarios(file_path, format="json")
            logger.info(f"Loaded {len(self.test_scenarios.test_cases)} test scenarios from: {file_path}")
        except Exception as e:
            logger.error(f"Failed to load test scenarios: {e}")
            raise
        return self

    def with_text_scenarios(self, text_content: str) -> 'APITestInputBuilder':
        """Load test scenarios from plain text."""
        try:
            self.test_scenarios = load_test_scenarios(text_content, format="text")
            logger.info(f"Loaded {len(self.test_scenarios.test_cases)} test scenarios from text")
        except Exception as e:
            logger.error(f"Failed to parse text scenarios: {e}")
            raise
        return self

    def with_manual_data(
        self,
        base_url: str,
        endpoints: List[Dict[str, Any]],
        authentication: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> 'APITestInputBuilder':
        """Add manual request data."""
        self.manual_data = ManualRequestData(
            base_url=base_url,
            endpoints=endpoints,
            authentication=authentication,
            headers=headers
        )
        logger.info(f"Added manual data with {len(endpoints)} endpoints")
        return self

    def build(self) -> APITestInput:
        """Build final APITestInput object."""
        if not any([self.openapi_spec, self.test_scenarios, self.manual_data]):
            raise ValueError("At least one input source required (OpenAPI, scenarios, or manual data)")

        return APITestInput(
            openapi_spec=self.openapi_spec,
            test_scenarios=self.test_scenarios,
            manual_data=self.manual_data,
            environment=self.environment
        )


def create_test_input_from_dict(input_dict: Dict[str, Any]) -> APITestInput:
    """
    Create APITestInput from dictionary (useful for LLM tool calls).

    Expected structure:
    {
        "openapi": {
            "source_type": "file|url|bitbucket",
            "source": "path or URL",
            ... (bitbucket params if applicable)
        },
        "scenarios": {
            "source_type": "file|text",
            "source": "path or content"
        },
        "manual_data": {
            "base_url": "...",
            "endpoints": [...]
        },
        "environment": "development|staging|production",
        "bitbucket_token": "optional token"
    }
    """
    builder = APITestInputBuilder()

    # Set environment
    if "environment" in input_dict:
        builder.with_environment(input_dict["environment"])

    # Set Bitbucket token if provided
    bitbucket_token = input_dict.get("bitbucket_token") or os.getenv("BITBUCKET_TOKEN")
    if bitbucket_token:
        builder.with_bitbucket_token(bitbucket_token)

    # Load OpenAPI spec
    if "openapi" in input_dict:
        openapi_config = input_dict["openapi"]
        source_type = openapi_config.get("source_type", "auto")
        source = openapi_config.get("source")

        if source_type == "file":
            builder.with_openapi_file(source)
        elif source_type == "url":
            builder.with_openapi_url(source)
        elif source_type == "bitbucket":
            builder.with_openapi_bitbucket(
                workspace=openapi_config["workspace"],
                repo_slug=openapi_config["repo_slug"],
                file_path=source,
                branch=openapi_config.get("branch", "main")
            )

    # Load test scenarios
    if "scenarios" in input_dict:
        scenarios_config = input_dict["scenarios"]
        source_type = scenarios_config.get("source_type", "auto")
        source = scenarios_config.get("source")

        if source_type == "file":
            builder.with_zephyr_file(source)
        elif source_type == "text":
            builder.with_text_scenarios(source)

    # Add manual data
    if "manual_data" in input_dict:
        manual_config = input_dict["manual_data"]
        builder.with_manual_data(
            base_url=manual_config["base_url"],
            endpoints=manual_config["endpoints"],
            authentication=manual_config.get("authentication"),
            headers=manual_config.get("headers")
        )

    return builder.build()

