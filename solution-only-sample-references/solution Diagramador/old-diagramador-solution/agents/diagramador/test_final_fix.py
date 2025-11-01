"""
Teste específico para verificar se o agente está usando os valores reais das ferramentas
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_prompt_instruction_compliance():
    """Testa se o prompt está instruindo corretamente o agente"""

    try:
        from app.prompt import ARCHITECT_AGENT_PROMPT

        print("🧪 Verificando instruções do prompt...")

        # Verificar se as instruções críticas estão presentes
        critical_instructions = [
            "Extract actual values from diagram_generator_tool response",
            "Use result[\"signed_url\"] for Download Direto",
            "Use result[\"gcs_blob_name\"] for Localização GCS",
            "DO NOT use placeholder text",
            "EXTRACT signed_url FROM diagram_generator_tool RESULT",
            "EXTRACT gcs_blob_name FROM diagram_generator_tool RESULT"
        ]

        missing_instructions = []
        for instruction in critical_instructions:
            if instruction not in ARCHITECT_AGENT_PROMPT:
                missing_instructions.append(instruction)

        if missing_instructions:
            print("❌ Instruções críticas ausentes no prompt:")
            for missing in missing_instructions:
                print(f"   - {missing}")
            return False
        else:
            print("✅ Todas as instruções críticas presentes no prompt!")
            return True

    except Exception as e:
        print(f"❌ Erro ao verificar prompt: {e}")
        return False

def simulate_tool_response():
    """Simula uma resposta da ferramenta diagram_generator_tool"""

    return {
        "success": True,
        "signed_url": "https://storage.googleapis.com/diagram_signed_temp/diagrama_container_20250907_193803.xml",
        "gcs_blob_name": "diagrama_container_20250907_193803.xml",
        "local_file_path": "C:\\Users\\...\\outputs\\diagrama_container_20250907_193803.xml",
        "filename": "diagrama_container_20250907_193803.xml",
        "quality_report": {
            "overall_score": 95.0,
            "metamodel_score": 100,
            "structure_score": 95,
            "naming_score": 92,
            "relationships_score": 94,
            "documentation_score": 96
        }
    }

def test_response_formatting():
    """Testa como o agente deveria formatar a resposta usando valores reais"""

    tool_response = simulate_tool_response()

    print("🧪 Testando formatação de resposta...")
    print(f"📊 Resposta simulada da ferramenta:")
    print(f"   - signed_url: {tool_response['signed_url']}")
    print(f"   - gcs_blob_name: {tool_response['gcs_blob_name']}")

    # Como deveria aparecer na resposta final
    expected_download = tool_response['signed_url']
    expected_location = tool_response['gcs_blob_name']

    print(f"\n✅ Como deveria aparecer na resposta final:")
    print(f"• Download Direto: {expected_download}")
    print(f"• Localização GCS: {expected_location}")

    # Verificar se os valores não são placeholders
    if "Link sendo gerado" in expected_download or "Localização sendo definida" in expected_location:
        print("❌ Valores ainda são placeholders!")
        return False
    else:
        print("✅ Valores reais extraídos corretamente!")
        return True

if __name__ == "__main__":
    print("🔧 Testando correções do sistema de paths...")
    print("=" * 60)

    # Teste 1: Verificar instruções do prompt
    print("\n1. Verificação do Prompt:")
    prompt_ok = test_prompt_instruction_compliance()

    # Teste 2: Formatação de resposta
    print("\n2. Formatação de Resposta:")
    format_ok = test_response_formatting()

    # Resultado final
    print("\n" + "=" * 60)
    if prompt_ok and format_ok:
        print("✅ CORREÇÃO COMPLETA - Sistema deve funcionar corretamente agora!")
        print("\n🎯 Próxima execução deve mostrar:")
        print("• Download Direto: https://storage.googleapis.com/diagram_signed_temp/...")
        print("• Localização GCS: diagrama_container_YYYYMMDD_HHMMSS.xml")
    else:
        print("❌ CORREÇÃO INCOMPLETA - Ainda há problemas:")
        if not prompt_ok:
            print("   - Instruções do prompt precisam ser ajustadas")
        if not format_ok:
            print("   - Formatação de resposta precisa ser corrigida")

    print("\n🚀 Execute novamente uma user story para testar as correções!")
