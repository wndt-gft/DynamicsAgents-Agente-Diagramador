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

"""Playwright Web Expert Agent - Specialized subagent for modern cross-browser testing."""

import os
from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool
from . import prompt
from .tools import generate_expert_playwright_tests
from ...utils.callbacks import validate_code_quality_callback

# Load model from environment variable, default to gemini-2.5-pro
MODEL = os.getenv("QA_MODEL", "gemini-2.5-pro")

# Playwright Expert Agent instance with cross-browser tools
playwright_expert_agent = Agent(
    model=MODEL,
    name="playwright_web_expert",
    instruction=prompt.PLAYWRIGHT_EXPERT_PROMPT,
    tools=[FunctionTool(generate_expert_playwright_tests)],
    output_key="playwright_expert_output",
    after_agent_callback=validate_code_quality_callback,  # ✅ QUALITY VALIDATION
)
