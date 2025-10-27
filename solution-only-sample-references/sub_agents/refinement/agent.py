"""
Refinement Loop System - Iterative Quality Improvement.

This module implements a feedback loop where the Validation Agent can send
code back to the generator agents for refinement when quality issues are found.
"""

import os
from typing import Optional
from google.adk import Agent
from google.adk.models import llm_response
from google.adk.models import llm_request
from google.adk.plugins import base_plugin
from google.genai import types

from ...utils.logging_config import create_contextual_logger
from .prompt import REFINEMENT_ORCHESTRATOR_PROMPT

logger = create_contextual_logger(
    "qa_automation.refinement",
    framework="refinement_loop",
    agent_type="orchestrator"
)

MODEL = os.getenv("QA_MODEL", "gemini-2.5-pro")
MAX_REFINEMENT_ITERATIONS = 3
QUALITY_THRESHOLD = 70


# ============================================================================
# CALLBACK FUNCTIONS - State Management
# ============================================================================

def init_refinement_loop_state(
    callback_context: base_plugin.CallbackContext
) -> Optional[types.Content]:
    """
    Initialize refinement loop state before starting iterations.

    Sets up tracking variables for the refinement loop:
    - iteration_count: Number of refinement attempts
    - quality_scores: History of quality scores
    - issues_fixed: List of issues that were fixed
    - issues_remaining: List of issues still pending
    - refinement_successful: Whether refinement achieved target quality
    """
    logger.info("Initializing refinement loop state", extra_fields={
        "max_iterations": MAX_REFINEMENT_ITERATIONS,
        "quality_threshold": QUALITY_THRESHOLD
    })

    callback_context.state["iteration_count"] = 0
    callback_context.state["quality_scores"] = []
    callback_context.state["issues_fixed"] = []
    callback_context.state["issues_remaining"] = []
    callback_context.state["refinement_successful"] = False
    callback_context.state["best_code"] = None
    callback_context.state["best_score"] = 0

    # ✅ Initialize ALL variables that ADK template system might look for
    # This prevents "Context variable not found" errors
    # Common API testing variables
    callback_context.state["base_url"] = ""
    callback_context.state["api_url"] = ""
    callback_context.state["endpoint"] = ""
    callback_context.state["framework"] = ""
    callback_context.state["access_token"] = ""
    callback_context.state["token"] = ""
    callback_context.state["api_key"] = ""
    callback_context.state["username"] = ""
    callback_context.state["password"] = ""
    callback_context.state["auth_token"] = ""
    callback_context.state["bearer_token"] = ""
    callback_context.state["jwt_token"] = ""
    # Common test data variables
    callback_context.state["account_id"] = ""
    callback_context.state["user_id"] = ""
    callback_context.state["transaction_id"] = ""
    callback_context.state["request_id"] = ""
    callback_context.state["session_id"] = ""
    callback_context.state["idempotency_key"] = ""
    # Environment variables
    callback_context.state["environment"] = ""
    callback_context.state["env"] = ""
    callback_context.state["stage"] = ""
    # Request/Response variables
    callback_context.state["method"] = ""
    callback_context.state["path"] = ""
    callback_context.state["query_params"] = ""
    callback_context.state["headers"] = ""
    callback_context.state["body"] = ""
    callback_context.state["response"] = ""
    callback_context.state["status_code"] = ""
    # Generic placeholders that might appear in prompt examples
    callback_context.state["variable"] = ""
    callback_context.state["var_name"] = ""
    callback_context.state["value"] = ""
    callback_context.state["key"] = ""
    callback_context.state["name"] = ""
    callback_context.state["id"] = ""
    callback_context.state["data"] = ""
    callback_context.state["result"] = ""
    callback_context.state["output"] = ""
    callback_context.state["input"] = ""

    return None


