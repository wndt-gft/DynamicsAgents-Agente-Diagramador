"""Utilities to evaluate the quality of Newman/Postman collections."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def evaluate_newman_quality(
    collection: Dict[str, Any],
    environments: Dict[str, Any],
    auth_flows: Dict[str, Any],
    monitoring: Optional[Dict[str, Any]],
    ci_cd: Dict[str, Any],
    validation_summary: Dict[str, Any],
    data_driven: Optional[Dict[str, Any]] = None,
    security_tests: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calculate a quality score inspired by Cypress validation heuristics."""

    score = 100
    penalties: List[Dict[str, Any]] = []
    bonuses: List[Dict[str, Any]] = []

    coverage_metrics = validation_summary.get("coverage", {}).get("metrics", {})
    schema_valid = validation_summary.get("schema", {}).get("valid", True)
    duplicate_entries = validation_summary.get("duplicates", {}).get("duplicates", [])

    request_count = coverage_metrics.get("requests_count", 0)
    tests_total = coverage_metrics.get("tests_total", 0)
    assertions_total = coverage_metrics.get("assertions_total", 0)
    positive_flows = coverage_metrics.get("positive_flows", 0)
    negative_flows = coverage_metrics.get("negative_flows", 0)
    requests_with_tests = coverage_metrics.get("requests_with_tests", 0)

    if not collection or not collection.get("item"):
        penalties.append({
            "reason": "collection_missing_items",
            "impact": 45,
            "message": "A coleção não possui itens ou não foi gerada corretamente.",
        })
        score -= 45

    if request_count == 0:
        penalties.append({
            "reason": "no_requests",
            "impact": 30,
            "message": "Nenhuma requisição foi encontrada na coleção.",
        })
        score -= 30

    if tests_total == 0:
        penalties.append({
            "reason": "missing_tests",
            "impact": 35,
            "message": "Nenhum teste Newman foi identificado (pm.test).",
        })
        score -= 35

    if assertions_total == 0:
        penalties.append({
            "reason": "missing_assertions",
            "impact": 20,
            "message": "Nenhuma asserção foi identificada (pm.expect ou status).",
        })
        score -= 20

    if not schema_valid:
        penalties.append({
            "reason": "schema_invalid",
            "impact": 25,
            "message": "A coleção não atende ao esquema mínimo esperado.",
        })
        score -= 25

    if duplicate_entries:
        penalties.append({
            "reason": "duplicates_detected",
            "impact": 10,
            "message": "Foram encontradas requisições duplicadas.",
            "details": duplicate_entries,
        })
        score -= 10

    if positive_flows == 0:
        penalties.append({
            "reason": "missing_positive_flows",
            "impact": 15,
            "message": "Nenhum fluxo positivo foi identificado nas assertions.",
        })
        score -= 15

    if negative_flows == 0:
        penalties.append({
            "reason": "missing_negative_flows",
            "impact": 10,
            "message": "Nenhum fluxo negativo foi identificado nas assertions.",
        })
        score -= 10

    if requests_with_tests < request_count:
        penalties.append({
            "reason": "requests_without_tests",
            "impact": 15,
            "message": "Existem requisições sem testes Newman associados.",
        })
        score -= 15

    if not environments:
        penalties.append({
            "reason": "missing_environments",
            "impact": 10,
            "message": "Nenhuma configuração de ambiente foi gerada.",
        })
        score -= 10
    else:
        bonuses.append({
            "reason": "environments_present",
            "impact": 5,
            "message": "Configurações de ambiente disponíveis.",
        })
        score += 5

    if not auth_flows:
        penalties.append({
            "reason": "missing_auth_flows",
            "impact": 15,
            "message": "Fluxos de autenticação não foram gerados.",
        })
        score -= 15
    else:
        bonuses.append({
            "reason": "auth_flows_present",
            "impact": 5,
            "message": "Fluxos de autenticação abrangentes detectados.",
        })
        score += 5

    if monitoring:
        bonuses.append({
            "reason": "monitoring_present",
            "impact": 3,
            "message": "Configurações de monitoramento incluídas.",
        })
        score += 3
    else:
        penalties.append({
            "reason": "missing_monitoring",
            "impact": 3,
            "message": "Monitoramento não foi configurado.",
        })
        score -= 3

    if ci_cd:
        bonuses.append({
            "reason": "ci_cd_present",
            "impact": 3,
            "message": "Pipelines de CI/CD disponíveis.",
        })
        score += 3
    else:
        penalties.append({
            "reason": "missing_ci_cd",
            "impact": 3,
            "message": "Integrações de CI/CD não foram geradas.",
        })
        score -= 3

    if data_driven:
        bonuses.append({
            "reason": "data_driven_present",
            "impact": 4,
            "message": "Testes orientados a dados foram preparados.",
        })
        score += 4

    if security_tests:
        bonuses.append({
            "reason": "security_tests_present",
            "impact": 4,
            "message": "Testes de segurança adicionais estão disponíveis.",
        })
        score += 4

    metrics = {
        "request_count": request_count,
        "tests_total": tests_total,
        "assertions_total": assertions_total,
        "positive_flows": positive_flows,
        "negative_flows": negative_flows,
        "requests_with_tests": requests_with_tests,
        "environment_count": len(environments or {}),
        "auth_flow_count": len(auth_flows or {}),
        "has_monitoring": bool(monitoring),
        "has_ci_cd": bool(ci_cd),
        "has_data_driven": bool(data_driven),
        "has_security": bool(security_tests),
    }

    score = max(0, min(100, score))

    return {
        "score": score,
        "penalties": penalties,
        "bonuses": bonuses,
        "metrics": metrics,
    }


__all__ = ["evaluate_newman_quality"]
