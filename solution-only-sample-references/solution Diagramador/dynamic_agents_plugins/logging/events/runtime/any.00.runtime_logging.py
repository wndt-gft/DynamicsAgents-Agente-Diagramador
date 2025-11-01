import logging
from typing import Any, Dict

from dynamic_agents.runtime import (
    ICON_AGENT,
    ICON_CALLBACK,
    ICON_ERROR,
    ICON_EVENT,
    ICON_STATE,
    ICON_STEP,
    ICON_TOOL,
    RUNTIME_LOGGING_PLUGIN_NAME,
    RuntimeEvent,
    RuntimePlugin,
    _stringify_object,
    _stringify_payload,
    logger,
)


class RuntimeLoggingPlugin(RuntimePlugin):
    """Plugin that mirrors emitted events to the runtime logger."""

    PLUGIN_NAME = RUNTIME_LOGGING_PLUGIN_NAME

    def __init__(self, *, log_level: int = logging.INFO, debug_payload: bool = True):
        self.log_level = log_level
        self.debug_payload = debug_payload

    def handle_event(self, event: RuntimeEvent) -> None:  # pragma: no cover - exercised via integration tests
        event_name = event.name or ""
        is_error = event_name.endswith("error")
        level = logging.ERROR if is_error else self.log_level
        payload: Dict[str, Any] = event.payload if isinstance(event.payload, dict) else {}
        step = payload.get("step") or payload.get("metadata", {}).get("step")
        step_label = payload.get("step_label") or payload.get("metadata", {}).get("step_label") or step or "-"
        tool_name = payload.get("tool") or ""
        method = payload.get("method") or ""
        tool_descriptor = tool_name
        if tool_name and method:
            tool_descriptor = f"{tool_name}.{method}"
        tool_label = payload.get("tool_label") or tool_descriptor or event.scope
        agent_name = payload.get("agent") or payload.get("agent_name")
        agent_label = payload.get("agent_label") or agent_name or event.scope
        parent_label = payload.get("parent_agent_label") or payload.get("parent_agent") or "User"

        if event_name.startswith("step."):
            line = f"{ICON_STEP} {step_label} - ID: {step or '-'} - Agent: {agent_label} - Event: {event_name}"
            if logger.isEnabledFor(level):
                logger.log(level, line)
            if payload.get("instructions") and logger.isEnabledFor(logging.DEBUG):
                logger.debug("%s %s", ICON_STATE, payload.get("instructions"))
            if is_error:
                self._log_error_details(level, payload)
            elif self.debug_payload and logger.isEnabledFor(logging.DEBUG):
                logger.debug("%s %s", ICON_STATE, _stringify_payload(payload))
            return

        if event_name.startswith("agent."):
            line = f"{ICON_AGENT} {agent_label} - Step: {step_label} - Event: {event_name}"
            if tool_label:
                line += f"  - Tool: {tool_label}"
            if logger.isEnabledFor(level):
                logger.log(level, line)
            # argument and result payloads are intentionally omitted from the logs

            if event_name == "agent.before" and logger.isEnabledFor(level):
                logger.log(
                    level,
                    "%s %s - Step: %s - Receive message from %s",
                    ICON_AGENT,
                    agent_label,
                    step_label,
                    parent_label,
                )
            if event_name == "agent.after" and logger.isEnabledFor(level):
                logger.log(
                    level,
                    "%s %s - Step: %s - Send message to %s",
                    ICON_AGENT,
                    agent_label,
                    step_label,
                    parent_label or "User",
                )

            if is_error:
                self._log_error_details(level, payload)
            elif self.debug_payload and logger.isEnabledFor(logging.DEBUG):
                logger.debug("%s %s", ICON_STATE, _stringify_payload(payload))
            return

        if event_name.startswith("tool."):
            display = tool_label or tool_descriptor or event.scope
            line = f"{ICON_TOOL} {display} - Step: {step_label} - Event: {event_name}"
            if agent_label:
                line += f"  - Agent: {agent_label}"
            if parent_label and payload.get("parent_agent"):
                line += f"  - Parent: {parent_label}"
            if logger.isEnabledFor(level):
                logger.log(level, line)
            # argument and result payloads are intentionally omitted from the logs
            if is_error:
                self._log_error_details(level, payload)
            elif self.debug_payload and logger.isEnabledFor(logging.DEBUG):
                logger.debug("%s %s", ICON_STATE, _stringify_payload(payload))
            return

        if event_name.startswith("callback."):
            callback_label = payload.get("callback_label") or payload.get("callback") or event.scope
            line = f"{ICON_CALLBACK} {callback_label} - Event: {event_name}"
            if logger.isEnabledFor(level):
                logger.log(level, line)
            if is_error:
                self._log_error_details(level, payload)
            elif self.debug_payload and logger.isEnabledFor(logging.DEBUG):
                logger.debug("%s %s", ICON_STATE, _stringify_payload(payload))
            return

        if logger.isEnabledFor(level):
            logger.log(level, f"{ICON_EVENT} {event.scope}::{event.name}")
        if is_error:
            self._log_error_details(level, payload)
        elif self.debug_payload and logger.isEnabledFor(logging.DEBUG):
            logger.debug("%s %s", ICON_STATE, _stringify_payload(payload))

    @staticmethod
    def _log_error_details(level: int, payload: Dict[str, Any]) -> None:
        message = payload.get("message") or payload.get("error")
        if message and logger.isEnabledFor(level):
            logger.log(level, "%s %s", ICON_ERROR, message)
        details_payload = payload.get("details")
        if details_payload and logger.isEnabledFor(level):
            logger.log(level, "%s %s", ICON_STATE, _stringify_object(details_payload))
        stacktrace = payload.get("stacktrace")
        if stacktrace and logger.isEnabledFor(level):
            logger.log(level, "%s stacktrace:\n%s", ICON_ERROR, stacktrace)


def build_plugin() -> RuntimeLoggingPlugin:
    return RuntimeLoggingPlugin()


__all__ = ["RuntimeLoggingPlugin", "build_plugin"]
