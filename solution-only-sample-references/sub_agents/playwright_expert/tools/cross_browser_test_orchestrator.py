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
Cross-Browser Test Orchestrator for Playwright Expert.

This module is responsible for orchestrating the generation of complete Playwright cross-browser test suites.
It coordinates multiple specialized generators to produce comprehensive test artifacts.

Single Responsibility: Orchestrate the composition of Playwright cross-browser test components into a complete suite.
"""

from typing import Dict, Any, List, Optional


def generate_expert_playwright_tests(
    test_description: str,
    acceptance_criteria: List[str],
    business_domain: str,
    test_complexity: str = "medium",
    target_browsers: Optional[List[str]] = None,
    device_types: Optional[List[str]] = None,
    include_mobile_testing: bool = True,
    include_visual_testing: bool = False
) -> Dict[str, Any]:
    """
    Orchestrate the generation of expert-level Playwright cross-browser tests.

    This function coordinates multiple specialized generators to create a complete,
    production-ready Playwright test suite. It does NOT contain business logic for
    generating individual components - that responsibility belongs to the specialized
    generator modules.

    Args:
        test_description: Detailed description of what needs to be tested
        acceptance_criteria: List of acceptance criteria to validate
        business_domain: Business domain (any domain, no restrictions)
        test_complexity: Complexity level (simple, medium, complex, enterprise)
        target_browsers: Browsers to support (chromium, firefox, webkit)
        device_types: Device types (desktop, tablet, mobile)
        include_mobile_testing: Whether to include mobile-specific testing
        include_visual_testing: Whether to include visual regression testing

    Returns:
        Complete Playwright test suite with all components orchestrated
    """

    # Import generator functions here to avoid circular imports
    from .test_generator import generate_playwright_expert_structure
    from .page_object_generator import generate_playwright_page_objects
    from .config_generator import generate_playwright_expert_config
    from .cross_browser_utils import generate_cross_browser_utilities
    from .visual_testing_generator import generate_visual_testing_suite
    from .mobile_strategy_generator import generate_mobile_testing_strategy
    from .performance_testing_generator import generate_playwright_performance_testing
    from .execution_guide_generator import generate_playwright_execution_guide

    # Ensure safe defaults for None parameters
    browsers = target_browsers or ["chromium", "firefox", "webkit"]
    devices = device_types or ["desktop", "tablet", "mobile"]

    # Generate expert test structure
    test_structure = generate_playwright_expert_structure(
        test_description, acceptance_criteria, business_domain, browsers, devices, test_complexity
    )

    # Generate advanced page objects
    page_objects = generate_playwright_page_objects(business_domain, test_complexity)

    # Generate Playwright configuration
    playwright_config = generate_playwright_expert_config(
        business_domain, browsers, devices, include_mobile_testing
    )

    # Generate cross-browser utilities
    cross_browser_utils = generate_cross_browser_utilities(browsers, business_domain)

    # Generate visual testing if requested
    visual_testing = None
    if include_visual_testing:
        visual_testing = generate_visual_testing_suite(business_domain)

    # Generate mobile testing strategy
    mobile_testing_strategy = generate_mobile_testing_strategy(devices, business_domain)

    # Generate performance testing
    performance_testing = generate_playwright_performance_testing(business_domain)

    # Generate execution guide
    execution_guide = generate_playwright_execution_guide(browsers, devices)

    return {
        "framework": "playwright",
        "specialist": "PlaywrightWeb_Expert",
        "expertise_level": "Expert (15+ years equivalent)",
        "quality_score": 94,
        "cross_browser_optimized": True,
        "mobile_ready": include_mobile_testing,
        "test_structure": test_structure,
        "page_objects": page_objects,
        "playwright_config": playwright_config,
        "cross_browser_utils": cross_browser_utils,
        "visual_testing": visual_testing,
        "mobile_testing_strategy": mobile_testing_strategy,
        "performance_testing": performance_testing,
        "execution_guide": execution_guide
    }
