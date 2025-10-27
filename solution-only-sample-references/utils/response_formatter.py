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

"""Human-friendly response formatter for better UX."""

from typing import Dict, List, Any


def format_validation_response_for_user(validation_data: Dict[str, Any]) -> str:
    """
    Transform technical validation JSON into a friendly, conversational message.

    Args:
        validation_data: The technical validation response dictionary

    Returns:
        A human-friendly formatted message
    """
    is_valid = validation_data.get("is_valid", False)
    quality_metrics = validation_data.get("quality_metrics", {})
    syntax_validation = validation_data.get("syntax_validation", {})
    can_proceed = validation_data.get("can_proceed", False)

    # Extract scores
    overall_score = quality_metrics.get("overall_score", 0)
    coverage_score = quality_metrics.get("coverage_score", 0)
    syntax_score = quality_metrics.get("syntax_score", 0)
    best_practices_score = quality_metrics.get("best_practices_score", 0)
    security_score = quality_metrics.get("security_score", 0)

    # Extract issues and recommendations
    issues = quality_metrics.get("issues_found", [])
    recommendations = quality_metrics.get("recommendations", [])
    hallucinations = quality_metrics.get("hallucinations_detected", [])

    # Build the friendly message
    message_parts = []

    # Header with emoji and status
    if overall_score >= 90:
        message_parts.append("✨ **Excelente! Seus testes estão com qualidade excepcional!** ✨\n")
    elif overall_score >= 70:
        message_parts.append("✅ **Ótimo! Seus testes foram aprovados!** ✅\n")
    elif overall_score >= 50:
        message_parts.append("⚠️ **Quase lá! Seus testes precisam de alguns ajustes.** ⚠️\n")
    else:
        message_parts.append("🔧 **Vamos melhorar! Encontramos alguns pontos que precisam de atenção.** 🔧\n")

    # Overall assessment
    message_parts.append(f"\n📊 **Avaliação Geral: {overall_score}/100**\n")

    # Score breakdown with visual indicators
    message_parts.append("\n**Detalhamento por categoria:**\n")
    message_parts.append(f"  {_score_bar(coverage_score)} Cobertura de Testes: {coverage_score}/100\n")
    message_parts.append(f"  {_score_bar(syntax_score)} Sintaxe: {syntax_score}/100\n")
    message_parts.append(f"  {_score_bar(best_practices_score)} Boas Práticas: {best_practices_score}/100\n")
    message_parts.append(f"  {_score_bar(security_score)} Segurança: {security_score}/100\n")

    # Syntax validation status
    if syntax_validation.get("is_valid", False):
        message_parts.append("\n✓ **Validação de Sintaxe:** Tudo certo! Nenhum erro de sintaxe encontrado.\n")
    else:
        errors = syntax_validation.get("errors", [])
        if errors:
            message_parts.append("\n⚠️ **Validação de Sintaxe:** Encontramos alguns problemas:\n")
            for error in errors[:3]:  # Show first 3 errors
                message_parts.append(f"  • {error}\n")
            if len(errors) > 3:
                message_parts.append(f"  ... e mais {len(errors) - 3} problema(s).\n")

    # Hallucinations check
    if hallucinations:
        message_parts.append("\n🚨 **Atenção - Inconsistências Detectadas:**\n")
        message_parts.append("Encontramos alguns elementos nos testes que não correspondem à especificação original:\n")
        for hallucination in hallucinations[:3]:
            message_parts.append(f"  • {hallucination}\n")
        message_parts.append("\n💡 *Certifique-se de que todos os endpoints e dados usados nos testes correspondem exatamente à sua especificação.*\n")

    # Issues found
    if issues and len(issues) > 0:
        message_parts.append("\n🔍 **Pontos de Atenção:**\n")
        for issue in issues[:5]:  # Show first 5 issues
            message_parts.append(f"  • {issue}\n")
        if len(issues) > 5:
            message_parts.append(f"  ... e mais {len(issues) - 5} ponto(s) identificado(s).\n")

    # Recommendations
    if recommendations and len(recommendations) > 0:
        message_parts.append("\n💡 **Recomendações para você:**\n")
        for idx, rec in enumerate(recommendations, 1):
            # Make recommendations more conversational
            friendly_rec = _make_recommendation_friendly(rec)
            message_parts.append(f"  {idx}. {friendly_rec}\n")

    # Final verdict
    message_parts.append("\n" + "─" * 60 + "\n")
    if can_proceed:
        message_parts.append("\n🎉 **Status: PRONTO PARA USO!**\n")
        message_parts.append("\nSeus testes atingiram o padrão de qualidade necessário e estão prontos para serem executados.\n")
        message_parts.append("Você pode prosseguir com confiança! 🚀\n")
    else:
        message_parts.append("\n🔄 **Status: NECESSITA REFINAMENTO**\n")
        message_parts.append("\nOs testes precisam de alguns ajustes antes de estarem prontos para uso em produção.\n")
        message_parts.append("Não se preocupe - estamos aqui para ajudar a melhorar! 💪\n")

    return "".join(message_parts)


