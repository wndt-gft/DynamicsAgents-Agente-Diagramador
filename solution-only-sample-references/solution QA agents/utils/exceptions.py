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
Custom exceptions for QA Automation Agent.

This module defines a comprehensive hierarchy of exceptions for proper error handling
and reporting throughout the QA automation agent system.
"""

from typing import Optional, Dict, Any


class QAAgentException(Exception):
    """Base exception for all QA Automation Agent errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Initialize QA Agent exception.

        Args:
            message: Human-readable error message
            details: Additional context about the error
        """
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return string representation with details."""
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


# Configuration Exceptions
class ConfigurationError(QAAgentException):
    """Raised when there's an error in agent configuration."""
    pass


class InvalidModelError(ConfigurationError):
    """Raised when an invalid AI model is specified."""
    pass


class MissingCredentialsError(ConfigurationError):
    """Raised when required credentials are missing."""
    pass


class EnvironmentVariableError(ConfigurationError):
    """Raised when required environment variables are not set."""
    pass


# Generation Exceptions
class GenerationError(QAAgentException):
    """Base exception for test generation errors."""
    pass


class TestGenerationError(GenerationError):
    """Raised when test generation fails."""
    pass


class TemplateRenderError(GenerationError):
    """Raised when template rendering fails."""
    pass


class CodeGenerationError(GenerationError):
    """Raised when code generation produces invalid output."""
    pass


# Validation Exceptions
class ValidationError(QAAgentException):
    """Base exception for validation errors."""
    pass


class InvalidInputError(ValidationError):
    """Raised when input parameters are invalid."""
    pass


class QualityThresholdError(ValidationError):
    """Raised when generated code doesn't meet quality thresholds."""
    pass


class SyntaxValidationError(ValidationError):
    """Raised when generated code has syntax errors."""
    pass


# Framework-Specific Exceptions
class FrameworkError(QAAgentException):
    """Base exception for framework-specific errors."""
    pass


class CypressError(FrameworkError):
    """Raised for Cypress-specific errors."""
    pass


class KarateError(FrameworkError):
    """Raised for Karate-specific errors."""
    pass


class NewmanError(FrameworkError):
    """Raised for Newman/Postman-specific errors."""
    pass


class PlaywrightError(FrameworkError):
    """Raised for Playwright-specific errors."""
    pass


# Integration Exceptions
class IntegrationError(QAAgentException):
    """Base exception for external integration errors."""
    pass


class TMJIntegrationError(IntegrationError):
    """Raised for TMJ/Jira integration errors."""
    pass


class BitbucketIntegrationError(IntegrationError):
    """Raised for Bitbucket integration errors."""
    pass


class APIError(IntegrationError):
    """Raised for general API communication errors."""
    pass


class AuthenticationError(IntegrationError):
    """Raised when authentication to external service fails."""
    pass


# Agent Execution Exceptions
class AgentExecutionError(QAAgentException):
    """Base exception for agent execution errors."""
    pass


class ToolExecutionError(AgentExecutionError):
    """Raised when a tool execution fails."""
    pass


class OrchestratorError(AgentExecutionError):
    """Raised when orchestrator coordination fails."""
    pass


class SubAgentError(AgentExecutionError):
    """Raised when a sub-agent encounters an error."""
    pass


# Timeout and Resource Exceptions
class TimeoutError(QAAgentException):
    """Raised when an operation times out."""
    pass


class ResourceExhaustedError(QAAgentException):
    """Raised when system resources are exhausted."""
    pass


class RateLimitError(QAAgentException):
    """Raised when API rate limits are exceeded."""
    pass

