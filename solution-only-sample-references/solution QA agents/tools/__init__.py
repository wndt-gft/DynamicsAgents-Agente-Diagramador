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
Tools for the QA Automation Orchestrator Agent.

Note: This agent now uses sub_agents architecture instead of manual orchestration tools.
The root agent automatically coordinates with specialized expert agents (Cypress, Playwright,
Karate, Newman) based on the requirements. No manual tools are needed for orchestration.
"""

from .git_tools import commit_generated_tests, get_git_status, push_to_remote

__all__ = [
    "commit_generated_tests",
    "get_git_status",
    "push_to_remote",
]
