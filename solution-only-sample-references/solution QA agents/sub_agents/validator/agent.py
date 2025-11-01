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

"""Code Validator Agent - Quality Gate for Generated Tests."""

import os
from google.adk import Agent
from . import prompt
from ...utils.logging_config import create_contextual_logger

logger = create_contextual_logger(
    "qa_automation.validator",
    framework="validator",
    agent_type="validation_agent"
)

# Load model from environment variable
MODEL = os.getenv("QA_MODEL", "gemini-2.5-pro")

try:
    logger.info("Initializing Code Validator Agent", extra_fields={
        "model": MODEL,
        "purpose": "quality_gate"
    })

    code_validator_agent = Agent(
        model=MODEL,
        name="code_validator",
        description="Validates generated test code for syntax, logic, security, and quality",
        instruction=prompt.VALIDATOR_PROMPT,
        disallow_transfer_to_parent=False,
        disallow_transfer_to_peers=True,
        output_key="validation_result",
    )

    logger.info("Code Validator Agent initialized successfully", extra_fields={
        "agent_name": "code_validator",
        "status": "ready",
        "validation_enabled": True
    })

except Exception as e:
    logger.error("Failed to initialize Code Validator Agent", extra_fields={
        "error_type": type(e).__name__,
        "error": str(e)
    }, exc_info=True)
    raise