def _score_bar(score: int) -> str:
    """Generate a visual score bar with emojis."""
    if score >= 90:
        return "🟢🟢🟢🟢🟢"
    elif score >= 70:
        return "🟢🟢🟢🟢⚪"
    elif score >= 50:
        return "🟡🟡🟡⚪⚪"
    elif score >= 30:
        return "🟠🟠⚪⚪⚪"
    else:
        return "🔴⚪⚪⚪⚪"


def _make_recommendation_friendly(recommendation: str) -> str:
    """Convert technical recommendations into friendly, actionable advice."""
    # Map technical phrases to friendly ones
    friendly_mappings = {
        "high quality": "excelente qualidade",
        "addresses all critical issues": "corrige todos os problemas críticos",
        "hallucinations have been eliminated": "inconsistências foram eliminadas",
        "To achieve 100% coverage": "Para alcançar cobertura completa",
        "consider adding": "considere adicionar",
        "feature files for": "arquivos de teste para",
        "endpoints": "endpoints",
        "based on the original specification": "conforme a especificação original",
    }

    result = recommendation
    for tech_term, friendly_term in friendly_mappings.items():
        result = result.replace(tech_term, friendly_term)

    # Add conversational touches
    if "100% coverage" in result:
        result = "🎯 " + result + " Isso deixará seus testes ainda mais completos!"
    elif "high quality" in recommendation or "excelente qualidade" in result:
        result = "👏 " + result

    return result


def format_refinement_complete_message(final_data: Dict[str, Any]) -> str:
    """
    Format a completion message when refinement is successful.

    Args:
        final_data: Dictionary with final metrics and results

    Returns:
        Friendly completion message
    """
    score = final_data.get("overall_score", 0)
    iterations = final_data.get("iterations_used", 0)

    message = [
        "\n" + "=" * 60,
        "\n🎊 **PARABÉNS! SEUS TESTES ESTÃO PRONTOS!** 🎊\n",
        "=" * 60 + "\n\n"
    ]

    message.append(f"✨ **Qualidade Final:** {score}/100\n")
    message.append(f"🔄 **Iterações Necessárias:** {iterations}\n\n")

    if score >= 95:
        message.append("🏆 **Nível Excepcional!** Seus testes atingiram um padrão de qualidade premium.\n")
    elif score >= 85:
        message.append("🌟 **Excelente Trabalho!** Seus testes estão com qualidade profissional.\n")
    else:
        message.append("✅ **Ótimo Resultado!** Seus testes estão aprovados e prontos para uso.\n")

    message.append("\n**Próximos passos:**\n")
    message.append("  1. ✅ Revise os arquivos de teste gerados\n")
    message.append("  2. 🚀 Execute os testes no seu ambiente\n")
    message.append("  3. 📊 Analise os resultados e relatórios\n")
    message.append("  4. 🔄 Mantenha os testes atualizados conforme sua aplicação evolui\n")

    message.append("\nBom trabalho! 💪 Seus testes automatizados estão prontos para garantir a qualidade do seu sistema.\n")

    return "".join(message)

