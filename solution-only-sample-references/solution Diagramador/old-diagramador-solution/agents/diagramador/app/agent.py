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
Agente Arquiteto ADK v5.1 com PyArchiMate
Geração de diagramas C4 ArchiMate a partir de user stories.
"""

__version__ = "5.1.0"

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Google ADK imports

from google.adk.agents import LlmAgent, Agent
from google.adk.tools import agent_tool

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from model_register import configure_model
from tools.diagram_service import DiagramService
from utils.local_download import ensure_download_availability
# Import logging toggle and quality validator helper for tests and fallback
from utils.logging_toggle import is_logging_enabled
from tools import validate_diagram_quality
# Local imports
from .callback import sanitize_model_response_callback as _sanitize_model_response

from .prompt import ARCHITECT_AGENT_PROMPT
# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "gft-bu-gcp")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-east5")

AGENT_BASE_MODEL = configure_model(
    env_var_name="MODEL_AGENT_ARCHITECT",
    env_registry_var_name="MODEL_AGENT_ARCHITECT_LIB",
    default_model="gemini-2.5-pro",
    logger=logger,
)
logger.info("✅ Modelo configurado para o agente: %s", AGENT_BASE_MODEL)

AGENT_SEARCH_MODEL = configure_model(
    env_var_name="MODEL_AGENT_SEARCH",
    env_registry_var_name="MODEL_AGENT_SEARCH_LIB",
    default_model="gemini-2.5-pro",
    logger=logger,
)
logger.info("✅ Modelo configurado para o agente de pesquisa: %s", AGENT_SEARCH_MODEL)


# Global cache for generated artifacts
LAST_GENERATION_RESULT: Dict[str, Any] = {}

# ============================================================================
# TOOL FUNCTIONS
# ============================================================================

def diagram_generator_tool(
        user_story: str = "",
        diagram_type: str = "container",
        elements: Optional[List[dict]] = None,
        relationships: Optional[List[dict]] = None,
        system_name: Optional[str] = None,
        steps: Optional[List[str]] = None,
        etapas: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Ferramenta principal para geração de diagramas C4.
    Agora exige mapeamento explícito (elements/relationships) produzido pelo prompt.
    Após geração, faz upload para GCS e gera URL assinada para acesso público.

    Args:
        user_story: História do usuário descrevendo o sistema
        diagram_type: Tipo do diagrama (context, container, component)
        elements: Lista de elementos mapeados explicitamente
        relationships: Lista de relacionamentos entre elementos
        system_name: Nome do sistema sendo modelado
        steps: Etapas do processo (português)
        etapas: Etapas do processo (alternativa)

    Returns:
        Dict com resultado da geração incluindo URL para download
    """
    global LAST_GENERATION_RESULT

    try:
        service = DiagramService()

        # Exigir mapeamento explícito
        if not elements or len(elements) == 0:
            logger.error("❌ Mapeamento explícito não fornecido pelo prompt")
            return {
                "success": False,
                "error": "Mapeamento explícito (elements/relationships) obrigatório.",
                "message": "Por favor, forneça o mapeamento completo de elementos e relacionamentos."
            }

        logger.info(f"🧭 Gerando diagrama a partir do mapeamento explícito")
        logger.info(f"   - Elementos: {len(elements)}")
        logger.info(f"   - Relacionamentos: {len(relationships or [])}")

        # Merge steps and etapas preserving order
        steps_labels: List[str] = (steps or []) + (etapas or [])

        # Processar com mapeamento explícito
        result = service.process_mapped_elements(
            elements=elements,
            relationships=relationships or [],
            diagram_type=diagram_type,
            system_name=system_name or "Sistema",
            steps_labels=steps_labels
        )

        if result.get("success"):
            xml_content = result.get("xml_content", "")
            local_file_path = result.get("file_path", "")
            filename = result.get("filename", f"diagrama_{diagram_type}.xml")

            logger.info(f"📊 Conformidade ao metamodelo: {result.get('conformance', 0)}%")
            logger.info(f"⭐ Qualidade geral: {result.get('quality_score', 0)}/100")

            # Upload para GCS e obter URL assinada
            blob_name = ""
            signed_url = ""

            try:
                logger.info(f"🚀 Iniciando upload para GCS - filename: {filename}")

                blob_name, signed_url = ensure_download_availability(
                    xml_content=xml_content,
                    local_file_path=local_file_path,
                    filename=filename
                )

                logger.info(f"✅ Download availability ensured")
                logger.info(f"   - Blob: {blob_name}")
                logger.info(f"   - URL: {signed_url[:100]}...")

            except Exception as upload_error:
                logger.error(f"❌ Erro no upload para GCS: {upload_error}")
                # Fallback para arquivo local
                if local_file_path:
                    signed_url = f"file:///{local_file_path}"
                    blob_name = filename
                    logger.info(f"📁 Fallback para arquivo local: {signed_url}")

            # Garantir que sempre temos uma URL
            if not signed_url:
                signed_url = f"Arquivo disponível: {filename}" if filename else "Link não disponível"
                logger.warning(f"⚠️ No signed_url set, using fallback: {signed_url}")

            logger.info(f"📋 Final result - blob_name: {blob_name}, signed_url: {signed_url}")

            # Atualizar cache global (substituindo Memory Bank)
            LAST_GENERATION_RESULT = {
                "gcs_blob_name": blob_name,
                "signed_url": signed_url,
                "filename": filename,
                "xml_content": xml_content,
                "local_file_path": local_file_path,
                "diagram_type": diagram_type,
                "system_name": system_name,
                "timestamp": result.get("timestamp", ""),
                "conformance": result.get("conformance", 0),
                "quality_score": result.get("quality_score", 0)
            }

            # Retornar resultado sanitizado
            final_result = {
                "success": True,
                "message": f"✅ Diagrama {diagram_type} gerado com sucesso!",
                "diagram_type": diagram_type,
                "system_name": system_name,
                "signed_url": signed_url,
                "gcs_blob_name": blob_name,
                "filename": filename,
                "xml_content": xml_content,
                # Aliases for prompt placeholder binding
                "diagram_download_url": signed_url,
                "diagram_gcs_location": blob_name,
                "metamodel_status": result.get("metamodel_status", "UNKNOWN"),
                "metamodel_applied": result.get("metamodel_applied", False),
                "conformance": result.get("conformance", 0),
                "quality_score": result.get("quality_score", 0),
                "quality_report": result.get("quality_report", {}),
                "compliance_summary": result.get("compliance_summary", {}),
                "quality_details": result.get("quality_details", {}),
                "metrics": {
                    "elements": len(elements),
                    "relationships": len(relationships or []),
                    "layers": result.get("layers_count", 0)
                }
            }

            return _sanitize_result_dict(final_result)

        else:
            error_msg = result.get("error", "Erro desconhecido na geração")
            logger.error(f"❌ Falha na geração: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "details": result.get("details", {})
            }

    except Exception as e:
        logger.error(f"❌ Erro na ferramenta de geração: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "message": "Erro ao processar o diagrama. Verifique o mapeamento fornecido."
        }


