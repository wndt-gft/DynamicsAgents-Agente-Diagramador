"""Configuração centralizada de logging estruturado para o agente Diagramador."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

LOGGER_ROOT = "diagramador"


class StructuredFormatter(logging.Formatter):
    """Formatter que emite logs em JSON com campos contextuais."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            payload["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)

        return json.dumps(payload, ensure_ascii=False)


class ContextFilter(logging.Filter):
    """Filtro que injeta contexto padrão em cada registro de log."""

    def __init__(self, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__()
        self._context = context or {}

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "extra_fields"):
            record.extra_fields = {}
        record.extra_fields = {**self._context, **record.extra_fields}
        return True


class LoggerAdapter(logging.LoggerAdapter):
    """Adapter que adiciona contexto dinâmico aos registros."""

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        extra = kwargs.setdefault("extra", {})
        extra_fields = extra.setdefault("extra_fields", {})
        extra_fields.update(self.extra)
        user_extra = kwargs.pop("extra_fields", None)
        if isinstance(user_extra, dict):
            extra_fields.update(user_extra)
        return msg, kwargs


def setup_logging(
    *,
    log_level: str | None = None,
    log_format: str | None = None,
    log_file: str | None = None,
    enable_console: bool = True,
    context: Optional[Dict[str, Any]] = None,
) -> logging.Logger:
    """Configura o logger raiz utilizado pelo agente Diagramador."""

    level_name = (log_level or os.getenv("DIAGRAMADOR_LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    format_name = (log_format or os.getenv("DIAGRAMADOR_LOG_FORMAT", "json")).lower()
    file_path = log_file or os.getenv("DIAGRAMADOR_LOG_FILE")

    logger = logging.getLogger(LOGGER_ROOT)
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    if context:
        logger.addFilter(ContextFilter(context))

    handler_format: logging.Formatter
    if format_name == "json":
        handler_format = StructuredFormatter()
    else:
        handler_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(handler_format)
        logger.addHandler(console_handler)

    if file_path:
        log_path = Path(file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(handler_format)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Obtém um logger filho com o prefixo padrão."""

    return logging.getLogger(f"{LOGGER_ROOT}.{name}")


def create_contextual_logger(name: str, **context: Any) -> LoggerAdapter:
    """Cria um logger com contexto adicional fixo."""

    base_logger = get_logger(name)
    return LoggerAdapter(base_logger, context)


default_logger = setup_logging(
    context={
        "service": "diagramador_agent",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "version": os.getenv("DIAGRAMADOR_VERSION", "1.0.0"),
    }
)


__all__ = ["setup_logging", "get_logger", "create_contextual_logger", "LoggerAdapter"]