def update_refinement_iteration(
    callback_context: base_plugin.CallbackContext
) -> Optional[types.Content]:
    """
    Update iteration counter after each refinement cycle and check for early exit.

    Tracks the current iteration and logs progress.
    Checks if quality threshold is met and signals loop to stop if needed.

    Returns:
        Content with stop signal if quality >= 70, None otherwise
    """
    current_iteration = callback_context.state.get("iteration_count", 0)
    callback_context.state["iteration_count"] = current_iteration + 1

    # Get quality score from validate_code_quality_callback
    overall_score = callback_context.state.get("quality_score", 0)
    quality_metrics = callback_context.state.get("quality_metrics", {})

    # Check if code requires regeneration (critical issues)
    requires_regeneration = callback_context.state.get("requires_regeneration", False)
    can_proceed = overall_score >= 50 and not requires_regeneration

    # Track score history
    quality_scores = callback_context.state.get("quality_scores", [])
    if overall_score > 0:  # Only track if we have a real score
        quality_scores.append(overall_score)
        callback_context.state["quality_scores"] = quality_scores

    # Update best result if current is better
    if overall_score > callback_context.state.get("best_score", 0):
        callback_context.state["best_score"] = overall_score
        callback_context.state["best_code"] = callback_context.state.get("generated_code")

    logger.info("Refinement iteration completed", extra_fields={
        "iteration": current_iteration + 1,
        "max_iterations": MAX_REFINEMENT_ITERATIONS,
        "current_score": overall_score,
        "best_score": callback_context.state.get("best_score", 0)
    })

    # ✅ CRITICAL FIX: Force early exit by manipulating iteration count
    # Early exit condition: Quality threshold met
    if can_proceed and overall_score >= QUALITY_THRESHOLD:
        callback_context.state["refinement_successful"] = True
        logger.info("Quality threshold met - forcing loop termination", extra_fields={
            "final_score": overall_score,
            "iterations_used": current_iteration + 1,
            "threshold": QUALITY_THRESHOLD
        })
        # Force the loop to stop by setting iteration_count to max
        # This is a workaround for ADK LoopAgent limitation
        callback_context.state["iteration_count"] = MAX_REFINEMENT_ITERATIONS

    # Log progress if continuing
    elif overall_score > 0:
        logger.info("Quality below threshold - continuing refinement", extra_fields={
            "current_score": overall_score,
            "target_score": QUALITY_THRESHOLD,
            "iteration": current_iteration + 1,
            "remaining_iterations": MAX_REFINEMENT_ITERATIONS - (current_iteration + 1)
        })

    return None


def check_quality_threshold(
    callback_context: base_plugin.CallbackContext,
    llm_req: llm_request.LlmRequest,
) -> Optional[llm_response.LlmResponse]:
    """
    Check if quality threshold is met (early exit condition).

    This function implements early exit logic to stop the refinement loop when:
    1. Quality score meets or exceeds the threshold (>= 70)
    2. Maximum iterations reached

    Returns:
        LlmResponse (empty) if loop should stop, None if loop should continue
    """
    iteration_count = callback_context.state.get("iteration_count", 0)

    # Get quality score from validate_code_quality_callback
    overall_score = callback_context.state.get("quality_score", 0)
    quality_metrics = callback_context.state.get("quality_metrics", {})

    # Check if code requires regeneration (critical issues)
    requires_regeneration = callback_context.state.get("requires_regeneration", False)
    can_proceed = overall_score >= 50 and not requires_regeneration

    # ✅ CRITICAL FIX: Check if loop should stop FIRST
    loop_should_stop = callback_context.state.get("loop_should_stop", False)
    if loop_should_stop:
        logger.info("Loop stop flag detected - forcing early exit", extra_fields={
            "iteration": iteration_count,
            "score": overall_score
        })
        # Return empty response to stop the loop
        return llm_response.LlmResponse(
            response_parts=[types.Part(text="Quality threshold met. Stopping refinement loop.")]
        )

    # Early exit condition 1: Quality threshold met
    if can_proceed and overall_score >= QUALITY_THRESHOLD:
        callback_context.state["refinement_successful"] = True
        callback_context.state["loop_should_stop"] = True
        logger.info("Quality threshold met - forcing loop termination", extra_fields={
            "final_score": overall_score,
            "iterations_used": iteration_count,
            "threshold": QUALITY_THRESHOLD
        })
        # Return empty response with completion message to stop the loop
        return llm_response.LlmResponse(
            response_parts=[types.Part(text=f"Quality threshold achieved (score: {overall_score}). Refinement complete.")]
        )

    # Early exit condition 2: Maximum iterations reached
    if iteration_count >= MAX_REFINEMENT_ITERATIONS:
        callback_context.state["loop_should_stop"] = True
        logger.warning("Maximum iterations reached - forcing loop termination", extra_fields={
            "final_score": overall_score,
            "iterations": iteration_count,
            "target_threshold": QUALITY_THRESHOLD,
            "threshold_met": False
        })
        # Return empty response to stop the loop
        return llm_response.LlmResponse(
            response_parts=[types.Part(text=f"Maximum iterations ({MAX_REFINEMENT_ITERATIONS}) reached. Best score: {overall_score}.")]
        )

    # Continue loop - quality not sufficient yet
    if overall_score > 0:  # Only log if we have a score to report
        logger.info("Quality below threshold - continuing refinement", extra_fields={
            "current_score": overall_score,
            "target_score": QUALITY_THRESHOLD,
            "iteration": iteration_count,
            "remaining_iterations": MAX_REFINEMENT_ITERATIONS - iteration_count
        })

    return None


