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

"""QA Automation Agent with Specialized Subagents Architecture and Refinement Loop."""

import logging
import warnings
from google.adk import Agent, agents
from google.adk.tools.function_tool import FunctionTool
from google.genai import types
from .utils.config import qa_config
from .prompt import QA_ORCHESTRATOR_PROMPT
from .tools.git_tools import commit_generated_tests, get_git_status, push_to_remote

# Import all specialized expert agents
from .sub_agents.cypress_expert.agent import cypress_expert_agent
from .sub_agents.karate_expert.agent import karate_expert_agent
from .sub_agents.newman_expert.agent import newman_expert_agent
from .sub_agents.playwright_expert.agent import playwright_expert_agent
from .sub_agents.validator.agent import code_validator_agent
from .sub_agents.refinement.agent import refinement_orchestrator
from .sub_agents.git_agent.agent import git_commit_agent

# Import refinement loop callbacks and configuration
from .sub_agents.refinement.agent import (
    init_refinement_loop_state,
    update_refinement_iteration,
    track_refinement_metrics,
    MAX_REFINEMENT_ITERATIONS,
)

warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")

logger = logging.getLogger(__name__)

# ============================================================================
# REFINEMENT LOOP ARCHITECTURE
# ============================================================================
#
# Structure:
# 1. Router Agent (selects appropriate framework expert)
# 2. SequentialAgent (Generator -> Validator -> Refinement Feedback)
# 3. LoopAgent (wraps sequence, iterates up to 3x until quality >= 70)
# 4. Root Agent (orchestrates entire flow)
#
# Flow:
# - User Request → Root Agent
# - Root delegates to Refinement Loop
# - Loop: Generate → Validate → [If score < 70] Refine → Repeat
# - Early Exit: If score >= 70 or max iterations (3) reached
# ============================================================================


# Step 1: Create router/selector for framework experts
# This agent decides which testing framework to use based on requirements
framework_selector_agent = Agent(
    model=qa_config.model,
    name="framework_selector",
    description=(
        "Analyzes requirements and selects the most appropriate testing framework. "
        "Routes to Cypress/Playwright for E2E UI tests, Karate/Newman for API tests."
    ),
    instruction="""You are the Framework Selector Agent.

Analyze the user's requirements and SELECT ONE appropriate testing framework:

**Choose Cypress when:**
- E2E testing for web applications
- Need fast, reliable UI testing
- JavaScript/TypeScript stack preferred

**Choose Playwright when:**
- Modern cross-browser testing required
- Need to test Chromium, Firefox, WebKit
- Advanced automation features needed

**Choose Karate when:**
- API testing with comprehensive validation
- Need BDD/Gherkin style syntax
- Complex API workflows and data-driven testing

**Choose Newman when:**
- Postman collections need automation
- CI/CD integration for API tests
- Team already uses Postman

After analysis, delegate to ONE of the expert agents:
- cypress_expert for Cypress
- playwright_expert for Playwright
- karate_expert for Karate
- newman_expert for Newman

The expert will generate the test code.
""",
    sub_agents=[
        cypress_expert_agent,
        playwright_expert_agent,
        karate_expert_agent,
        newman_expert_agent,
    ],
    output_key="generated_test_code",
)


# Step 2: Create sequential flow - Generate -> Validate -> Refine
generation_validation_refinement_sequence = agents.SequentialAgent(
    name="gen_validate_refine_sequence",
    description=(
        "Sequential execution: Select framework and generate tests, "
        "validate code quality, provide refinement feedback if needed"
    ),
    sub_agents=[
        framework_selector_agent,      # 1. Selects framework & generates code
        code_validator_agent,          # 2. Validates quality (returns score & issues)
        refinement_orchestrator,       # 3. Analyzes results & prepares feedback for next iteration
    ],
    after_agent_callback=update_refinement_iteration,
)


# Step 3: Wrap in LoopAgent for iterative refinement
qa_refinement_loop = agents.LoopAgent(
    name="qa_refinement_loop",
    description=(
        "Iterative refinement loop with quality validation. "
        "Generates tests, validates quality, and refines up to 3 times "
        "until quality score >= 70 or maximum iterations reached."
    ),
    sub_agents=[generation_validation_refinement_sequence],
    before_agent_callback=init_refinement_loop_state,      # Initialize: iteration_count=0
    after_agent_callback=update_refinement_iteration,      # Update iteration and check for early exit
    max_iterations=MAX_REFINEMENT_ITERATIONS,              # Maximum 3 attempts (hard limit)
)


