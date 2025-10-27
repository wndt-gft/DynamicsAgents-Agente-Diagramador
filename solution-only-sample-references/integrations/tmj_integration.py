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
TMJ (Test Management for Jira) Integration Module.

This module provides integration capabilities with Zephyr Scale (TMJ) for:
- Creating test cases from generated test suites
- Syncing test execution results
- Managing test cycles and folders
- Linking tests to Jira issues
"""

import os
import json
import logging
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class TMJTestStatus(Enum):
    """Test execution statuses in TMJ."""
    PASS = "Pass"
    FAIL = "Fail"
    BLOCKED = "Blocked"
    IN_PROGRESS = "In Progress"
    NOT_EXECUTED = "Not Executed"


class TMJPriority(Enum):
    """Test case priorities in TMJ."""
    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"
    CRITICAL = "Critical"


@dataclass
class TMJConfig:
    """Configuration for TMJ integration."""
    base_url: str  # e.g., "https://your-domain.atlassian.net"
    api_token: str
    email: str  # Jira account email
    project_key: str  # e.g., "PROJ"
    folder_id: Optional[str] = None

    @classmethod
    def from_env(cls) -> "TMJConfig":
        """Load TMJ configuration from environment variables."""
        return cls(
            base_url=os.getenv("TMJ_BASE_URL", ""),
            api_token=os.getenv("TMJ_API_TOKEN", ""),
            email=os.getenv("TMJ_EMAIL", ""),
            project_key=os.getenv("TMJ_PROJECT_KEY", ""),
            folder_id=os.getenv("TMJ_FOLDER_ID")
        )

    def validate(self) -> bool:
        """Validate that all required configuration is present."""
        required = [self.base_url, self.api_token, self.email, self.project_key]
        return all(required)


@dataclass
class TMJTestCase:
    """Represents a test case in TMJ format."""
    name: str
    objective: str
    precondition: Optional[str] = None
    estimatedTime: Optional[int] = None  # in milliseconds
    priority: str = TMJPriority.NORMAL.value
    status: str = "Draft"
    folder: Optional[str] = None
    labels: List[str] = None
    customFields: Dict[str, Any] = None

    def __post_init__(self):
        if self.labels is None:
            self.labels = []
        if self.customFields is None:
            self.customFields = {}


class TMJIntegration:
    """
    Main integration class for TMJ (Test Management for Jira).

    Provides methods to:
    - Create test cases from AI-generated tests
    - Sync test execution results
    - Manage test cycles
    - Link tests to user stories/requirements
    """

    def __init__(self, config: Optional[TMJConfig] = None):
        """
        Initialize TMJ integration.

        Args:
            config: TMJ configuration. If None, loads from environment.
        """
        self.config = config or TMJConfig.from_env()

        if not self.config.validate():
            logger.warning("TMJ configuration is incomplete. Some features may not work.")

        self.session = requests.Session()
        self.session.auth = (self.config.email, self.config.api_token)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

        self.api_base = f"{self.config.base_url}/rest/atm/1.0"

    def create_test_case(self, test_case: TMJTestCase) -> Dict[str, Any]:
        """
        Create a test case in TMJ.

        Args:
            test_case: Test case data

        Returns:
            Created test case response from TMJ API
        """
        endpoint = f"{self.api_base}/testcase"

        payload = {
            "projectKey": self.config.project_key,
            "name": test_case.name,
            "objective": test_case.objective,
            "priority": test_case.priority,
            "status": test_case.status
        }

        # Add optional fields
        if test_case.precondition:
            payload["precondition"] = test_case.precondition
        if test_case.estimatedTime:
            payload["estimatedTime"] = test_case.estimatedTime
        if test_case.folder:
            payload["folder"] = test_case.folder
        if test_case.labels:
            payload["labels"] = test_case.labels
        if test_case.customFields:
            payload["customFields"] = test_case.customFields

        try:
            response = self.session.post(endpoint, json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Created test case: {test_case.name} (Key: {result.get('key')})")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create test case: {e}")
            raise

    def create_test_cycle(self, name: str, description: str = "",
                         planned_start_date: Optional[str] = None,
                         planned_end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a test cycle in TMJ.

        Args:
            name: Cycle name
            description: Cycle description
            planned_start_date: Start date (ISO format)
            planned_end_date: End date (ISO format)

        Returns:
            Created test cycle response
        """
        endpoint = f"{self.api_base}/testrun"

        payload = {
            "projectKey": self.config.project_key,
            "name": name,
            "description": description
        }

        if planned_start_date:
            payload["plannedStartDate"] = planned_start_date
        if planned_end_date:
            payload["plannedEndDate"] = planned_end_date

        try:
            response = self.session.post(endpoint, json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Created test cycle: {name} (Key: {result.get('key')})")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create test cycle: {e}")
            raise

    def add_test_to_cycle(self, test_case_key: str, cycle_key: str) -> Dict[str, Any]:
        """
        Add a test case to a test cycle.

        Args:
            test_case_key: Test case key (e.g., "PROJ-T123")
            cycle_key: Test cycle key (e.g., "PROJ-C456")

        Returns:
            Test run response
        """
        endpoint = f"{self.api_base}/testrun/{cycle_key}/testcase"

        payload = {
            "testCaseKey": test_case_key
        }

        try:
            response = self.session.post(endpoint, json=payload)
            response.raise_for_status()

            logger.info(f"Added test {test_case_key} to cycle {cycle_key}")
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to add test to cycle: {e}")
            raise

    def update_test_execution(self, test_run_key: str, status: TMJTestStatus,
                            comment: Optional[str] = None,
                            execution_time: Optional[int] = None) -> Dict[str, Any]:
        """
        Update test execution status.

        Args:
            test_run_key: Test run key
            status: Execution status
            comment: Optional comment
            execution_time: Execution time in milliseconds

        Returns:
            Updated test run response
        """
        endpoint = f"{self.api_base}/testrun/{test_run_key}"

        payload = {
            "status": status.value
        }

        if comment:
            payload["comment"] = comment
        if execution_time:
            payload["executionTime"] = execution_time

        try:
            response = self.session.put(endpoint, json=payload)
            response.raise_for_status()

            logger.info(f"Updated test run {test_run_key} to {status.value}")
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update test execution: {e}")
            raise

    def link_test_to_issue(self, test_case_key: str, issue_key: str) -> bool:
        """
        Link a test case to a Jira issue (user story, bug, etc.).

        Args:
            test_case_key: Test case key
            issue_key: Jira issue key

        Returns:
            True if successful
        """
        endpoint = f"{self.api_base}/testcase/{test_case_key}/issues"

        payload = {
            "issuesKeys": [issue_key]
        }

        try:
            response = self.session.post(endpoint, json=payload)
            response.raise_for_status()

            logger.info(f"Linked test {test_case_key} to issue {issue_key}")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to link test to issue: {e}")
            return False

    def convert_qa_agent_tests_to_tmj(self, qa_test_suite: Dict[str, Any],
                                     domain: str) -> List[TMJTestCase]:
        """
        Convert QA Agent generated tests to TMJ test cases format.

        Args:
            qa_test_suite: Test suite from QA Agent
            domain: Business domain

        Returns:
            List of TMJ test cases ready to be created
        """
        tmj_tests = []

        # Extract framework
        framework = qa_test_suite.get("framework", "unknown")

        # Add framework-specific label
        labels = [framework, domain, "ai-generated"]

        # For Cypress tests
        if framework == "cypress":
            test_suite = qa_test_suite.get("test_suite", {})
            test_description = test_suite.get("description", "")
            acceptance_criteria = test_suite.get("acceptance_criteria", [])

            # Create a test case for each acceptance criterion
            for idx, criterion in enumerate(acceptance_criteria, 1):
                test_case = TMJTestCase(
                    name=f"{domain.title()} - {criterion[:80]}",
                    objective=f"Verify: {criterion}",
                    precondition=test_description,
                    priority=TMJPriority.NORMAL.value,
                    labels=labels.copy(),
                    customFields={
                        "framework": framework,
                        "complexity": test_suite.get("complexity", "medium"),
                        "ai_generated": "true"
                    }
                )
                tmj_tests.append(test_case)

        # For Karate tests
        elif framework == "karate":
            test_suite = qa_test_suite.get("test_suite", {})
            scenarios = test_suite.get("test_scenarios", [])

            for scenario in scenarios:
                test_case = TMJTestCase(
                    name=f"{domain.title()} API - {scenario[:80]}",
                    objective=f"API Test: {scenario}",
                    priority=TMJPriority.HIGH.value,
                    labels=labels + ["api-test"],
                    customFields={
                        "framework": framework,
                        "test_type": "api",
                        "ai_generated": "true"
                    }
                )
                tmj_tests.append(test_case)

        # For Newman/Postman tests
        elif framework == "newman":
            collection_suite = qa_test_suite.get("collection_suite", {})
            main_collection = collection_suite.get("main_collection", {})

            # Create test cases from collection items
            items = main_collection.get("item", [])
            for item in items[:10]:  # Limit to first 10 to avoid overwhelming
                test_case = TMJTestCase(
                    name=f"{domain.title()} - {item.get('name', 'API Test')[:80]}",
                    objective=f"API Collection Test: {item.get('name', '')}",
                    priority=TMJPriority.NORMAL.value,
                    labels=labels + ["postman", "api-test"],
                    customFields={
                        "framework": framework,
                        "test_type": "api",
                        "ai_generated": "true"
                    }
                )
                tmj_tests.append(test_case)

        # For Playwright tests
        elif framework == "playwright":
            test_description = qa_test_suite.get("test_description", "")

            test_case = TMJTestCase(
                name=f"{domain.title()} - Cross-Browser Test",
                objective=test_description,
                priority=TMJPriority.HIGH.value,
                labels=labels + ["cross-browser", "e2e"],
                customFields={
                    "framework": framework,
                    "browsers": "chromium,firefox,webkit",
                    "ai_generated": "true"
                }
            )
            tmj_tests.append(test_case)

        logger.info(f"Converted {len(tmj_tests)} QA Agent tests to TMJ format")
        return tmj_tests


