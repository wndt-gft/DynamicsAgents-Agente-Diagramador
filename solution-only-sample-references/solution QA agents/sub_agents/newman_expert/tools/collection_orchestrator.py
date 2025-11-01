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
Collection Orchestrator for Newman Expert.

This module is responsible for orchestrating the generation of complete Newman/Postman collections.
It coordinates multiple specialized generators to produce comprehensive collection artifacts.

Single Responsibility: Orchestrate the composition of Newman collection components into a complete suite.
"""

from typing import Dict, Any, List, Optional, Iterable, Union

from jsonschema import Draft7Validator

from .quality_validator import evaluate_newman_quality


POSTMAN_MINIMAL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["info", "item"],
    "properties": {
        "info": {
            "type": "object",
            "required": ["name", "schema"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "schema": {"type": "string"},
            },
        },
        "item": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "item": {"type": "array"},
                    "request": {"type": "object"},
                },
            },
        },
        "variable": {"type": "array"},
        "event": {"type": "array"},
    },
}

ERROR_HINT = "Verifique o formato do OpenAPI, cenários de teste e configurações auxiliares."

ERROR_MESSAGES = {
    "collection_generation_failed": "Não foi possível gerar a coleção principal do Newman.",
    "invalid_input": "Entrada inválida fornecida para geração da coleção do Newman.",
}


def generate_expert_newman_collections(
    api_specification: str,
    test_scenarios: Optional[List[str]] = None,
    business_domain: str = "general",
    collection_complexity: str = "medium",
    authentication_types: Optional[List[str]] = None,
    environment_stages: Optional[List[str]] = None,
    include_monitoring: bool = True,
    include_collaboration_features: bool = True,
    custom_config: Optional[Dict[str, Any]] = None,
    endpoints: Optional[List[Dict[str, Any]]] = None,
    include_data_driven_tests: bool = True,
    include_security_tests: bool = True,
) -> Dict[str, Any]:
    """
    Generate expert-level Newman/Postman collections from OpenAPI specification and Zephyr test scenarios.

    This function orchestrates the creation of production-ready Postman collections for Newman automation,
    including environment configurations, authentication, monitoring, and CI/CD integration.

    Args:
        api_specification: OpenAPI/Swagger specification in YAML or JSON format, or API documentation text
        test_scenarios: List of test scenarios from Zephyr/TestRail or plain text descriptions
        business_domain: Domain context (e.g., 'banking', 'ecommerce', 'healthcare')
        collection_complexity: Complexity level ('simple', 'medium', 'complex')
        authentication_types: List of auth types to support (e.g., ['bearer', 'basic', 'oauth2'])
        environment_stages: List of environment names (e.g., ['dev', 'staging', 'prod'])
        include_monitoring: Whether to include monitoring configuration
        include_collaboration_features: Whether to include team collaboration features
        custom_config: Additional custom configuration options
        endpoints: Optional list of endpoint definitions
        include_data_driven_tests: Whether to include data-driven test examples
        include_security_tests: Whether to include security testing scenarios

    Returns:
        Dicionário estruturado com coleção, ambientes, fluxos de autenticação,
        configurações de monitoramento e CI/CD, metadados e pontuação de qualidade.
    """

    # Import generator functions
    from .smart_collection_builder import build_smart_newman_collection
    from .environment_generator import generate_multi_environment_configs
    from .auth_generator import generate_authentication_collections
    from .monitoring_generator import generate_monitoring_config
    from .collaboration_generator import generate_collaboration_features
    from .execution_generator import generate_execution_strategies
    from .ci_cd_generator import generate_ci_cd_integration
    from .data_driven_generator import generate_data_driven_tests
    from .security_generator import generate_security_tests
    import json

    # ✅ CRITICAL FIX: Handle malformed or oversized inputs gracefully
    # Ensure safe defaults
    test_scenarios = test_scenarios or []
    authentication_types = authentication_types or ["bearer", "basic"]
    environment_stages = environment_stages or ["dev", "staging", "production"]
    custom_config = custom_config or {}
    endpoints = endpoints or []

    # ✅ Sanitize test_scenarios if it's malformed
    # Sometimes the LLM passes a list with a single very large string
    if test_scenarios and len(test_scenarios) == 1 and len(test_scenarios[0]) > 10000:
        # Try to parse it as JSON to validate
        try:
            json.loads(test_scenarios[0])
        except json.JSONDecodeError:
            # If it fails, try to clean it up
            test_scenarios = [test_scenarios[0].replace('\n', ' ').strip()]

    # Try to detect if api_specification contains OpenAPI and test_scenarios contains Zephyr JSON
    openapi_spec = None
    zephyr_scenarios = None

    # Check if api_specification looks like OpenAPI YAML/JSON
    if api_specification and ("openapi:" in api_specification or "swagger:" in api_specification or '"openapi"' in api_specification):
        openapi_spec = api_specification

    # ✅ Improved test_scenarios processing
    if test_scenarios and len(test_scenarios) > 0:
        # Join all test scenario strings if it's a list
        if isinstance(test_scenarios, list):
            combined_scenarios = '\n'.join(str(s) for s in test_scenarios)
        else:
            combined_scenarios = str(test_scenarios)

        # Check if it looks like JSON (Zephyr format)
        if combined_scenarios.strip().startswith('{') or combined_scenarios.strip().startswith('['):
            # Try to parse as JSON to validate
            try:
                json.loads(combined_scenarios)
                zephyr_scenarios = combined_scenarios
            except json.JSONDecodeError:
                # If parsing fails, still use it but log a warning
                zephyr_scenarios = combined_scenarios
                print(f"Warning: test_scenarios appears to be JSON but failed to parse. Using as-is.")

    # Generate main Postman collection using smart builder
    try:
        main_collection = build_smart_newman_collection(
            openapi_spec=openapi_spec,
            zephyr_scenarios=zephyr_scenarios,
            api_specification=api_specification if not openapi_spec else None,
            test_scenarios=test_scenarios if not zephyr_scenarios else None,
            domain=business_domain,
            config=custom_config,
        )
    except Exception as exc:  # pragma: no cover - defensive path
        return _build_error_result(
            code="collection_generation_failed",
            message=str(exc),
            extra={"exception": type(exc).__name__},
        )

    # Generate environment configurations for multiple stages
    environment_configs = generate_multi_environment_configs(
        environment_stages=environment_stages,
        domain=business_domain,
        config=custom_config,
    )

    # Generate authentication collections if needed
    auth_collections: Dict[str, Any] = {}
    if openapi_spec:
        auth_collections = generate_authentication_collections(
            auth_types=authentication_types,
            domain=business_domain,
            config=custom_config,
        )

    # Generate monitoring configuration if requested
    monitoring_config: Optional[Dict[str, Any]] = None
    if include_monitoring:
        monitoring_config = generate_monitoring_config(
            domain=business_domain,
            config=custom_config,
        )

    # Generate collaboration features if requested
    collaboration_features: Optional[Dict[str, Any]] = None
    if include_collaboration_features:
        collaboration_features = generate_collaboration_features(
            domain=business_domain,
            config=custom_config,
        )

    # Generate execution strategies
    execution_strategies = generate_execution_strategies(
        domain=business_domain,
        complexity=collection_complexity,
        config=custom_config,
    )

    # Generate CI/CD integration
    ci_cd_integration = generate_ci_cd_integration(
        domain=business_domain,
        config=custom_config,
    )

    data_driven_assets: Optional[Dict[str, Any]] = None
    if include_data_driven_tests:
        data_driven_assets = generate_data_driven_tests(
            domain=business_domain,
            endpoints=endpoints,
            config=custom_config,
        )

    security_assets: Optional[Dict[str, Any]] = None
    if include_security_tests:
        security_assets = generate_security_tests(
            domain=business_domain,
            endpoints=endpoints,
            config=custom_config,
        )

    validation_summary = _run_validations(main_collection)

    quality = evaluate_newman_quality(
        collection=main_collection,
        environments=environment_configs,
        auth_flows=auth_collections,
        monitoring=monitoring_config,
        ci_cd=ci_cd_integration,
        validation_summary=validation_summary,
        data_driven=data_driven_assets,
        security_tests=security_assets,
    )

    scripts_registry = _extract_script_registry(main_collection)

    environment_payload = [
        {
            "stage": stage,
            "name": details.get("name", f"{business_domain.title()} - {stage.upper()}"),
            "values": details.get("values", []),
            "file": f"environments/{business_domain}-{stage}.json",
        }
        for stage, details in (environment_configs or {}).items()
    ]

    collections_payload = [
        {
            "name": main_collection.get("info", {}).get(
                "name", f"{business_domain.title()} API Collection"
            ),
            "description": main_collection.get("info", {}).get("description", ""),
            "filename": f"collections/{business_domain}-api-collection.json",
            "collection": main_collection,
        }
    ]

    newman_options = execution_strategies.get("newman_options", {})
    cli_command = "newman run {collection} --environment {environment}".format(
        collection=newman_options.get(
            "collection", f"collections/{business_domain}-api-collection.json"
        ),
        environment=newman_options.get(
            "environment", f"environments/{business_domain}-{{env}}.json"
        ),
    )
    if reporters := newman_options.get("reporters"):
        cli_command += f" --reporters {','.join(reporters)}"
    if iteration := newman_options.get("iterationCount"):
        cli_command += f" --iteration-count {iteration}"
    if delay := newman_options.get("delayRequest"):
        cli_command += f" --delay-request {delay}"

    newman_plan = {
        "cli_command": cli_command,
        "options": newman_options,
        "parallel_execution": execution_strategies.get("parallel_execution", {}),
        "reporting": newman_options.get("reporter", {}),
        "recommended_workflow": [
            "Instalar dependências (Node.js 18+, newman, newman-reporter-htmlextra)",
            "Selecionar o ambiente apropriado via variável de pipeline",
            "Executar o comando Newman acima monitorando códigos de saída",
            "Publicar relatórios HTML/JSON em artefatos do pipeline",
        ],
    }

    metadata: Dict[str, Any] = {
        "status": "success",
        "business_domain": business_domain,
        "complexity": collection_complexity,
        "environment_stages": environment_stages,
        "authentication_types": authentication_types,
        "features_enabled": {
            "monitoring": include_monitoring,
            "collaboration": include_collaboration_features,
            "data_driven": include_data_driven_tests,
            "security": include_security_tests,
        },
        "validation": validation_summary,
        "quality": quality,
        "collaboration": collaboration_features,
        "execution": execution_strategies,
        "supplemental_assets": {
            "data_driven": _summarize_asset(data_driven_assets),
            "security": _summarize_asset(security_assets),
        },
    }

    readme = _build_readme(
        business_domain=business_domain,
        collections_payload=collections_payload,
        environment_payload=environment_payload,
        newman_plan=newman_plan,
        quality=quality,
    )

    return {
        "collections": collections_payload,
        "environments": environment_payload,
        "scripts": scripts_registry,
        "newman_plan": newman_plan,
        "ci_cd": ci_cd_integration,
        "readme": readme,
        "metadata": metadata,
        "auth_flows": auth_collections,
        "monitoring": monitoring_config,
        "data_driven_assets": data_driven_assets,
        "security_assets": security_assets,
        "quality_score": quality.get("score", 0),
    }


def _build_error_result(code: str, message: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    error_message = ERROR_MESSAGES.get(code, ERROR_MESSAGES["invalid_input"])
    payload: Dict[str, Any] = {
        "collections": [],
        "environments": [],
        "scripts": {},
        "newman_plan": {},
        "ci_cd": {},
        "readme": "",
        "auth_flows": {},
        "monitoring": None,
        "metadata": {
            "status": "error",
            "error": {
                "code": code,
                "message": error_message,
                "details": message,
                "hint": ERROR_HINT,
                **(extra or {}),
            },
        },
        "data_driven_assets": None,
        "security_assets": None,
        "quality_score": 0,
    }
    return payload


def _run_validations(collection: Dict[str, Any]) -> Dict[str, Any]:
    schema_result = _validate_collection_schema(collection)
    duplicates_result = _check_duplicate_requests(collection)
    coverage_result = _evaluate_scenario_coverage(collection)
    return {
        "schema": schema_result,
        "duplicates": duplicates_result,
        "coverage": coverage_result,
    }


def _validate_collection_schema(collection: Dict[str, Any]) -> Dict[str, Any]:
    validator = Draft7Validator(POSTMAN_MINIMAL_SCHEMA)
    errors = [
        f"{'.'.join(str(part) for part in error.absolute_path)}: {error.message}"
        for error in validator.iter_errors(collection)
    ]
    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def _check_duplicate_requests(collection: Dict[str, Any]) -> Dict[str, Any]:
    duplicates: List[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}

    for request in _iter_collection_requests(collection):
        name = (request.get("name") or "").strip().lower()
        url = _extract_request_url(request)
        key = f"{name}|{url}"
        if key in seen:
            duplicates.append({
                "request": request.get("name"),
                "url": url,
            })
        else:
            seen[key] = {"name": name, "url": url}

    return {
        "valid": len(duplicates) == 0,
        "duplicates": duplicates,
    }


def _evaluate_scenario_coverage(collection: Dict[str, Any]) -> Dict[str, Any]:
    requests = list(_iter_collection_requests(collection))
    positive_total = 0
    negative_total = 0
    requests_with_tests = 0
    assertions_total = 0
    test_total = 0
    warnings: List[str] = []

    for request in requests:
        analysis = _analyze_request_tests(request)
        if analysis["has_tests"]:
            requests_with_tests += 1
        else:
            warnings.append(f"Sem testes definidos para '{request.get('name', 'request')}'")

        positive_total += analysis["positive_hits"]
        negative_total += analysis["negative_hits"]
        assertions_total += analysis["assertions"]
        test_total += analysis["tests"]

    metrics = {
        "requests_count": len(requests),
        "requests_with_tests": requests_with_tests,
        "positive_flows": positive_total,
        "negative_flows": negative_total,
        "assertions_total": assertions_total,
        "tests_total": test_total,
    }

    valid = (
        metrics["requests_count"] > 0
        and metrics["positive_flows"] > 0
        and metrics["negative_flows"] > 0
        and metrics["requests_with_tests"] == metrics["requests_count"]
    )

    if metrics["positive_flows"] == 0:
        warnings.append("Nenhum fluxo positivo identificado nas assertions.")
    if metrics["negative_flows"] == 0:
        warnings.append("Nenhum fluxo negativo identificado nas assertions.")
    if metrics["requests_with_tests"] < metrics["requests_count"]:
        warnings.append("Existem requisições sem testes associados.")

    return {
        "valid": valid,
        "warnings": warnings,
        "metrics": metrics,
    }


def _analyze_request_tests(request: Dict[str, Any]) -> Dict[str, Any]:
    script_text = _extract_test_script(request)
    normalized = script_text.lower()

    tests = normalized.count("pm.test")
    assertions = normalized.count("pm.expect") + normalized.count(".to.have.status")

    positive_hits = sum(
        normalized.count(f"status({code}")
        for code in ["200", "201", "202", "204"]
    )
    negative_hits = sum(
        normalized.count(f"status({code}")
        for code in ["400", "401", "403", "404", "409", "422", "500", "503"]
    )

    return {
        "has_tests": tests > 0,
        "tests": tests,
        "assertions": assertions,
        "positive_hits": positive_hits,
        "negative_hits": negative_hits,
    }


def _iter_collection_requests(collection: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for item in collection.get("item", []) or []:
        yield from _walk_item(item)


def _walk_item(item: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    if "request" in item:
        yield item
    if "item" in item and isinstance(item["item"], list):
        for child in item["item"]:
            yield from _walk_item(child)


def _extract_test_script(request: Dict[str, Any]) -> str:
    snippets: List[str] = []
    for event in request.get("event", []) or []:
        if event.get("listen") != "test":
            continue
        script = event.get("script", {})
        exec_block = script.get("exec")
        if isinstance(exec_block, list):
            snippets.extend(str(line) for line in exec_block)
        elif isinstance(exec_block, str):
            snippets.append(exec_block)
    return "\n".join(snippets)


def _extract_request_url(request: Dict[str, Any]) -> str:
    url = request.get("request", {}).get("url")
    if isinstance(url, str):
        return url
    if isinstance(url, dict):
        raw = url.get("raw")
        if raw:
            return raw
        host = url.get("host", [])
        path = url.get("path", [])
        if isinstance(host, list):
            host = "/".join(str(part) for part in host)
        if isinstance(path, list):
            path = "/".join(str(part) for part in path)
        return f"{host}/{path}".strip("/")
    return ""


def _summarize_asset(asset: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not asset:
        return None
    summary = {
        "keys": sorted(asset.keys()),
    }
    if "info" in asset and isinstance(asset["info"], dict):
        summary["info"] = {
            key: asset["info"].get(key)
            for key in ("name", "description")
            if key in asset["info"]
        }
    if "data_file" in asset:
        summary["data_file"] = asset.get("data_file")
    return summary


def _extract_script_registry(collection: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize collection, folder and request scripts for downstream consumers."""

    def _normalize_exec(exec_block: Union[List[str], str, None]) -> str:
        if isinstance(exec_block, list):
            return "\n".join(str(line) for line in exec_block)
        if isinstance(exec_block, str):
            return exec_block
        return ""

    registry: Dict[str, Any] = {
        "collection": {"prerequest": [], "test": []},
        "folders": {},
        "requests": {},
    }

    for event in collection.get("event", []) or []:
        listen = event.get("listen")
        if listen not in ("prerequest", "test"):
            continue
        registry["collection"].setdefault(listen, []).append(
            _normalize_exec(event.get("script", {}).get("exec"))
        )

    for folder in collection.get("item", []) or []:
        folder_name = folder.get("name", "Folder")
        folder_entry = registry["folders"].setdefault(
            folder_name, {"prerequest": [], "test": []}
        )

        for event in folder.get("event", []) or []:
            listen = event.get("listen")
            if listen not in ("prerequest", "test"):
                continue
            folder_entry.setdefault(listen, []).append(
                _normalize_exec(event.get("script", {}).get("exec"))
            )

        for request in folder.get("item", []) or []:
            request_name = request.get("name", "Request")
            request_entry = registry["requests"].setdefault(
                request_name, {"prerequest": [], "test": []}
            )
            for event in request.get("event", []) or []:
                listen = event.get("listen")
                if listen not in ("prerequest", "test"):
                    continue
                request_entry.setdefault(listen, []).append(
                    _normalize_exec(event.get("script", {}).get("exec"))
                )

    return registry