# Utility helpers required by tests

def _decode_unicode_escapes(text: str) -> str:
    """Decode unicode escape sequences like \u00E1 into actual characters."""
    if not isinstance(text, str):
        return text

    try:
        decoded = text.encode('utf-8').decode('unicode_escape')
    except Exception:
        decoded = text

    try:
        # Handle cases where UTF-8 characters were double-encoded (e.g., "Ã¡").
        return decoded.encode('latin-1').decode('utf-8')
    except Exception:
        return decoded


def process_message(message: str) -> str:
    """Send a message to the architect_agent and return decoded text.
    On error, return a friendly error string beginning with the expected prefix.
    """
    try:
        response = architect_agent.invoke(message)
        if isinstance(response, str):
            decoded = _decode_unicode_escapes(response)
        else:
            decoded = str(response)
        if is_logging_enabled():
            logger.info(f"Agent response: {decoded[:200]}")
        return decoded
    except Exception as e:
        logger.error(f"Processing error: {e}", exc_info=True)
        return f"❌ Erro no processamento: {e}"


def get_agent_capabilities() -> Dict[str, Any]:
    """Expose basic capabilities for tests and introspection."""
    try:
        tools_list = [
            'diagram_generator_tool',
            'quality_validator_tool',
            'vertex_search_tool',
        ]
        return {
            "name": architect_agent.name,
            "model": AGENT_BASE_MODEL,
            "supported_diagrams": ["context", "container", "component"],
            "tools": tools_list,
        }
    except Exception:
        return {
            "name": "architect_agent",
            "model": AGENT_BASE_MODEL,
            "supported_diagrams": ["context", "container", "component"],
            "tools": ["diagram_generator_tool", "quality_validator_tool"],
        }


