#!/usr/bin/env python3
"""
Teste de upload para GCS para identificar o problema específico
"""

from app.utils.gcs import upload_and_get_signed_url
import traceback

def test_gcs_upload():
    # XML de exemplo simples
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<model xmlns="http://www.opengroup.org/xsd/archimate/3.0/" identifier="test-model">
    <name xml:lang="pt-br">Teste Upload GCS</name>
</model>"""

    print("🔍 Testando upload para GCS...")
    print(f"📄 XML content length: {len(xml_content)} caracteres")

    try:
        blob_name, signed_url = upload_and_get_signed_url(xml_content)
        print("✅ Upload bem-sucedido!")
        print(f"📁 Blob: {blob_name}")
        print(f"🔗 URL: {signed_url}")
        return True

    except Exception as e:
        print(f"❌ Erro no upload: {str(e)}")
        print(f"🔧 Tipo do erro: {type(e).__name__}")
        print("📋 Stack trace completo:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_gcs_upload()
    print(f"\n🎯 Resultado final: {'SUCESSO' if success else 'FALHOU'}")
