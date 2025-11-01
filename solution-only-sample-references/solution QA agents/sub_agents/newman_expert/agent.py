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

"""Newman API Expert Agent - Generic modular structure for any domain."""

import json
import os
from typing import Any, Dict, List, Optional, Union, Callable

from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool

from . import prompt
from .tools import generate_expert_newman_collections as _generate_expert_newman_collections
from ...utils.callbacks import (
    newman_structured_response_callback,
    validate_code_quality_callback,
)
from ...utils.exceptions import InvalidModelError, NewmanError
from ...utils.logging_config import create_contextual_logger

# Initialize structured logger
logger = create_contextual_logger(
    "newman_expert",
    framework="newman",
    agent_type="sub_agent",
)


def _parse_newman_output(raw_output: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Parse the Newman tool output into a structured dictionary."""
    if isinstance(raw_output, dict):
        return raw_output

    if not raw_output:
        raise ValueError("Empty response returned by Newman collection generator")

    # Strip Markdown fences when present
    cleaned_output = raw_output.strip()
    if cleaned_output.startswith("```"):
        cleaned_output = cleaned_output.strip("`").strip()
        if cleaned_output.lower().startswith("json"):
            cleaned_output = cleaned_output[4:].strip()

    try:
        return json.loads(cleaned_output)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Não foi possível interpretar a resposta JSON produzida pelo agente Newman"
        ) from exc


def generate_newman_collections_wrapper(
    api_specification: str,
    test_scenarios: Optional[List[str]] = None,
    business_domain: str = "general",
    collection_complexity: str = "medium",
    authentication_types: Optional[List[str]] = None,
    environment_stages: Optional[List[str]] = None,
    include_monitoring: bool = True,
    include_collaboration_features: bool = True,
    include_data_driven_tests: bool = True,
    include_security_tests: bool = True,
    custom_config: Optional[Dict[str, Any]] = None,
    endpoints: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Wrapper para gerar coleções Newman com validações e telemetria."""

    logger.info(
        "Solicitação de geração de coleção Newman recebida",
        extra_fields={
            "domain": business_domain,
            "complexity": collection_complexity,
            "monitoring": include_monitoring,
            "collaboration": include_collaboration_features,
            "data_driven": include_data_driven_tests,
            "security": include_security_tests,
            "environments": environment_stages or [],
        },
    )

    try:
        if not api_specification or not api_specification.strip():
            logger.warning("api_specification ausente ou vazio")
            raise ValueError("api_specification is required and cannot be empty")

        raw_response = _generate_expert_newman_collections(
            api_specification=api_specification,
            test_scenarios=test_scenarios,
            business_domain=business_domain,
            collection_complexity=collection_complexity,
            authentication_types=authentication_types,
            environment_stages=environment_stages,
            include_monitoring=include_monitoring,
            include_collaboration_features=include_collaboration_features,
            custom_config=custom_config,
            endpoints=endpoints,
            include_data_driven_tests=include_data_driven_tests,
            include_security_tests=include_security_tests,
        )

        parsed_response = _parse_newman_output(raw_response)

        missing_fields = [
            field
            for field in (
                "collections",
                "environments",
                "scripts",
                "newman_plan",
                "ci_cd",
                "readme",
            )
            if field not in parsed_response
        ]
        if missing_fields:
            raise KeyError(
                f"Response missing required fields: {', '.join(missing_fields)}"
            )

        logger.info(
            "Coleção Newman gerada com sucesso",
            extra_fields={
                "quality_score": parsed_response.get("quality_score", 0),
                "collections": len(parsed_response.get("collections", []) or []),
                "environments": len(parsed_response.get("environments", []) or []),
            },
        )

        return parsed_response

    except ValueError as exc:
        logger.error(
            "Erro de validação ao gerar coleção Newman",
            extra_fields={"error": str(exc)},
        )
        raise NewmanError(
            "Parâmetros inválidos para gerar coleções Newman",
            details={"message": str(exc)},
        ) from exc
    except KeyError as exc:
        logger.error(
            "Resposta do agente Newman incompleta",
            extra_fields={"missing_field": str(exc)},
        )
        raise NewmanError(
            "A resposta do especialista Newman não contém todos os dados esperados",
            details={"missing_field": str(exc)},
        ) from exc
    except Exception as exc:  # pragma: no cover - log unexpected errors
        logger.error(
            "Falha inesperada na geração de coleções Newman",
            extra_fields={"error_type": type(exc).__name__},
            exc_info=True,
        )
        raise NewmanError(
            "Newman Expert Agent encontrou um erro inesperado",
            details={"message": str(exc)},
        ) from exc


def _create_function_tool(func: Callable[..., Any], name: str) -> FunctionTool:
    """Instantiate a FunctionTool ensuring the declared name is stable."""

    try:
        return FunctionTool(func, name=name)
    except TypeError:
        try:
            tool = FunctionTool(func)
        except TypeError:
            tool = FunctionTool()
        if hasattr(tool, "name"):
            try:
                setattr(tool, "name", name)
            except Exception:  # pragma: no cover - best-effort fallback
                pass
        return tool


def newman_after_agent_callback(callback_context: Any) -> None:
    """Executa callbacks especializados para o agente Newman."""

    try:
        newman_structured_response_callback(callback_context)
    finally:
        # Sempre executar a validação de qualidade para registrar métricas
        validate_code_quality_callback(callback_context)


# Load model from environment variable, default to gemini-2.5-pro
MODEL = os.getenv("QA_MODEL", "gemini-2.5-pro")

try:
    logger.info(
        "Inicializando Newman Expert Agent",
        extra_fields={"model": MODEL, "tools_count": 1},
    )

    if not MODEL:
        raise InvalidModelError(
            "QA_MODEL environment variable is not set",
            details={"default": "gemini-2.5-pro"},
        )

    # Newman Expert Agent instance with universal tools
    newman_expert_agent = Agent(
        model=MODEL,
        name="newman_api_expert",
        instruction=prompt.NEWMAN_EXPERT_PROMPT,
        tools=[
            _create_function_tool(
                generate_newman_collections_wrapper,
                "generate_newman_collections_wrapper",
            )
        ],
        output_key="newman_expert_output",
        after_agent_callback=newman_after_agent_callback,
    )

    logger.info(
        "Newman Expert Agent inicializado com sucesso",
        extra_fields={"agent_name": "newman_api_expert", "status": "ready"},
    )

except InvalidModelError:
    raise
except Exception as exc:
    logger.error(
        "Falha ao inicializar o Newman Expert Agent",
        extra_fields={"error_type": type(exc).__name__, "error": str(exc)},
        exc_info=True,
    )
    raise NewmanError(
        "Newman Expert Agent initialization failed",
        details={"original_error": str(exc)},
    ) from exc

# Backwards compatibility - expose parsed generator as original name
generate_expert_newman_collections = generate_newman_collections_wrapper
