"""Deterministic test runner used by the self-test lab workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from dynamic_agents import RuntimeToolError


@dataclass
class AssertionInput:
    """Declarative representation of a single assertion."""

    name: str
    comparator: str = "equals"
    expected: Any = None
    actual: Any = None
    notes: Optional[str] = None


class Tool:
    """Executes simple deterministic assertions and records results in the state."""

    def __init__(self, metadata: Optional[Dict[str, Any]] = None):
        self.metadata = metadata or {}

    def run_suite(
        self,
        suite_name: str,
        assertions: Iterable[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a declarative suite of assertions.

        Args:
            suite_name: Identifier of the suite being executed.
            assertions: Collection of assertion payloads containing at least a name,
                comparator, expected and actual values.
            context: Optional metadata describing how the suite was generated.
            state: Shared conversation state that will be augmented with results.

        Returns:
            Dict with totals, pass/fail ratio and per-assertion diagnostics.
        """

        if not suite_name:
            raise RuntimeToolError("O campo 'suite_name' é obrigatório.")

        assertion_payloads = list(assertions or [])
        if not assertion_payloads:
            raise RuntimeToolError("A suíte precisa conter pelo menos uma asserção.")

        state = state or {}
        context = context or {}

        results: List[Dict[str, Any]] = []
        passed = 0
        failed = 0
        skipped = 0

        for index, payload in enumerate(assertion_payloads, start=1):
            prepared = self._prepare_assertion(payload, index)
            comparison_result = self._evaluate_assertion(prepared)
            if comparison_result["status"] == "passed":
                passed += 1
            elif comparison_result["status"] == "failed":
                failed += 1
            else:
                skipped += 1
            results.append(comparison_result)

        summary = {
            "suite_name": suite_name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "totals": {
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "total": len(results),
            },
            "passed": failed == 0,
            "context": context,
            "results": results,
        }

        testing_state = state.setdefault("testing", {})
        suites = testing_state.setdefault("suites", {})
        suites[suite_name] = summary
        history = testing_state.setdefault("history", [])
        history.append(
            {
                "suite": suite_name,
                "timestamp": summary["timestamp"],
                "passed": summary["passed"],
                "totals": summary["totals"],
            }
        )
        testing_state["last_result"] = summary

        return summary

    # ------------------------------------------------------------------ #

    def _prepare_assertion(self, payload: Dict[str, Any], index: int) -> AssertionInput:
        if not isinstance(payload, dict):
            raise RuntimeToolError(
                "Cada asserção deve ser um objeto com os campos esperados."
            )
        name = str(payload.get("name") or f"assertion_{index}")
        comparator = str(payload.get("comparator") or "equals").lower()
        expected = payload.get("expected")
        actual = payload.get("actual")
        notes = payload.get("notes")
        if comparator not in {"equals", "contains", "gte", "lte"}:
            raise RuntimeToolError(
                f"Comparador desconhecido '{comparator}'. Utilize equals, contains, gte ou lte."
            )
        return AssertionInput(
            name=name,
            comparator=comparator,
            expected=expected,
            actual=actual,
            notes=notes,
        )

    def _evaluate_assertion(self, assertion: AssertionInput) -> Dict[str, Any]:
        comparator = assertion.comparator
        expected = assertion.expected
        actual = assertion.actual

        status = "failed"
        detail = ""

        if actual is None and comparator != "contains":
            status = "skipped"
            detail = "Valor 'actual' ausente; assertion marcada como ignorada."
        elif comparator == "equals":
            if actual == expected:
                status = "passed"
                detail = "Valores coincidem."
            else:
                detail = f"Esperado {expected!r}, obtido {actual!r}."
        elif comparator == "contains":
            status, detail = self._check_contains(expected, actual)
        elif comparator == "gte":
            status, detail = self._check_numeric(expected, actual, greater_than=True)
        elif comparator == "lte":
            status, detail = self._check_numeric(expected, actual, greater_than=False)

        return {
            "name": assertion.name,
            "comparator": comparator,
            "expected": expected,
            "actual": actual,
            "status": status,
            "detail": detail,
            "notes": assertion.notes,
        }

    def _check_contains(self, expected: Any, actual: Any) -> tuple[str, str]:
        if isinstance(actual, str) and isinstance(expected, str):
            if expected.lower() in actual.lower():
                return "passed", "Trecho encontrado no texto analisado."
            return "failed", f"Trecho '{expected}' não encontrado."
        if isinstance(actual, (list, tuple, set)):
            if expected in actual:
                return "passed", "Elemento presente na coleção."
            return "failed", f"Elemento {expected!r} ausente da coleção."
        return (
            "failed",
            "Comparador 'contains' requer texto ou coleção nos campos expected/actual.",
        )

    def _check_numeric(self, expected: Any, actual: Any, *, greater_than: bool) -> tuple[str, str]:
        comparator_label = "gte" if greater_than else "lte"
        try:
            expected_value = float(expected)
            actual_value = float(actual)
        except (TypeError, ValueError):
            return (
                "failed",
                f"Valores não numéricos para comparador '{comparator_label}'.",
            )
        if greater_than:
            if actual_value >= expected_value:
                return "passed", "Valor atual maior ou igual ao esperado."
            return "failed", f"{actual_value} é menor que {expected_value}."
        if actual_value <= expected_value:
            return "passed", "Valor atual menor ou igual ao esperado."
        return "failed", f"{actual_value} é maior que {expected_value}."