def track_refinement_metrics(
    callback_context: base_plugin.CallbackContext
) -> Optional[types.Content]:
    """
    Track and log refinement metrics at the end of loop.

    Provides summary of the refinement process including:
    - Total iterations
    - Score progression
    - Best result achieved
    - Success status
    """
    iteration_count = callback_context.state.get("iteration_count", 0)
    quality_scores = callback_context.state.get("quality_scores", [])
    best_score = callback_context.state.get("best_score", 0)
    refinement_successful = callback_context.state.get("refinement_successful", False)

    # Calculate score improvement
    if len(quality_scores) > 1:
        initial_score = quality_scores[0]
        final_score = quality_scores[-1]
        improvement = final_score - initial_score
    else:
        initial_score = quality_scores[0] if quality_scores else 0
        final_score = initial_score
        improvement = 0

    logger.info("Refinement loop completed", extra_fields={
        "total_iterations": iteration_count,
        "initial_score": initial_score,
        "final_score": final_score,
        "best_score": best_score,
        "improvement": improvement,
        "success": refinement_successful,
        "score_history": quality_scores
    })

    return None


# ============================================================================
# REFINEMENT ORCHESTRATOR AGENT - Using LoopAgent Pattern
# ============================================================================

try:
    logger.info("Initializing Refinement Orchestrator with LoopAgent", extra_fields={
        "model": MODEL,
        "max_iterations": MAX_REFINEMENT_ITERATIONS,
        "quality_threshold": QUALITY_THRESHOLD
    })

    # Core refinement agent that orchestrates generation and validation
    refinement_orchestrator = Agent(
        model=MODEL,
        name="refinement_orchestrator",
        description=(
            "Orchestrates iterative refinement between code generation and validation "
            "to ensure high-quality test code output"
        ),
        instruction=REFINEMENT_ORCHESTRATOR_PROMPT,
        output_key="refined_output",
    )

    # NOTE: The LoopAgent structure will be created at the parent level
    # (in agent.py) by wrapping this refinement_orchestrator in a SequentialAgent
    # with validator and then wrapping both in a LoopAgent.
    #
    # Expected structure:
    # LoopAgent(
    #     sub_agents=[
    #         SequentialAgent([
    #             generator_agent,
    #             validator_agent,
    #             refinement_orchestrator  # Provides feedback for next iteration
    #         ])
    #     ],
    #     before_agent_callback=init_refinement_loop_state,
    #     after_agent_callback=update_refinement_iteration,
    #     before_model_callback=check_quality_threshold,
    #     max_iterations=MAX_REFINEMENT_ITERATIONS
    # )

    logger.info("Refinement Orchestrator initialized successfully", extra_fields={
        "agent_name": "refinement_orchestrator",
        "status": "ready",
        "callback_functions_defined": [
            "init_refinement_loop_state",
            "update_refinement_iteration",
            "check_quality_threshold",
            "track_refinement_metrics"
        ]
    })

except Exception as e:
    logger.error("Failed to initialize Refinement Orchestrator", extra_fields={
        "error_type": type(e).__name__,
        "error": str(e)
    }, exc_info=True)
    raise
