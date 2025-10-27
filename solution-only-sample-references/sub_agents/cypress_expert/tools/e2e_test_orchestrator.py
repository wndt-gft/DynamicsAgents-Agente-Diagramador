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
E2E Test Orchestrator for Cypress Expert.

This module is responsible for orchestrating the generation of complete Cypress E2E test suites.
It coordinates multiple specialized generators to produce comprehensive test artifacts.

Single Responsibility: Orchestrate the composition of Cypress E2E test components into a complete suite.
"""

from typing import Dict, Any, List, Optional
from ....utils.logging_config import create_contextual_logger
from ....utils.exceptions import (
    TestGenerationError,
    CypressError,
    InvalidInputError,
    ValidationError
)

# Initialize logger with context
logger = create_contextual_logger(
    "cypress_orchestrator",
    framework="cypress",
    component="e2e_orchestrator"
)


def generate_expert_cypress_tests(
    test_description: str,
    acceptance_criteria: List[str],
    business_domain: str,
    test_complexity: str = "medium",
    base_url: str = "http://localhost:3000",
    include_accessibility: bool = True,
    include_performance: bool = True,
    cross_browser_support: Optional[List[str]] = None,
    domain_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Orchestrate the generation of expert-level Cypress E2E tests.

    This function coordinates multiple specialized generators to create a complete,
    production-ready Cypress test suite. It does NOT contain business logic for
    generating individual components - that responsibility belongs to the specialized
    generator modules.

    Args:
        test_description: Detailed description of what needs to be tested
        acceptance_criteria: List of acceptance criteria to validate
        business_domain: Business domain (dynamically configured)
        test_complexity: Complexity level (simple, medium, complex, enterprise)
        base_url: Base URL for the application under test
        include_accessibility: Whether to include accessibility testing
        include_performance: Whether to include performance monitoring
        cross_browser_support: List of browsers to support
        domain_config: Dynamic domain configuration

    Returns:
        Complete Cypress test suite with all components orchestrated

    Raises:
        InvalidInputError: If input parameters are invalid
        TestGenerationError: If test generation fails
        CypressError: If Cypress-specific error occurs
    """
    # Import generator functions here to avoid circular imports
    from .test_generator import generate_cypress_test_structure
    from .page_object_generator import generate_page_objects
    from .command_generator import generate_custom_commands
    from .config_generator import generate_cypress_config
    from .data_generator import generate_test_data
    from .ci_cd_generator import generate_ci_cd_pipeline
    from .strategy_generator import generate_testing_strategies

    logger.info("Starting Cypress test generation", extra_fields={
        "domain": business_domain,
        "complexity": test_complexity,
        "criteria_count": len(acceptance_criteria),
        "accessibility": include_accessibility,
        "performance": include_performance
    })

    try:
        # Validate inputs
        if not test_description or not test_description.strip():
            raise InvalidInputError(
                "test_description cannot be empty",
                details={"parameter": "test_description"}
            )

        if not acceptance_criteria or len(acceptance_criteria) == 0:
            raise InvalidInputError(
                "acceptance_criteria must contain at least one criterion",
                details={"parameter": "acceptance_criteria", "received": acceptance_criteria}
            )

        if test_complexity not in ["simple", "medium", "complex", "enterprise"]:
            logger.warning("Invalid complexity level, using default", extra_fields={
                "received": test_complexity,
                "default": "medium"
            })
            test_complexity = "medium"

        if cross_browser_support is None:
            cross_browser_support = ["chrome", "firefox", "edge"]
            logger.debug("Using default browser support", extra_fields={
                "browsers": cross_browser_support
            })

        if domain_config is None:
            domain_config = {}

        # Generate test structure
        logger.info("Generating test structure", extra_fields={
            "step": "test_structure"
        })
        test_structure = generate_cypress_test_structure(
            description=test_description,
            criteria=acceptance_criteria,
            domain=business_domain,
            complexity=test_complexity
        )

        # Generate page objects
        logger.info("Generating page objects", extra_fields={
            "step": "page_objects"
        })
        page_objects = generate_page_objects(
            domain=business_domain,
            complexity=test_complexity
        )

        # Generate custom commands
        logger.info("Generating custom commands", extra_fields={
            "step": "custom_commands"
        })
        custom_commands = generate_custom_commands(
            domain=business_domain,
            domain_config=domain_config
        )

        # Generate Cypress configuration
        logger.info("Generating Cypress configuration", extra_fields={
            "step": "config",
            "browsers": cross_browser_support
        })
        cypress_config = generate_cypress_config(
            domain=business_domain,
            browsers=cross_browser_support,
            accessibility=include_accessibility,
            performance=include_performance
        )

        # Generate test data
        logger.info("Generating test data", extra_fields={
            "step": "test_data"
        })
        test_data = generate_test_data(
            domain=business_domain,
            complexity=test_complexity
        )

        # Generate CI/CD pipeline
        logger.info("Generating CI/CD pipeline", extra_fields={
            "step": "ci_cd_pipeline"
        })
        ci_cd_pipeline = generate_ci_cd_pipeline(
            domain=business_domain,
            browsers=cross_browser_support
        )

        # Generate testing strategies
        logger.info("Generating testing strategies", extra_fields={
            "step": "testing_strategies"
        })
        testing_strategies = generate_testing_strategies(
            domain=business_domain
        )

        # Orchestrate all components into a complete test suite
        result = {
            "test_suite": {
                "description": test_description,
                "business_domain": business_domain,
                "complexity": test_complexity,
                "test_structure": test_structure,
                "page_objects": page_objects,
                "custom_commands": custom_commands,
                "cypress_config": cypress_config,
                "test_data": test_data,
                "ci_cd_pipeline": ci_cd_pipeline,
                "testing_strategies": testing_strategies,
                "accessibility_enabled": include_accessibility,
                "performance_enabled": include_performance,
                "browsers": cross_browser_support
            },
            "metadata": {
                "framework": "cypress",
                "version": "13.x",
                "generated_components": [
                    "test_specs",
                    "page_objects",
                    "custom_commands",
                    "config",
                    "test_data",
                    "ci_cd",
                    "strategies"
                ]
            }
        }

        logger.info("Cypress test generation completed successfully", extra_fields={
            "domain": business_domain,
            "components_generated": len(result["metadata"]["generated_components"]),
            "status": "success"
        })

        return result

    except InvalidInputError as e:
        logger.error("Invalid input parameters", extra_fields={
            "error": str(e),
            "details": e.details
        })
        raise

    except (TestGenerationError, CypressError) as e:
        logger.error("Test generation failed", extra_fields={
            "error_type": type(e).__name__,
            "error": str(e),
            "domain": business_domain
        }, exc_info=True)
        raise

    except Exception as e:
        logger.error("Unexpected error during test generation", extra_fields={
            "error_type": type(e).__name__,
            "error": str(e),
            "domain": business_domain
        }, exc_info=True)
        raise CypressError(
            "Failed to generate Cypress tests due to unexpected error",
            details={
                "original_error": str(e),
                "domain": business_domain,
                "complexity": test_complexity
            }
        ) from e
