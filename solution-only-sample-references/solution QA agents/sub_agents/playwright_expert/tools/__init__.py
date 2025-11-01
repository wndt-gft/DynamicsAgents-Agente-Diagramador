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

"""Tools for Playwright Expert Agent."""

from .cross_browser_test_orchestrator import generate_expert_playwright_tests
from .test_generator import generate_playwright_expert_structure
from .page_object_generator import generate_playwright_page_objects
from .config_generator import generate_playwright_expert_config
from .cross_browser_utils import generate_cross_browser_utilities
from .visual_testing_generator import generate_visual_testing_suite
from .mobile_strategy_generator import generate_mobile_testing_strategy
from .performance_testing_generator import generate_playwright_performance_testing
from .execution_guide_generator import generate_playwright_execution_guide

__all__ = [
    "generate_expert_playwright_tests",
    "generate_playwright_expert_structure",
    "generate_playwright_page_objects",
    "generate_playwright_expert_config",
    "generate_cross_browser_utilities",
    "generate_visual_testing_suite",
    "generate_mobile_testing_strategy",
    "generate_playwright_performance_testing",
    "generate_playwright_execution_guide",
]
