"""Callback that maintains confirmation state based on user replies."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from agents.diagramador.app.tools.shared.diagram_generator.utilities import (
    confirmation_handler,
)


class Callback:
    """Update confirmation status automatically after every user message."""

    _POSITIVE = {
        "sim",
        "confirmo",
        "correto",
        "ok",
        "está correto",
        "esta correto",
        "pode gerar",
        "gerar",
        "aprovado",
        "aprovada",
        "perfeito",
    }
    _NEGATIVE = {
        "nao",
        "não",
        "corrigir",
        "correcao",
        "ajustar",
        "errado",
        "alterar",
        "mudar",
        "rever",
    }

    def __init__(self, metadata: Optional[Dict[str, Any]] = None):
        self.metadata = metadata or {}

    def handle_event(
        self,
        event: str,
        payload: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if event != "after_user_message":
            return {}

        if state is None:
            state = {}

        message = self._extract_message(payload)
        if not message:
            return {}

        confirmation = state.setdefault("confirmation", {})
        previous_history = confirmation.setdefault("history", [])
        timestamp = datetime.utcnow().isoformat() + "Z"
        previous_history.append({"timestamp": timestamp, "message": message})
        confirmation["last_user_message"] = message
        confirmation.setdefault("diagram_generated", False)

        if confirmation.get("diagram_generated"):
            confirmation.update(
                {
                    "status": "already_generated",
                    "should_generate": False,
                    "message": "Diagrama já gerado para esta sessão.",
                    "updated_at": timestamp,
                }
            )
            return {"confirmation": confirmation}

        normalized = message.lower()
        if self._matches(normalized, self._POSITIVE):
            confirmation.update(
                {
                    "status": "confirmed",
                    "should_generate": True,
                    "message": "Confirmação recebida - iniciar geração do diagrama.",
                    "updated_at": timestamp,
                }
            )
            snapshot = self._extract_analysis_snapshot(state)
            if snapshot:
                confirmation_handler.update_approved_snapshot(snapshot)
            else:
                confirmation_handler.update_approved_snapshot(None)

            approved_snapshot = confirmation_handler.get_approved_snapshot()
            confirmation["approved_analysis"] = approved_snapshot.get("analysis")
            confirmation["approved_elements"] = approved_snapshot.get("elements")
            confirmation["approved_relationships"] = approved_snapshot.get("relationships")
            confirmation["approved_steps"] = approved_snapshot.get("steps")
            confirmation["approved_system_name"] = approved_snapshot.get("system_name")
        elif self._matches(normalized, self._NEGATIVE):
            confirmation.update(
                {
                    "status": "correction_needed",
                    "should_generate": False,
                    "message": "Usuário solicitou ajustes antes da geração.",
                    "updated_at": timestamp,
                }
            )
            confirmation_handler.update_approved_snapshot(None)
        else:
            confirmation.update(
                {
                    "status": "clarification_needed",
                    "should_generate": False,
                    "message": "Aguardando confirmação explícita ou instruções de correção.",
                    "updated_at": timestamp,
                }
            )
            confirmation_handler.update_approved_snapshot(None)

        return {"confirmation": confirmation}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _matches(message: str, keywords: Iterable[str]) -> bool:
        return any(keyword in message for keyword in keywords)

    def _extract_message(self, payload: Dict[str, Any]) -> str:
        value = payload.get("message") or payload.get("content") or payload.get("text")
        if isinstance(value, str):
            return value.strip()

        # Some payloads wrap content in dictionaries or arrays
        if isinstance(value, dict):
            return self._extract_from_dict(value)
        if isinstance(value, list):
            for item in value:
                extracted = self._extract_message({"message": item})
                if extracted:
                    return extracted
        return ""

    def _extract_analysis_snapshot(self, state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(state, dict):
            return {}

        analysis = state.get("analysis") or {}
        if not isinstance(analysis, dict):
            return {}

        candidates = [analysis]

        confirmed = analysis.get("confirmed")
        if isinstance(confirmed, dict):
            candidates.insert(0, confirmed)

        latest = analysis.get("latest")
        if isinstance(latest, dict):
            candidates.insert(0, latest)

        last_presented = analysis.get("last_presented")
        if isinstance(last_presented, dict):
            candidates.append(last_presented)

        for candidate in candidates:
            elements = candidate.get("elements")
            system_name = candidate.get("system_name") or candidate.get("summary", {}).get("system_name")
            relationships = candidate.get("relationships")
            steps = candidate.get("steps")

            if elements:
                snapshot = {
                    "elements": deepcopy(elements),
                    "relationships": deepcopy(relationships) if relationships is not None else None,
                    "steps": deepcopy(steps) if steps is not None else None,
                    "system_name": deepcopy(system_name),
                }
                if not snapshot["system_name"]:
                    system = candidate.get("system") or candidate.get("summary", {}).get("system")
                    snapshot["system_name"] = deepcopy(system)
                return snapshot

        return {}

    def _extract_from_dict(self, value: Dict[str, Any]) -> str:
        if "$input" in value:
            return str(value.get("value", "")).strip()
        for key in ("text", "content", "message", "value"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        return ""
