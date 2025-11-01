"""
Confirmation Handler - Gerencia o fluxo de confirmação e estado do agente
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Estado global para controlar o fluxo
CONFIRMATION_STATE = {
    "analysis_presented": False,
    "user_confirmed": False,
    "diagram_generated": False,
    "last_analysis": None,
    "generation_result": None
}

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
                CONFIRMATION_STATE["last_analysis"] = current_analysis

            logger.info("✅ Usuário confirmou - prosseguindo para geração")
            return {
                "action": "confirmed",
                "message": "Confirmação recebida - gerando diagrama...",
                "should_generate": True,
                "analysis": CONFIRMATION_STATE.get("last_analysis")
            }

        # Verificar necessidade de correção
        elif any(indicator in user_input_lower for indicator in negative_indicators):
            logger.info("🔄 Usuário solicitou correções")
            return {
                "action": "correction_needed",
                "message": "Correções necessárias - reanalise solicitada",
                "should_generate": False
            }

        # Entrada ambígua - solicitar clarificação
        else:
            logger.info("❓ Entrada ambígua - solicitando clarificação")
            return {
                "action": "clarification_needed",
                "message": "Por favor, digite 'SIM' para confirmar ou descreva as correções necessárias.",
                "should_generate": False
            }

    except Exception as e:
        logger.error(f"❌ Erro no processamento de confirmação: {e}")
        return {
            "action": "error",
            "message": f"Erro no processamento: {e}",
            "should_generate": False
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
        "generation_result": None
    }
    logger.info("🔄 Estado de confirmação resetado")

def is_diagram_generated() -> bool:
    """
    Verifica se o diagrama já foi gerado

    Returns:
        bool: True se o diagrama já foi gerado
    """
    return CONFIRMATION_STATE.get("diagram_generated", False)
