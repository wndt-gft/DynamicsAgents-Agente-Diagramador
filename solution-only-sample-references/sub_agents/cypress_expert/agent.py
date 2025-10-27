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

"""Cypress QA Expert Agent - BDD Pattern with 3 files output and auto-save."""

import os
from typing import Dict, Any, List, Optional
from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool
from . import prompt
from .tools.cypress_test_orchestrator import (
    process_agent_response_and_save,
    generate_expert_cypress_qa_tests
)
from ...utils.logging_config import create_contextual_logger
from ...utils.callbacks import validate_code_quality_callback
from ...utils.exceptions import (
    InvalidModelError,
    CypressError
)

# Initialize structured logger
logger = create_contextual_logger(
    "cypress_expert",
    framework="cypress",
    agent_type="sub_agent"
)

# Load model from environment variable, default to gemini-2.5-pro
MODEL = os.getenv("QA_MODEL", "gemini-2.5-pro")

# Get output directory from environment or use default
OUTPUT_DIR = os.getenv("CYPRESS_OUTPUT_DIR", "./cypress")


def cypress_bdd_save_callback(response: str, **kwargs) -> Dict[str, Any]:
    """
    Callback executed after agent generates response.

    This callback:
    1. Parses the 3 BDD files from agent response
    2. Validates them
    3. Saves to filesystem
    4. Returns metadata

    Args:
        response: Raw agent response with 3 files
        **kwargs: Additional context (feature_name, output_dir, etc.)

    Returns:
        Processing result with saved paths
    """
    logger.info("Post-generation callback triggered")

    try:
        # Extract parameters from kwargs
        feature_name = kwargs.get('feature_name')
        output_dir = kwargs.get('output_dir', OUTPUT_DIR)
        save_to_disk = kwargs.get('save_to_disk', True)

        # Process response and save files
        result = process_agent_response_and_save(
            agent_response=response,
            feature_name=feature_name,
            output_dir=output_dir,
            save_to_disk=save_to_disk
        )

        # Log success
        if result.get('saved_paths'):
            logger.info("Files saved successfully", extra_fields={
                "feature": result['saved_paths'].get('feature'),
                "steps": result['saved_paths'].get('steps'),
                "page_object": result['saved_paths'].get('page_object'),
                "quality_score": result.get('quality_score', 0)
            })

        return result

    except Exception as e:
        logger.error(f"Error in save callback: {e}", exc_info=True)
        return {
            "status": "error",
            "error_type": "callback_error",
            "error_message": str(e)
        }