# Step 4: Root Agent - Main entry point
# Git commit agent is available as optional sub-agent, not in automatic sequence
root_agent = Agent(
    model=qa_config.model,
    name=qa_config.agent_name,
    description=(
        "Expert QA Automation Orchestrator with iterative refinement loop. "
        "Automatically selects the appropriate testing framework (Cypress, Playwright, "
        "Karate, Newman) based on requirements, generates tests, validates quality, "
        "and refines iteratively (up to 3 attempts) until achieving production-ready "
        "code quality (score >= 70). Can also help commit generated tests to Git if requested."
    ),
    instruction=QA_ORCHESTRATOR_PROMPT + """

## 🎯 CRITICAL WORKFLOW - FOLLOW THIS ORDER:

### STEP 0: FRAMEWORK SELECTION (ALWAYS FIRST!)

**YOU MUST ALWAYS START HERE** when receiving a new test generation request:

1. **Detect if user has already selected a framework:**
   - Look for explicit mentions: "usar Karate", "com Cypress", "framework Playwright", etc.
   - Check conversation context for prior framework selection
   
2. **IF NO FRAMEWORK SELECTED YET:**
   - ✅ Present the 4 framework options (Karate, Newman, Cypress, Playwright)
   - ✅ Use the exact message format from QA_ORCHESTRATOR_PROMPT
   - ✅ STOP and WAIT for user response
   - ❌ DO NOT proceed to Step 1
   - ❌ DO NOT ask for OpenAPI or scenarios yet
   - ❌ DO NOT delegate to any sub-agent

3. **WHEN USER RESPONDS with a framework choice:**
   - Validate the choice (1-4, or framework name)
   - Confirm: "✅ Perfeito! Vou usar [Framework] para seus testes."
   - THEN proceed to Step 1 (Input Validation)

4. **IF FRAMEWORK IS ALREADY SELECTED:**
   - Skip to Step 1 (Input Validation)

---

### STEP 1: INPUT VALIDATION (AFTER FRAMEWORK SELECTION)

## ⚠️ MANDATORY: INPUT VALIDATION BEFORE DELEGATION

**BEFORE delegating to qa_refinement_loop, you MUST check:**

**IF FRAMEWORK = NEWMAN:**
1. **Has the user provided OpenAPI specification (.yaml/.json)?**
   - Yes: ✓ OpenAPI spec available
   - No: ⛔ STOP and ask for OpenAPI specification (MANDATORY for Newman)

2. **Has the user provided business context (Zephyr test scenarios)?**
   - Yes: ✓ Business context available → PROCEED to delegation
   - No: ⛔ STOP and ask for scenarios (MANDATORY)

You MUST respond in PORTUGUESE for Newman:

"📄 Entendi os cenários de negócio! 

Mas para gerar testes Newman, eu preciso da **especificação OpenAPI** (.yaml ou .json).

Por favor, me envie:
- Arquivo OpenAPI/Swagger da API
- Documentação dos endpoints com schemas

Com a especificação OpenAPI, posso gerar uma coleção Postman completa e 
configurar os testes Newman corretamente.

💡 **Importante**: Newman trabalha melhor quando temos a especificação técnica 
completa dos endpoints, métodos HTTP, headers e schemas de request/response."

**WAIT for user to provide the OpenAPI specification.**

---

**IF FRAMEWORK = KARATE, CYPRESS, or PLAYWRIGHT:**

1. **Has the user provided OpenAPI/technical specification?**
   - Yes: ✓ Technical spec available
   - No: Ask for it (optional, can proceed with scenarios only)

2. **Has the user provided business context (Zephyr test scenarios)?**
   - Yes: ✓ Business context available → PROCEED to delegation
   - No: ⛔ STOP and ask for scenarios (MANDATORY)

You MUST respond in PORTUGUESE:

"📋 Tenho a especificação técnica (OpenAPI/endpoints), mas para gerar 
testes de alta qualidade e assertivos, preciso do contexto de negócio.

Por favor, forneça:

📝 **Cenários de Teste do Zephyr/TestRail**

Inclua:
- IDs e descrições dos casos de teste
- Comportamentos esperados
- Casos extremos (edge cases) a serem cobertos
- Validações de negócio importantes

Isso garante que eu gere testes que validem as REGRAS DE NEGÓCIO reais, 
não apenas códigos HTTP! 🎯"

**WAIT for user to provide the scenarios. DO NOT proceed to test generation.**

---

**IF user provided BOTH required inputs (based on framework):**
✅ Proceed to delegation to qa_refinement_loop

**IF user provided ONLY Zephyr scenarios (no OpenAPI):**
- For Karate/Cypress/Playwright: ✅ Can proceed, but optionally ask if OpenAPI is available
- For Newman: ⛔ MUST have OpenAPI specification - cannot proceed without it

---
""",
    sub_agents=[qa_refinement_loop, git_commit_agent],
)