def sync_tests_to_tmj(qa_test_suite: Dict[str, Any], domain: str,
                      cycle_name: Optional[str] = None) -> Dict[str, Any]:
    """
    High-level function to sync QA Agent tests to TMJ.

    Args:
        qa_test_suite: Generated test suite from QA Agent
        domain: Business domain
        cycle_name: Optional test cycle name

    Returns:
        Summary of sync operation
    """
    tmj = TMJIntegration()

    # Convert tests
    tmj_tests = tmj.convert_qa_agent_tests_to_tmj(qa_test_suite, domain)

    # Create test cases
    created_tests = []
    for test in tmj_tests:
        try:
            result = tmj.create_test_case(test)
            created_tests.append(result)
        except Exception as e:
            logger.error(f"Failed to create test {test.name}: {e}")

    # Optionally create cycle and add tests
    cycle_key = None
    if cycle_name:
        try:
            cycle = tmj.create_test_cycle(
                name=cycle_name,
                description=f"AI-generated tests for {domain}"
            )
            cycle_key = cycle.get("key")

            # Add tests to cycle
            for test in created_tests:
                test_key = test.get("key")
                if test_key and cycle_key:
                    tmj.add_test_to_cycle(test_key, cycle_key)
        except Exception as e:
            logger.error(f"Failed to create cycle: {e}")

    return {
        "status": "success",
        "tests_created": len(created_tests),
        "cycle_key": cycle_key,
        "test_keys": [t.get("key") for t in created_tests]
    }


def create_test_cycle(name: str, description: str = "") -> str:
    """
    Simple function to create a test cycle.

    Args:
        name: Cycle name
        description: Cycle description

    Returns:
        Test cycle key
    """
    tmj = TMJIntegration()
    result = tmj.create_test_cycle(name, description)
    return result.get("key", "")
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

"""Integration modules for external test management systems."""

from .tmj_integration import TMJIntegration, sync_tests_to_tmj, create_test_cycle

__all__ = [
    "TMJIntegration",
    "sync_tests_to_tmj",
    "create_test_cycle",
]