def _build_readme(
    *,
    business_domain: str,
    collections_payload: List[Dict[str, Any]],
    environment_payload: List[Dict[str, Any]],
    newman_plan: Dict[str, Any],
    quality: Dict[str, Any],
) -> str:
    """Generate markdown README content summarizing Newman assets."""

    collection_info_lines = [
        f"- **{item['name']}** → `{item['filename']}`" for item in collections_payload
    ]
    environment_lines = [
        f"- `{env['file']}` (stage: {env['stage']})" for env in environment_payload
    ] or ["- Nenhum ambiente adicional gerado"]

    quality_summary = quality.get("score")
    quality_line = (
        f"Pontuação de qualidade avaliada automaticamente: **{quality_summary}**."
        if quality_summary is not None
        else "Pontuação de qualidade não calculada."
    )

    cli_command = newman_plan.get("cli_command", "newman run <collection>")

    workflow_lines = [f"- {step}" for step in newman_plan.get("recommended_workflow", [])]

    readme_sections = [
        f"# Pacote Newman – {business_domain.title()}\n",
        "## Artefatos Gerados",
        "Coleções disponíveis:",
        *collection_info_lines,
        "\nAmbientes disponíveis:",
        *environment_lines,
        "\n## Execução via Newman",
        "Execute o comando abaixo substituindo a variável de ambiente desejada:",
        f"```bash\n{cli_command}\n```",
        "Etapas recomendadas:",
        *workflow_lines,
        "\n## Qualidade",
        quality_line,
    ]

    return "\n".join(readme_sections)
