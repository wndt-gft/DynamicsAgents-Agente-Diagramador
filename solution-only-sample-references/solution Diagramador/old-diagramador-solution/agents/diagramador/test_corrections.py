"""
Teste das correções realizadas no sistema de upload GCS e retorno de paths
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_gcs_upload_with_correct_paths():
    """Testa se o upload para GCS está retornando os paths corretos"""

    try:
        from app.utils.gcs import upload_and_get_signed_url

        # XML de teste
        test_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<model xmlns="http://www.opengroup.org/xsd/archimate/3.0/">
    <name xml:lang="pt-br">Teste de Upload</name>
</model>'''

        print("🧪 Testando upload para GCS...")

        # Fazer upload
        blob_name, signed_url = upload_and_get_signed_url(
            xml_content=test_xml,
            filename="test_upload.xml"
        )

        print(f"✅ Upload realizado com sucesso!")
        print(f"📁 Blob name: {blob_name}")
        print(f"🔗 Signed URL: {signed_url}")

        # Verificar se os valores não estão vazios
        if blob_name and signed_url:
            print("✅ Paths retornados corretamente!")
            return True
        else:
            print("❌ Paths vazios retornados!")
            return False

    except Exception as e:
        print(f"❌ Erro no teste: {e}")
        return False

def test_diagram_service_with_explicit_mapping():
    """Testa se o DiagramService está processando corretamente o mapeamento explícito"""

    try:
        from app.tools.diagram_service import DiagramService

        print("🧪 Testando DiagramService com mapeamento explícito...")

        # Criar elementos de teste
        elements = [
            {"id": "1", "name": "Portal Web", "type": "ApplicationCollaboration", "layer": "channels"},
            {"id": "2", "name": "API Gateway", "type": "TechnologyService", "layer": "gateway_inbound"},
            {"id": "3", "name": "Serviço Principal", "type": "ApplicationComponent", "layer": "execution_logic"},
            {"id": "4", "name": "Base de Dados", "type": "DataObject", "layer": "data_management"}
        ]

        relationships = [
            {"source_id": "1", "target_id": "2", "type": "Serving", "rationale": "Acesso via gateway"},
            {"source_id": "2", "target_id": "3", "type": "Serving", "rationale": "Processa requisições"},
            {"source_id": "3", "target_id": "4", "type": "Access", "rationale": "Acessa dados"}
        ]

        service = DiagramService()
        result = service.process_mapped_elements(
            elements=elements,
            relationships=relationships,
            diagram_type="container",
            system_name="Sistema de Teste"
        )

        if result.get("success"):
            print("✅ Diagrama gerado com sucesso!")
            print(f"📁 Arquivo local: {result.get('local_file_path', 'N/A')}")
            print(f"📄 Nome do arquivo: {result.get('filename', 'N/A')}")
            return True
        else:
            print(f"❌ Falha na geração: {result.get('error', 'Erro desconhecido')}")
            return False

    except Exception as e:
        print(f"❌ Erro no teste: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Testando correções implementadas...")
    print("=" * 50)

    # Teste 1: Upload GCS
    print("\n1. Teste de Upload GCS:")
    gcs_success = test_gcs_upload_with_correct_paths()

    # Teste 2: DiagramService
    print("\n2. Teste de DiagramService:")
    service_success = test_diagram_service_with_explicit_mapping()

    # Resultado final
    print("\n" + "=" * 50)
    if gcs_success and service_success:
        print("✅ Todas as correções funcionando corretamente!")
    else:
        print("❌ Algumas correções ainda precisam de ajustes.")
        if not gcs_success:
            print("   - Problema com upload GCS")
        if not service_success:
            print("   - Problema com DiagramService")