def _sanitize_result_dict(result_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitiza e valida o dicionário de resultados.

    Args:
        result_dict: Dictionary containing generation results with URLs

    Returns:
        Dict: Sanitized result dictionary with validated URLs
    """
    # Check if signed_url exists and is valid
    signed_url = result_dict.get("signed_url", "")
    gcs_blob_name = result_dict.get("gcs_blob_name", "")

    # Validate URL format
    if signed_url and signed_url.startswith("https://storage.googleapis.com/"):
        logger.info(f"✅ Valid GCS URL detected: {signed_url[:100]}...")
    elif signed_url and signed_url.startswith("file:///"):
        logger.warning(f"⚠️ Local file URL fallback: {signed_url[:100]}...")
    elif signed_url:
        logger.warning(f"⚠️ Non-standard URL format: {signed_url[:100]}...")
    else:
        logger.error("❌ No valid URL found in result")

    return result_dict


def _validate_and_sanitize_urls(result_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates and sanitizes URLs in the result dictionary to ensure they are valid and accessible.

    Args:
        result_dict: Dictionary containing generation results with URLs

    Returns:
        Dict: Sanitized result dictionary with validated URLs
    """
    logger = logging.getLogger(__name__)

    # Check if signed_url exists and is valid
    signed_url = result_dict.get("signed_url", "")
    gcs_blob_name = result_dict.get("gcs_blob_name", "")

    # Validate URL format
    if signed_url and signed_url.startswith("https://storage.googleapis.com/"):
        logger.info(f"✅ Valid GCS URL detected: {signed_url[:100]}...")
    elif signed_url and signed_url.startswith("file:///"):
        logger.warning(f"⚠️ Local file URL fallback: {signed_url[:100]}...")
    elif signed_url:
        logger.warning(f"⚠️ Non-standard URL format: {signed_url[:100]}...")
    else:
        logger.error("❌ No valid URL found in result")

    return result_dict


def quality_validator_tool(
        xml_content: Optional[str] = None,
        validate_against: str = "metamodel"
) -> Dict[str, Any]:
    """
    Valida a qualidade de um diagrama ArchiMate; usa o metamodelo quando disponível.
    """
    global LAST_GENERATION_RESULT

    logger.info("🔍 Validando qualidade do diagrama")

    try:
        # Se não forneceu XML, usar o último gerado
        if not xml_content:
            if LAST_GENERATION_RESULT and "xml_content" in LAST_GENERATION_RESULT:
                xml_content = LAST_GENERATION_RESULT["xml_content"]
                logger.info("✅ Usando XML do último diagrama gerado")
            else:
                return {
                    "success": False,
                    "error": "Nenhum diagrama disponível para validação"
                }

        # Tentar usar o serviço com metamodelo se disponível
        try:
            service = DiagramService()
            if getattr(service, 'use_metamodel', False):
                meta_result = service._validate_diagram_quality(xml_content, "container")
                # Espera-se dict com chaves como is_metamodel_compliant/overall_score
                return {
                    "success": True,
                    "metamodel_compliant": bool(meta_result.get("is_metamodel_compliant", True)),
                    "overall_score": meta_result.get("overall_score", 0),
                    "details": meta_result,
                }
        except Exception as svc_err:
            logger.warning(f"Service validator unavailable, falling back: {svc_err}")
            # Continua para fallback

        # Fallback para validador unificado exposto em tools.validate_diagram_quality
        report = validate_diagram_quality(xml_content)
        # Suporta objetos com atributos (tests usam SimpleNamespace) ou dicts
        overall = getattr(report, 'overall_score', None)
        if overall is None and isinstance(report, dict):
            overall = report.get('overall_score', 0)
        quality_level = getattr(report, 'quality_level', None)
        summary = getattr(report, 'summary', None)
        elements_count = getattr(report, 'elements_count', None)
        relationships_count = getattr(report, 'relationships_count', None)
        recommendations = getattr(report, 'recommendations', None)
        issues = getattr(report, 'issues', None)

        return {
            "success": True,
            "metamodel_compliant": False,
            "overall_score": overall or 0,
            "quality_level": quality_level,
            "summary": summary,
            "elements_count": elements_count,
            "relationships_count": relationships_count,
            "recommendations": recommendations or [],
            "issues": issues or [],
        }

    except Exception as e:
        logger.error(f"❌ Erro na validação: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# Remove lightweight placeholder vertex_search_tool function to avoid name clash
# =========================================================================
# AGENTE VERTEX AI SEARCH (SIGLAS CMDB)
# =========================================================================
from app.tools.search.discovery_engine_search import discovery_search_tool as vertex_search_tool # using the default name previously defined

vertexai_search_agent = Agent(
    name="vertexai_search_agent",
    model=AGENT_SEARCH_MODEL,
    instruction=("""
    You are an expert system that matches user queries to system acronyms.
    
    DATA:
    - Acronyms are 4-letter base codes (some have module variants: base + suffix).
    - Each record has: u_acronym, comments, environment, u_service_classification.
    
    TASK:
    Given a user query and a set of retrieved records:
    0. Prepare the query correctly: make sure to make a search with **THE COMPLETE USER STORY**, as much detail as possible. Do not summarize anything!
    1. Consider only records with environment = "Produção".
    2. Evaluate conceptual alignment between the query and each record's comments.
        - Match = same system/functionality described.
        - No Match = only partial/keyword overlap.
    3. If a module matches, return its 4-letter bas and the suffix if it has one.
    4. Require at least 60% conceptual overlap (not just keywords).
    5. Check the similarity score. The correct acronym is the one with the highest score. 
        - Return only the highest score acronym and any other acronym with the SAME similarity score. Any thing lower than the highest scoring acronym must be discarded.

    OUTPUT:
    - Return a comma-separated list of base acronyms (if the base is the same and suffix is different, return both of them copmpletely).
    - If the returned acronym has a suffix, also return it's base acronym as well, as part of the list;
    - If no match: return exactly "N/A".
    - No explanations or extra text.
    """
    ),
    tools=[vertex_search_tool],
)

# ============================================================================
# AGENTE PRINCIPAL COM GOOGLE ADK - PADRÃO CORRETO
# ============================================================================

architect_agent = LlmAgent(
    name="architect_diagram_agent",
    model=AGENT_BASE_MODEL,
    description="Assistente especializado em arquitetura de software que gera diagramas C4 ArchiMate conforme metamodelo BiZZdesign a partir de user stories.",
    instruction=ARCHITECT_AGENT_PROMPT,
    tools=[
        diagram_generator_tool,
        quality_validator_tool,
        agent_tool.AgentTool(vertexai_search_agent, skip_summarization=False),
    ],
    after_model_callback=_sanitize_model_response
)


# ============================================================================
# EXPORTS FOR ADK COMPATIBILITY
# ============================================================================

root_agent = architect_agent
agent = architect_agent

__all__ = [
    "root_agent",
    "architect_agent",
    "agent",
    "diagram_generator_tool",
    "quality_validator_tool",
    "vertex_search_tool",
    "__version__"
]

logger.info(f"🚀 Architect Agent ADK v{__version__} inicializado com sucesso!")
logger.info("✅ Sistema de callback ativo para garantir URLs corretas do GCS")