def generate_cypress_tests_wrapper(
        gherkin_scenario: str,
        page_html: str,
        feature_name: Optional[str] = None,
        test_type: str = "bdd",
        output_format: str = "three_files",
        include_error_scenarios: bool = True,
        automation_level: str = "medium",
        output_dir: Optional[str] = None,
        save_to_disk: bool = True,
        custom_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Wrapper function for Google ADK Agent integration.

    Generates complete Cypress BDD test suites (3 files: Gherkin, Steps, Page Object)
    with proper error handling and automatic file saving.

    Args:
        gherkin_scenario: Test scenario in Gherkin format or natural language
        page_html: HTML structure of the page to be tested
        feature_name: Name of the feature (auto-generated if not provided)
        test_type: Type of test output ("bdd" for 3 files, "simple" for single file)
        output_format: Format specification ("three_files" for BDD pattern)
        include_error_scenarios: Whether to include error/negative test scenarios
        automation_level: Test complexity ("simple", "medium", "complex")
        output_dir: Output directory for saving files (default: ./cypress)
        save_to_disk: Whether to save files to filesystem (default: True)
        custom_config: Custom Cypress/Cucumber configuration

    Returns:
        Complete BDD test suite with 3 separate files:
        {
            "status": "success",
            "files": {
                "feature": {"path": "...", "content": "..."},
                "steps": {"path": "...", "content": "..."},
                "page_object": {"path": "...", "content": "..."}
            },
            "saved_paths": {
                "feature": "/absolute/path/to/features/login.feature",
                "steps": "/absolute/path/to/step_definitions/login_steps.js",
                "page_object": "/absolute/path/to/page_objects/LoginPage.js"
            },
            "metadata": {
                "feature_name": "login",
                "scenarios_count": 3,
                "steps_count": 12,
                "output_directory": "/absolute/path/to/cypress"
            },
            "quality_score": 95
        }

    Examples:
        >>> result = generate_cypress_tests_wrapper(
        ...     gherkin_scenario="Scenario: User login\\n  Given I am on login page...",
        ...     page_html="<form>...</form>",
        ...     feature_name="login"
        ... )
        >>> print(result["saved_paths"]["feature"])
        /path/to/cypress/e2e/features/login.feature
    """
    try:
        logger.info(
            "Cypress BDD test generation requested",
            extra_fields={
                "feature_name": feature_name or "auto_generated",
                "test_type": test_type,
                "output_format": output_format,
                "automation_level": automation_level,
                "html_length": len(page_html) if page_html else 0,
                "output_dir": output_dir or OUTPUT_DIR,
                "save_to_disk": save_to_disk
            }
        )

        # Validate required inputs
        if not gherkin_scenario or not gherkin_scenario.strip():
            raise ValueError("gherkin_scenario is required and cannot be empty")

        if not page_html or not page_html.strip():
            raise ValueError("page_html is required and cannot be empty")

        # Prepare context for agent
        context = generate_expert_cypress_qa_tests(
            gherkin_scenario=gherkin_scenario,
            page_html=page_html,
            feature_name=feature_name,
            test_type=test_type,
            output_format=output_format,
            include_error_scenarios=include_error_scenarios,
            automation_level=automation_level,
            custom_config=custom_config
        )

        # Build query for agent
        query = f"""
Generate Cypress BDD test files (Feature + Steps + Page Object) for:

**Gherkin Scenario:**
{gherkin_scenario}

**Page HTML:**
```html
{page_html}
```

**Feature Name:** {feature_name or 'auto_generated'}

**Requirements:**
- Generate exactly 3 files with proper delimiters (=== FILE: ... === and === END FILE ===)
- Use data-testid selectors as first priority
- Include proper error handling
- Follow BDD best practices
- Output format: {output_format}
"""

        # Call agent
        logger.info("Invoking Cypress Expert Agent")
        response = cypress_expert_agent.query(query)

        # Process response and save files
        result = process_agent_response_and_save(
            agent_response=response.content,
            feature_name=feature_name,
            output_dir=output_dir or OUTPUT_DIR,
            save_to_disk=save_to_disk
        )

        logger.info(
            "Cypress BDD test suite generated successfully",
            extra_fields={
                "feature_name": result.get("metadata", {}).get("feature_name"),
                "quality_score": result.get("quality_score", 0),
                "files_generated": len(result.get("files", {})),
                "files_saved": save_to_disk,
                "scenarios_count": result.get("metadata", {}).get("scenarios_count", 0)
            }
        )

        return result

    except ValueError as e:
        # Validation errors - return structured error
        logger.warning(f"Validation error in test generation: {str(e)}")
        return {
            "status": "error",
            "error_type": "validation_error",
            "error_message": str(e),
            "suggestion": "Please check input parameters (gherkin_scenario and page_html are required)"
        }

    except KeyError as e:
        # Missing expected data in response
        logger.error(f"Missing expected data in test generation: {str(e)}")
        return {
            "status": "error",
            "error_type": "parsing_error",
            "error_message": f"Failed to parse agent response: missing {str(e)}",
            "suggestion": "The agent may not have generated all required files. Please try again."
        }

    except Exception as e:
        # Unexpected errors - log and return structured error
        logger.error(
            f"Unexpected error in test generation: {str(e)}",
            extra_fields={
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        return {
            "status": "error",
            "error_type": "generation_error",
            "error_message": str(e),
            "suggestion": "Please review the error details and contact support if needed"
        }


try:
    logger.info("Initializing Cypress Expert Agent (BDD)", extra_fields={
        "model": MODEL,
        "tools_count": 1,
        "output_format": "three_files_bdd",
        "default_output_dir": OUTPUT_DIR
    })

    # Validate model configuration
    if not MODEL:
        raise InvalidModelError(
            "QA_MODEL environment variable is not set",
            details={"default": "gemini-2.5-pro"}
        )

    # Cypress Expert Agent instance for BDD pattern
    cypress_expert_agent = Agent(
        model=MODEL,
        name="cypress_qa_expert",
        instruction=prompt.CYPRESS_EXPERT_PROMPT,
        tools=[FunctionTool(generate_cypress_tests_wrapper)],  # ✅ Using wrapper
        output_key="cypress_expert_bdd_output",
        after_agent_callback=validate_code_quality_callback,  # ✅ QUALITY VALIDATION
    )

    logger.info("Cypress Expert Agent (BDD) initialized successfully", extra_fields={
        "agent_name": "cypress_qa_expert",
        "status": "ready",
        "output_pattern": "gherkin_feature + step_definitions + page_object",
        "auto_save": "enabled"
    })

except InvalidModelError as e:
    logger.error("Invalid model configuration", extra_fields={
        "error": str(e),
        "details": e.details
    })
    raise

except Exception as e:
    logger.error("Failed to initialize Cypress Expert Agent", extra_fields={
        "error_type": type(e).__name__,
        "error": str(e)
    }, exc_info=True)
    raise CypressError(
        "Cypress Expert Agent initialization failed",
        details={"original_error": str(e)}
    ) from e