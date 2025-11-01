"""Confirmation Handler - Gerencia o fluxo de confirmação e estado do agente."""

from copy import deepcopy
import logging
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)

# Estado global para controlar o fluxo
CONFIRMATION_STATE = {
    "analysis_presented": False,
    "user_confirmed": False,
    "diagram_generated": False,
    "last_analysis": None,
    "generation_result": None,
    "approved_analysis": None,
    "approved_elements": None,
    "approved_relationships": None,
    "approved_steps": None,
    "approved_system_name": None,
}


def _iter_candidate_dicts(payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """Iterate through potential snapshot dictionaries inside ``payload``."""

    queue: list[Dict[str, Any]] = []
    seen: set[int] = set()

    if isinstance(payload, dict):
        queue.append(payload)

    while queue:
        candidate = queue.pop(0)
        identifier = id(candidate)
        if identifier in seen:
            continue
        seen.add(identifier)
        yield candidate

        for value in candidate.values():
            if isinstance(value, dict):
                queue.append(value)
            elif isinstance(value, (list, tuple, set)):
                for item in value:
                    if isinstance(item, dict):
                        queue.append(item)


def _normalize_snapshot_source(snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract a normalized snapshot with elements and metadata."""

    if not isinstance(snapshot, dict):
        return {}

    for candidate in _iter_candidate_dicts(snapshot):
        elements = candidate.get("elements")
        if not elements:
            continue

        relationships = candidate.get("relationships")
        steps = candidate.get("steps")

        system_name = candidate.get("system_name") or candidate.get("system")
        summary = candidate.get("summary") if isinstance(candidate.get("summary"), dict) else {}
        if not system_name:
            system_name = summary.get("system_name") or summary.get("system")

        return {
            "analysis": candidate,
            "elements": elements,
            "relationships": relationships,
            "steps": steps,
            "system_name": system_name,
        }

    return {}

def handle_user_confirmation(user_input: str, current_analysis: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Processa a entrada do usuário para detectar confirmação ou necessidade de correção

    Args:
        user_input: Entrada do usuário
        current_analysis: Análise atual (se disponível)

    Returns:
        Dict: Resultado do processamento da confirmação
    """
    global CONFIRMATION_STATE

    try:
        user_input_lower = user_input.lower().strip()

        # Verificar se o diagrama já foi gerado
        if CONFIRMATION_STATE.get("diagram_generated", False):
            logger.info("⚠️ Diagrama já foi gerado - bloqueando nova geração")
            return {
                "action": "already_generated",
                "message": "Diagrama já gerado. Para novo diagrama, inicie nova conversa.",
                "should_stop": True
            }

        # Detectar confirmação positiva
        positive_indicators = [
            "sim", "ok", "correto", "confirmo", "gerar", "pode gerar",
            "está correto", "tudo certo", "perfeito", "concordo"
        ]

        # Detectar necessidade de correção
        negative_indicators = [
            "não", "nao", "errado", "incorreto", "corrigir", "alterar",
            "mudar", "modificar", "revisar", "ajustar"
        ]

        # Verificar confirmação positiva
        if any(indicator in user_input_lower for indicator in positive_indicators):
            CONFIRMATION_STATE["user_confirmed"] = True
            if current_analysis:
                CONFIRMATION_STATE["last_analysis"] = deepcopy(current_analysis)

            snapshot_source = current_analysis or CONFIRMATION_STATE.get("last_analysis")
            if snapshot_source:
                update_approved_snapshot(snapshot_source)
            else:
                update_approved_snapshot(None)

            logger.info("✅ Usuário confirmou - prosseguindo para geração")
            return {
                "action": "confirmed",
                "message": "Confirmação recebida - gerando diagrama...",
                "should_generate": True,
                "analysis": deepcopy(CONFIRMATION_STATE.get("last_analysis")),
            }

        # Verificar necessidade de correção
        elif any(indicator in user_input_lower for indicator in negative_indicators):
            logger.info("🔄 Usuário solicitou correções")
            update_approved_snapshot(None)
            return {
                "action": "correction_needed",
                "message": "Correções necessárias - reanalise solicitada",
                "should_generate": False,
            }

        # Entrada ambígua - solicitar clarificação
        else:
            logger.info("❓ Entrada ambígua - solicitando clarificação")
            update_approved_snapshot(None)
            return {
                "action": "clarification_needed",
                "message": "Por favor, digite 'SIM' para confirmar ou descreva as correções necessárias.",
                "should_generate": False,
            }

    except Exception as e:
        logger.error(f"❌ Erro no processamento de confirmação: {e}")
        return {
            "action": "error",
            "message": f"Erro no processamento: {e}",
            "should_generate": False,
        }


def update_approved_snapshot(snapshot: Optional[Dict[str, Any]]) -> None:
    """Armazena uma cópia do snapshot aprovado para reutilização posterior."""

    global CONFIRMATION_STATE

    if not snapshot:
        CONFIRMATION_STATE["approved_analysis"] = None
        CONFIRMATION_STATE["approved_elements"] = None
        CONFIRMATION_STATE["approved_relationships"] = None
        CONFIRMATION_STATE["approved_steps"] = None
        CONFIRMATION_STATE["approved_system_name"] = None
        return

    normalized = _normalize_snapshot_source(snapshot)
    if not normalized:
        CONFIRMATION_STATE["approved_analysis"] = None
        CONFIRMATION_STATE["approved_elements"] = None
        CONFIRMATION_STATE["approved_relationships"] = None
        CONFIRMATION_STATE["approved_steps"] = None
        CONFIRMATION_STATE["approved_system_name"] = None
        return

    CONFIRMATION_STATE["approved_analysis"] = deepcopy(normalized.get("analysis"))
    CONFIRMATION_STATE["approved_elements"] = deepcopy(normalized.get("elements"))
    CONFIRMATION_STATE["approved_relationships"] = deepcopy(
        normalized.get("relationships")
    )
    CONFIRMATION_STATE["approved_steps"] = deepcopy(normalized.get("steps"))
    CONFIRMATION_STATE["approved_system_name"] = deepcopy(
        normalized.get("system_name")
    )


def get_approved_snapshot() -> Dict[str, Any]:
    """Retorna uma cópia dos dados aprovados para geração de diagrama."""

    return {
        "analysis": deepcopy(CONFIRMATION_STATE.get("approved_analysis"))
        if CONFIRMATION_STATE.get("approved_analysis")
        else None,
        "elements": deepcopy(CONFIRMATION_STATE.get("approved_elements"))
        if CONFIRMATION_STATE.get("approved_elements")
        else None,
        "relationships": deepcopy(CONFIRMATION_STATE.get("approved_relationships"))
        if CONFIRMATION_STATE.get("approved_relationships")
        else None,
        "steps": deepcopy(CONFIRMATION_STATE.get("approved_steps"))
        if CONFIRMATION_STATE.get("approved_steps")
        else None,
        "system_name": deepcopy(CONFIRMATION_STATE.get("approved_system_name"))
        if CONFIRMATION_STATE.get("approved_system_name")
        else None,
    }

def mark_diagram_generated(generation_result: Dict[str, Any]) -> None:
    """
    Marca que o diagrama foi gerado com sucesso e armazena o resultado

    Args:
        generation_result: Resultado da geração do diagrama
    """
    global CONFIRMATION_STATE

    CONFIRMATION_STATE["diagram_generated"] = True
    CONFIRMATION_STATE["generation_result"] = generation_result
    logger.info("✅ Diagrama marcado como gerado - estado atualizado")

def get_generation_result() -> Optional[Dict[str, Any]]:
    """
    Retorna o resultado da geração do diagrama se disponível

    Returns:
        Dict ou None: Resultado da geração
    """
    return CONFIRMATION_STATE.get("generation_result")

def reset_confirmation_state() -> None:
    """
    Reseta o estado de confirmação (para nova conversa)
    """
    global CONFIRMATION_STATE

    CONFIRMATION_STATE = {
        "analysis_presented": False,
        "user_confirmed": False,
        "diagram_generated": False,
        "last_analysis": None,
        "generation_result": None,
        "approved_analysis": None,
        "approved_elements": None,
        "approved_relationships": None,
        "approved_steps": None,
        "approved_system_name": None,
    }
    logger.info("🔄 Estado de confirmação resetado")

def is_diagram_generated() -> bool:
    """
    Verifica se o diagrama já foi gerado

    Returns:
        bool: True se o diagrama já foi gerado
    """
    return CONFIRMATION_STATE.get("diagram_generated", False)


class ConfirmationHandler:
    """Wrapper compatível com a assinatura legada baseada em classe."""

    handle_user_confirmation = staticmethod(handle_user_confirmation)
    mark_diagram_generated = staticmethod(mark_diagram_generated)
    get_generation_result = staticmethod(get_generation_result)
    reset_confirmation_state = staticmethod(reset_confirmation_state)
    is_diagram_generated = staticmethod(is_diagram_generated)
    update_approved_snapshot = staticmethod(update_approved_snapshot)
    get_approved_snapshot = staticmethod(get_approved_snapshot)
