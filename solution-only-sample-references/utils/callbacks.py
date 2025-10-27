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
Quality validation callbacks for QA Automation Agent.

This module provides callbacks that execute after agent runs to validate
code quality, detect hallucinations, and ensure production-ready output.
"""

import json
import re
import logging
from typing import Dict, List, Any, Set
from google.adk.agents.callback_context import CallbackContext
from .schemas import QualityMetrics, SyntaxValidation, TestFramework
from .logging_config import create_contextual_logger
from .response_formatter import format_validation_response_for_user, format_refinement_complete_message

logger = create_contextual_logger("qa_automation.callbacks", agent_type="callback_system")


def _extract_last_agent_message(session: Any) -> str:
    """Safely obtain the latest non-empty message emitted by the agent."""

    events = getattr(session, "events", []) if session else []
    for event in reversed(events):
        content = getattr(event, "content", None)
        if not content:
            continue
        text = str(content).strip()
        if text:
            return text
    return ""


def newman_structured_response_callback(callback_context: CallbackContext) -> None:
    """Parse Newman responses into structured data and surface friendly errors."""

    state = callback_context.state
    session = getattr(callback_context._invocation_context, "session", None)

    raw_response = state.get("newman_raw_response") or _extract_last_agent_message(session)

    if not raw_response:
        logger.warning(
            "Newman callback did not receive any response to parse",
            extra_fields={"session_id": getattr(session, "id", "unknown")},
        )
        state["newman_parsing_error"] = "empty_response"
        state["newman_friendly_error"] = (
            "Não encontrei o JSON retornado pelo especialista Newman. Tente executar novamente."
        )
        return

    sanitized_response = raw_response.strip()
    sanitized_response = re.sub(r"^```(?:json)?", "", sanitized_response, flags=re.IGNORECASE)
    sanitized_response = re.sub(r"```$", "", sanitized_response).strip()

    try:
        parsed_response = json.loads(sanitized_response)
    except json.JSONDecodeError as exc:
        logger.error(
            "Failed to parse Newman agent response as JSON",
            extra_fields={"error": str(exc)},
        )
        state["newman_parsing_error"] = "json_decode_error"
        state["newman_friendly_error"] = (
            "A resposta do especialista Newman não está em um formato JSON válido."
            " Peça para o agente gerar novamente garantindo um JSON bem formado."
        )
        state["newman_error_details"] = str(exc)
        return

    required_fields = {
        "collections",
        "environments",
        "scripts",
        "newman_plan",
        "ci_cd",
        "readme",
    }
    missing_fields = [field for field in required_fields if field not in parsed_response]

    if missing_fields:
        logger.error(
            "Newman response is missing required fields",
            extra_fields={"missing_fields": missing_fields},
        )
        state["newman_parsing_error"] = "missing_fields"
        state["newman_missing_fields"] = missing_fields
        state["newman_friendly_error"] = (
            "A resposta do especialista Newman está incompleta: faltam os campos "
            + ", ".join(missing_fields)
            + ". Solicite uma nova geração."
        )
        return

    state.pop("newman_parsing_error", None)
    state.pop("newman_friendly_error", None)
    state["framework"] = "newman"
    state["newman_result"] = parsed_response
    state["newman_collections"] = parsed_response.get("collections", [])
    state["newman_environments"] = parsed_response.get("environments", [])
    state["newman_scripts"] = parsed_response.get("scripts", {})
    state["newman_plan"] = parsed_response.get("newman_plan")
    state["newman_ci_cd"] = parsed_response.get("ci_cd")
    state["newman_readme"] = parsed_response.get("readme")
    state["newman_metadata"] = parsed_response.get("metadata", {})
    state["quality_score"] = parsed_response.get("quality_score")
    state["input_endpoints"] = parsed_response.get("metadata", {}).get("endpoints", [])

    logger.info(
        "Newman response parsed successfully",
        extra_fields={
            "quality_score": state.get("quality_score"),
            "collections": len(state.get("newman_collections", []) or []),
            "environments": len(state.get("newman_environments", []) or []),
        },
    )


def format_user_facing_response_callback(callback_context: CallbackContext) -> None:
    """
    Format technical validation responses into user-friendly messages.

    This callback intercepts validation results and transforms them from
    technical JSON into conversational, helpful messages in Portuguese
    with emojis, visual indicators, and actionable guidance.

    Args:
        callback_context: ADK callback context with session and state
    """
    try:
        state = callback_context.state

        # Check if we have validation results to format
        validation_result = state.get("validation_result")

        if validation_result:
            # Transform technical JSON into friendly message
            friendly_message = format_validation_response_for_user(validation_result)

            # Store the friendly message for user display
            state["user_friendly_message"] = friendly_message

            logger.info("Formatted user-friendly response", extra_fields={
                "original_score": validation_result.get("quality_metrics", {}).get("overall_score", 0),
                "message_length": len(friendly_message)
            })

        # Check if refinement completed successfully
        refinement_complete = state.get("refinement_successful", False)
        if refinement_complete:
            final_data = {
                "overall_score": state.get("best_score", 0),
                "iterations_used": state.get("iteration_count", 0)
            }
            completion_message = format_refinement_complete_message(final_data)
            state["completion_message"] = completion_message

            logger.info("Generated refinement completion message", extra_fields={
                "score": final_data["overall_score"],
                "iterations": final_data["iterations_used"]
            })

    except Exception as e:
        logger.error(f"Error formatting user response: {str(e)}", extra_fields={
            "error_type": type(e).__name__
        })


def validate_code_quality_callback(callback_context: CallbackContext) -> None:
    """
    Comprehensive callback to validate code quality after generation.

    Executes automatically after each sub-agent completes to:
    - Detect hallucinated endpoints
    - Find hardcoded credentials
    - Identify placeholder code
    - Check assertion quality
    - Calculate quality scores

    Args:
        callback_context: ADK callback context with session and state
    """
    try:
        session = callback_context._invocation_context.session
        state = callback_context.state

        logger.info("Starting code quality validation", extra_fields={
            "session_id": session.id if hasattr(session, 'id') else 'unknown'
        })

        # Extract generated code from events
        generated_code = _extract_generated_code(session.events)

        if not generated_code:
            logger.warning("No code found in session events")
            return

        # Get input specification for validation
        input_endpoints = state.get("input_endpoints", [])
        framework = state.get("framework", "unknown")

        # Run all validation checks
        metrics = {
            "syntax_errors": _check_syntax_errors(generated_code, framework),
            "hallucinated_endpoints": _detect_hallucinations(
                generated_code,
                input_endpoints
            ),
            "hardcoded_credentials": _detect_hardcoded_secrets(generated_code),
            "placeholder_usage": _detect_placeholders(generated_code),
            "assertion_quality": _check_assertion_quality(generated_code, framework),
            "best_practices_violations": _check_best_practices(generated_code, framework),
        }

        # Calculate overall quality score
        quality_score = _calculate_quality_score(metrics)

        # Store in state for access by the agent
        state["quality_metrics"] = metrics
        state["quality_score"] = quality_score

        logger.info("Code quality validation completed", extra_fields={
            "quality_score": quality_score,
            "syntax_errors": len(metrics["syntax_errors"]),
            "hallucinations": len(metrics["hallucinated_endpoints"]),
            "hardcoded_secrets": len(metrics["hardcoded_credentials"])
        })

        # CRITICAL: Flag if quality is too low
        if quality_score < 50:
            logger.error("Quality score below acceptable threshold", extra_fields={
                "score": quality_score,
                "threshold": 50,
                "issues": _format_critical_issues(metrics)
            })
            state["requires_regeneration"] = True
            state["regeneration_reason"] = _format_critical_issues(metrics)

    except Exception as e:
        logger.error("Error in quality validation callback", extra_fields={
            "error": str(e),
            "error_type": type(e).__name__
        }, exc_info=True)


def _extract_generated_code(events: List[Any]) -> str:
    """Extract code content from session events."""
    code_parts = []

    for event in events:
        if hasattr(event, 'content'):
            content = str(event.content)
            # Look for code blocks
            code_blocks = re.findall(r'```[\w]*\n(.*?)\n```', content, re.DOTALL)
            code_parts.extend(code_blocks)

            # Also capture plain text that looks like code
            if any(keyword in content for keyword in ['function', 'describe', 'Feature:', 'Scenario:', 'def ', 'class ']):
                code_parts.append(content)

    return '\n'.join(code_parts)


def _check_syntax_errors(code: str, framework: str) -> List[str]:
    """
    Check for common syntax errors based on framework.

    Returns:
        List of syntax error descriptions
    """
    errors = []

    if framework in ['cypress', 'playwright']:
        # JavaScript/TypeScript syntax checks
        if code.count('(') != code.count(')'):
            errors.append("Mismatched parentheses")
        if code.count('{') != code.count('}'):
            errors.append("Mismatched curly braces")
        if code.count('[') != code.count(']'):
            errors.append("Mismatched square brackets")

        # Check for common mistakes
        if re.search(r'cy\.wait\(\d+\)', code):
            errors.append("Using arbitrary cy.wait() - anti-pattern")
        if re.search(r'\.should\(\s*\)', code):
            errors.append("Empty .should() assertion")

    elif framework == 'karate':
        # Karate/Gherkin syntax checks
        if '//' in code and 'Feature:' in code:
            errors.append("Using // comments in Gherkin (should use #)")

        if 'karate.parallel(' in code:
            errors.append("karate.parallel() does not exist in Karate DSL")

        if re.search(r'status:\s*["\']active["\']', code) and 'regex' not in code:
            errors.append("Hardcoded status value - should use #regex for flexibility")

    elif framework == 'newman':
        # JSON validation for Postman collections
        try:
            import json
            # Try to find JSON structures
            json_blocks = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', code)
            for block in json_blocks[:5]:  # Check first 5 blocks
                try:
                    json.loads(block)
                except json.JSONDecodeError as e:
                    errors.append(f"Invalid JSON structure: {str(e)[:100]}")
        except Exception:
            pass

    return errors


def _detect_hallucinations(code: str, allowed_endpoints: List[str]) -> List[str]:
    """
    Detect hallucinated (invented) endpoints that weren't in the specification.

    This is CRITICAL for preventing AI from making up APIs that don't exist.

    Args:
        code: Generated code
        allowed_endpoints: List of actual endpoints from spec

    Returns:
        List of hallucinated endpoints found
    """
    hallucinations = []

    if not allowed_endpoints:
        logger.warning("No allowed endpoints provided for hallucination detection")
        return hallucinations

    # Extract paths from code using multiple patterns
    path_patterns = [
        r'path\s+["\']([^"\']+)["\']',  # Karate: path 'api', 'users'
        r'path\(["\']([^"\']+)["\']',    # Karate: path('api')
        r'url:\s*["\']([^"\']+)["\']',   # Newman: url: "..."
        r'cy\.request\(["\']([^"\']+)["\']',  # Cypress: cy.request('...')
        r'\.get\(["\']([^"\']+)["\']',   # Various: .get('...')
        r'\.post\(["\']([^"\']+)["\']',  # Various: .post('...')
        r'\.visit\(["\']([^"\']+)["\']', # Cypress: cy.visit('...')
        r'Given url ["\']([^"\']+)["\']', # Karate BDD
    ]

    found_paths = set()
    for pattern in path_patterns:
        matches = re.findall(pattern, code, re.IGNORECASE)
        found_paths.update(matches)

    # Normalize allowed endpoints for comparison
    normalized_allowed = set()
    for endpoint in allowed_endpoints:
        if isinstance(endpoint, dict):
            path = endpoint.get('path', '')
        else:
            path = str(endpoint)

        # Normalize path
        path = path.strip().lstrip('/')
        normalized_allowed.add(path)

    # Check each found path
    for path in found_paths:
        # Skip variable placeholders and base URLs
        if path.startswith(('http://', 'https://', 'base', '{{', '${')):
            continue

        path_normalized = path.strip().lstrip('/')

        # Check if path is in allowed list (partial match for flexibility)
        is_valid = any(
            allowed in path_normalized or path_normalized in allowed
            for allowed in normalized_allowed
        )

        if not is_valid and len(path_normalized) > 3:
            hallucinations.append(f"Hallucinated endpoint: {path}")

    return list(set(hallucinations))  # Remove duplicates


def _detect_hardcoded_secrets(code: str) -> List[str]:
    """
    Detect hardcoded credentials, API keys, tokens, etc.

    Smart detection that ignores:
    - OpenAPI specification examples
    - Test/example credentials (test@, example.com, etc.)
    - Environment variable references
    - Template variables

    Returns:
        List of security issues found
    """
    issues = []

    # Patterns for detecting REAL hardcoded secrets (not examples)
    secret_patterns = [
        # Real API keys (long alphanumeric, not example patterns)
        (r'api[_-]?key\s*[:=]\s*["\'](?!{{)(?!\$\{)(?!process\.env)(?!test)(?!example)(?!demo)([A-Za-z0-9]{32,})["\']',
         "Hardcoded API key (production-like)"),

        # Real tokens (very long, not test tokens)
        (r'token\s*[:=]\s*["\'](?!{{)(?!\$\{)(?!process\.env)(?!test)(?!example)(?!eyJhbGc)([A-Za-z0-9\-_\.]{40,})["\']',
         "Hardcoded token (production-like)"),

        # Bearer tokens that look real (not examples like "eyJhbGc...")
        (r'bearer\s+(?!{{)(?!\$\{)(?!eyJhbGc)(?!test)([A-Za-z0-9\-_\.]{40,})',
         "Hardcoded bearer token (production-like)"),

        # AWS keys
        (r'AKIA[0-9A-Z]{16}',
         "Hardcoded AWS access key"),

        # Real passwords (not test passwords, must be complex)
        (r'password\s*[:=]\s*["\'](?!{{)(?!\$\{)(?!process\.env)(?!test)(?!example)(?!demo)(?!password)(?!123)(?!Pass)(?!Bank)([A-ZaZ0-9!@#$%^&*]{15,})["\']',
         "Hardcoded complex password (production-like)"),
    ]

    # Safe patterns that should be ignored (test/example data)
    safe_patterns = [
        r'test\.banking@example\.com',  # Example from OpenAPI spec
        r'test@test\.com',
        r'user@example\.com',
        r'BankTest@\d{4}',  # Test passwords like BankTest@2024
        r'Test\w+@\d{4}',
        r'example\.com',
        r'eyJhbGc',  # JWT example tokens that start with "eyJhbGc"
        r'\{\{.*\}\}',  # Template variables
        r'\$\{.*\}',  # Environment variables
        r'process\.env\.',
        r'Bearer\s+\$\{',
        r'Bearer\s+\{\{',
    ]

    # Check if code contains safe patterns - if yes, be more lenient
    has_safe_patterns = any(re.search(pattern, code, re.IGNORECASE) for pattern in safe_patterns)

    for pattern, message in secret_patterns:
        matches = re.findall(pattern, code, re.IGNORECASE)
        if matches:
            # Filter out matches that contain safe keywords
            real_secrets = []
            for match in matches:
                match_str = str(match)
                # Skip if it looks like test data
                if not any(keyword in match_str.lower() for keyword in ['test', 'example', 'demo', 'sample', 'mock']):
                    real_secrets.append(match)

            if real_secrets:
                issues.append(f"{message} (found {len(real_secrets)} occurrence(s))")

    # Only flag email+password if it looks like REAL credentials (not test data)
    email_password_pattern = r'([\w\.-]+@(?!example\.com)(?!test\.com)[\w\.-]+\.\w+).*password.*["\']([^"\']+)["\']'
    matches = re.findall(email_password_pattern, code, re.IGNORECASE)

    # Filter out test credentials
    real_credentials = [m for m in matches if not any(
        test_word in str(m).lower()
        for test_word in ['test', 'example', 'demo', 'sample']
    )]

    if real_credentials:
        issues.append("Potential production credentials (email + password) in plain text")

    return issues


def _detect_placeholders(code: str) -> List[str]:
    """
    Detect placeholder text that indicates incomplete code generation.

    Returns:
        List of placeholder issues
    """
    placeholders = []

    placeholder_patterns = [
        (r'\bTODO\b', "TODO comment"),
        (r'\bFIXME\b', "FIXME comment"),
        (r'\bXXX\b', "XXX comment"),
        (r'placeholder', "Literal 'placeholder' text"),
        (r'test@test\.com', "Generic test email"),
        (r'example\.com', "Example domain"),
        (r'your[_-]api[_-]key', "Placeholder API key"),
        (r'replace[_-]?this', "Replace-this placeholder"),
        (r'<[A-Z_]+>', "Template variable placeholder"),
        (r'\.\.\.', "Ellipsis placeholder"),
    ]

    for pattern, description in placeholder_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            placeholders.append(description)

    return placeholders


def _check_assertion_quality(code: str, framework: str) -> Dict[str, Any]:
    """
    Check quality of assertions in test code.

    Returns:
        Dictionary with assertion quality metrics
    """
    quality = {
        "total_assertions": 0,
        "specific_assertions": 0,
        "generic_assertions": 0,
        "quality_ratio": 0.0,
        "issues": []
    }

    if framework in ['cypress', 'playwright']:
        # Count assertions
        quality["total_assertions"] = len(re.findall(r'\.should\(|expect\(', code))

        # Check for specific assertions
        specific_patterns = [
            r'\.should\(["\']have\.length["\']',
            r'\.should\(["\']equal["\']',
            r'\.should\(["\']contain["\']',
            r'expect\(.*\)\.to\.(equal|be\.|have\.)',
        ]

        for pattern in specific_patterns:
            quality["specific_assertions"] += len(re.findall(pattern, code))

        # Check for generic assertions (bad)
        if re.search(r'\.should\(["\']exist["\']', code):
            quality["generic_assertions"] += 1
            quality["issues"].append("Using generic 'exist' assertion")

    elif framework == 'karate':
        # Count match statements
        quality["total_assertions"] = len(re.findall(r'\bAnd match\b|\bThen match\b', code))

        # Check for specific matchers
        if re.search(r'match.*#string|#number|#regex', code):
            quality["specific_assertions"] = len(re.findall(r'#string|#number|#regex', code))

        # Check for generic matchers
        if re.search(r'match response == \{\}', code):
            quality["generic_assertions"] += 1
            quality["issues"].append("Empty response match")

    # Calculate quality ratio
    if quality["total_assertions"] > 0:
        quality["quality_ratio"] = quality["specific_assertions"] / quality["total_assertions"]

    return quality


def _check_best_practices(code: str, framework: str) -> List[str]:
    """Check for violations of framework best practices."""
    violations = []

    if framework == 'cypress':
        if re.search(r'cy\.wait\(\d{4,}\)', code):
            violations.append("Long arbitrary wait times (use proper assertions instead)")

        if re.search(r'\.click\(\).*\.click\(\)', code, re.DOTALL):
            violations.append("Multiple clicks without assertions between")

        if not re.search(r'describe\(|it\(', code):
            violations.append("Missing test structure (describe/it blocks)")

    elif framework == 'karate':
        if not re.search(r'Feature:', code):
            violations.append("Missing Feature declaration")

        if not re.search(r'Scenario:', code):
            violations.append("Missing Scenario declarations")

        if re.search(r'@Test.*@Karate\.Test', code, re.DOTALL):
            violations.append("Redundant @Test with @Karate.Test")

    elif framework == 'playwright':
        if not re.search(r'test\(|test\.describe\(', code):
            violations.append("Missing Playwright test structure")

        if re.search(r'page\.waitForTimeout\(\d+\)', code):
            violations.append("Using waitForTimeout (anti-pattern, use waitForSelector)")

    return violations


def _calculate_quality_score(metrics: Dict[str, Any]) -> int:
    """
    Calculate overall quality score (0-100).

    Scoring:
    - Start at 100
    - Deduct points for each issue category
    - Critical issues (hallucinations, secrets) deduct more points
    """
    score = 100

    # Critical deductions
    score -= len(metrics.get("syntax_errors", [])) * 15
    score -= len(metrics.get("hallucinated_endpoints", [])) * 20
    score -= len(metrics.get("hardcoded_credentials", [])) * 25

    # Moderate deductions
    score -= len(metrics.get("placeholder_usage", [])) * 5
    score -= len(metrics.get("best_practices_violations", [])) * 3

    # Assertion quality bonus/penalty
    assertion_metrics = metrics.get("assertion_quality", {})
    quality_ratio = assertion_metrics.get("quality_ratio", 0.5)
    score += int((quality_ratio - 0.5) * 20)  # -10 to +10 based on quality

    return max(0, min(100, score))


def _format_critical_issues(metrics: Dict[str, Any]) -> str:
    """Format critical issues for error reporting."""
    critical = []

    if metrics.get("syntax_errors"):
        critical.append(f"Syntax errors: {', '.join(metrics['syntax_errors'][:3])}")

    if metrics.get("hallucinated_endpoints"):
        critical.append(f"Hallucinations: {', '.join(metrics['hallucinated_endpoints'][:3])}")

    if metrics.get("hardcoded_credentials"):
        critical.append(f"Security: {', '.join(metrics['hardcoded_credentials'][:2])}")

    return '; '.join(critical) if critical else "Multiple quality issues detected"


def collect_generation_metrics_callback(callback_context: CallbackContext) -> None:
    """
    Collect metrics about test generation process.

    Tracks:
    - Number of files generated
    - Endpoints covered
    - Generation time
    - Model calls made
    """
    try:
        state = callback_context.state
        session = callback_context._invocation_context.session

        metrics = {
            "files_generated": state.get("files_generated", 0),
            "endpoints_covered": len(state.get("endpoints_covered", [])),
            "total_events": len(session.events) if hasattr(session, 'events') else 0,
        }

        state["generation_metrics"] = metrics

        logger.info("Generation metrics collected", extra_fields=metrics)

    except Exception as e:
        logger.error("Error collecting generation metrics", extra_fields={
            "error": str(e)
        })
