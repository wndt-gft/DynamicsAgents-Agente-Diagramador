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
Structured logging configuration for QA Automation Agent.

This module provides centralized logging configuration with structured output,
contextual information, and proper formatting for production environments.
"""

import logging
import logging.handlers
import sys
import os
import json
from typing import Any, Dict, Optional
from datetime import datetime
from pathlib import Path


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as structured JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info)
            }

        # Add custom fields from extra parameter
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class ContextFilter(logging.Filter):
    """Filter to add contextual information to log records."""

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        """
        Initialize context filter.

        Args:
            context: Default context to add to all logs
        """
        super().__init__()
        self.context = context or {}

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context to log record."""
        if not hasattr(record, "extra_fields"):
            record.extra_fields = {}
        record.extra_fields.update(self.context)
        return True


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    log_file: Optional[str] = None,
    enable_console: bool = True,
    context: Optional[Dict[str, Any]] = None
) -> logging.Logger:
    """
    Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Format type ('json' or 'text')
        log_file: Optional file path for logging to file
        enable_console: Whether to enable console logging
        context: Default context to add to all logs

    Returns:
        Configured logger instance
    """
    # Get log level from environment or parameter
    level_name = os.getenv("QA_LOG_LEVEL", log_level).upper()
    level = getattr(logging, level_name, logging.INFO)

    # Create root logger
    logger = logging.getLogger("qa_automation")
    logger.setLevel(level)
    logger.handlers.clear()

    # Add context filter
    if context:
        logger.addFilter(ContextFilter(context))

    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)

        if log_format == "json":
            console_handler.setFormatter(StructuredFormatter())
        else:
            console_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))

        logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(level)

        if log_format == "json":
            file_handler.setFormatter(StructuredFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))

        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(f"qa_automation.{name}")


class LoggerAdapter(logging.LoggerAdapter):
    """Custom logger adapter for adding contextual information."""

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """
        Process log message and add extra fields.

        Args:
            msg: Log message
            kwargs: Keyword arguments

        Returns:
            Processed message and kwargs
        """
        # Initialize extra if not present
        if "extra" not in kwargs:
            kwargs["extra"] = {}

        # Initialize extra_fields if not present
        if "extra_fields" not in kwargs["extra"]:
            kwargs["extra"]["extra_fields"] = {}

        # Add adapter context to extra_fields
        kwargs["extra"]["extra_fields"].update(self.extra)

        # If user passed extra_fields directly, merge them
        if "extra_fields" in kwargs:
            kwargs["extra"]["extra_fields"].update(kwargs.pop("extra_fields"))

        return msg, kwargs


def create_contextual_logger(
    name: str,
    **context: Any
) -> LoggerAdapter:
    """
    Create a logger with permanent context.

    Args:
        name: Logger name
        **context: Context key-value pairs

    Returns:
        Logger adapter with context

    Example:
        logger = create_contextual_logger(
            "cypress_expert",
            framework="cypress",
            domain="ecommerce"
        )
        logger.info("Generating tests")  # Will include framework and domain
    """
    base_logger = get_logger(name)
    return LoggerAdapter(base_logger, context)


# Initialize default logger
default_logger = setup_logging(
    log_level=os.getenv("QA_LOG_LEVEL", "INFO"),
    log_format=os.getenv("QA_LOG_FORMAT", "json"),
    log_file=os.getenv("QA_LOG_FILE"),
    enable_console=True,
    context={
        "service": "qa_automation_agent",
        "version": "1.0.0",
        "environment": os.getenv("ENVIRONMENT", "development")
    }
)
