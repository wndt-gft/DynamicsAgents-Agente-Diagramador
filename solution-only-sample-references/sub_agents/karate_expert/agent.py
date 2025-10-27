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

"""Karate API Expert Agent - Generic modular structure for any domain."""

import os
from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool
from . import prompt
from .tools import generate_expert_karate_api_tests
from ...utils.logging_config import create_contextual_logger
from ...utils.callbacks import validate_code_quality_callback
from ...utils.exceptions import (
    InvalidModelError,
    KarateError
)

# Initialize structured logger
logger = create_contextual_logger(
    "karate_expert",
    framework="karate",
    agent_type="sub_agent"
)

# Load model from environment variable, default to gemini-2.5-pro
MODEL = os.getenv("QA_MODEL", "gemini-2.5-pro")

try:
    logger.info("Initializing Karate Expert Agent", extra_fields={
        "model": MODEL,
        "tools_count": 1
    })

    # Validate model configuration
    if not MODEL:
        raise InvalidModelError(
            "QA_MODEL environment variable is not set",
            details={"default": "gemini-2.5-pro"}
        )

    # Karate Expert Agent instance with universal tools
    karate_expert_agent = Agent(
        model=MODEL,
        name="karate_api_expert",
        instruction=prompt.KARATE_EXPERT_PROMPT,
        tools=[FunctionTool(generate_expert_karate_api_tests)],
        # Removido output_schema para permitir transferência ao agente pai
        output_key="karate_expert_output",
        after_agent_callback=validate_code_quality_callback,  # ✅ QUALITY VALIDATION
    )

    logger.info("Karate Expert Agent initialized successfully", extra_fields={
        "agent_name": "karate_api_expert",
        "status": "ready"
    })

except InvalidModelError as e:
    logger.error("Invalid model configuration", extra_fields={
        "error": str(e),
        "details": e.details
    })
    raise

except Exception as e:
    logger.error("Failed to initialize Karate Expert Agent", extra_fields={
        "error_type": type(e).__name__,
        "error": str(e)
    }, exc_info=True)
    raise KarateError(
        "Karate Expert Agent initialization failed",
        details={"original_error": str(e)}
    ) from e
