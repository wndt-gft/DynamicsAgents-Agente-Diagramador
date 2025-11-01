import csv
import json
from datetime import datetime


def create_acronym_files():
    """
    Cria arquivos CSV e JSON com siglas baseado no print fornecido.
    Não requer bibliotecas de Excel.
    """

    # Dados extraídos do print
    data = [
        {
            'u_acronym': 'AADA-RISK',
            'comments': 'Autenticação Avançada risk usando CA Risk',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Autenticação e Autorização - CORE',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Serviço de Não Avalia Módulo',
            'sys_cla': 'u_lba'
        },
        {
            'u_acronym': 'AADA-STRG',
            'comments': 'Autenticação Avançada usando Múltiplos Fatores de Autenticação da CA Strong',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Autenticação e Autorização - CORE',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Serviço de Não Avalia Módulo',
            'sys_cla': 'u_lba'
        },
        {
            'u_acronym': 'AADA',
            'comments': 'Produto de autenticação avançada e avaliação risco',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Autenticação e Autorização - CORE',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Serviço de Não Avalia Infraestrutura',
            'sys_cla': 'u_syste'
        },
        {
            'u_acronym': 'ANFL',
            'comments': 'Produto de autenticação avançada e avaliação micro',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Inteligência de Dados',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Produto de autenticação avançada e avaliação micro',
            'sys_cla': 'u_syste'
        },
        {
            'u_acronym': 'AADA-ANLT',
            'comments': 'Sigla para ambientes Analíticos em áreas referente a área de negócio do PLD',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Inteligência de Dados',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Sigla para ambientes Analíticos em áreas referente a área de negócio do PLD',
            'sys_cla': 'u_lba'
        },
        {
            'u_acronym': 'AADA-HBIO',
            'comments': 'Sigla para ambiente Hadoop em Cloud. Serviço para referenciar a área referente a área de negócio do PLD',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Inteligência de Dados',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Sigla para ambiente Hadoop em Cloud. Serviço para referenciar a área referente a área de negócio do PLD',
            'sys_cla': 'u_lba'
        },
        {
            'u_acronym': 'ASDI',
            'comments': 'Sistema de notificações do feedback para squid',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Análise de Fraudes',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Sistema de Notificações de feedback para squid',
            'sys_cla': 'u_syste'
        },
        {
            'u_acronym': 'HFAO',
            'comments': 'Sistema de múltiplas fatores de autenticação de segurança',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Monitoramento transacional de fraudes',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Sistema de múltiplas fatores de autenticação de segurança',
            'sys_cla': 'u_syste'
        },
        {
            'u_acronym': 'OFRD-ONBD',
            'comments': 'Sistema Single Sign-On (SSO) federativo utilizando o NetOps Portal e todos os fontes de dados suportadas',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Onboarding e Renovação',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Sigla para o barramento de prevenção e fraudes, base transacional',
            'sys_cla': 'u_syste'
        },
        {
            'u_acronym': 'OFRD-TRAN',
            'comments': 'Sistema de múltiplas fatores de autenticação de segurança para transações',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Onboarding e Renovação',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Sigla para o barramento de prevenção e fraudes de análise e descoberta',
            'sys_cla': 'u_syste'
        },
        {
            'u_acronym': 'HBBI',
            'comments': 'Sigla para o barramento de prevenção e fraudes, base transacional',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de Monitoramento transacional de fraudes',
            'u_tower': 'Prevenção Autenticação e Autorização - CORE',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Política de Riscos de Identidade e Acesso de Clientes por meio de ferramenta da informação',
            'sys_cla': 'u_syste'
        },
        {
            'u_acronym': 'AADA-PDNA',
            'comments': 'Sigla para o barramento de prevenção e fraudes de análise e descoberta',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Inteligência de Dados',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Diretório de identidade do PING Identity',
            'sys_cla': 'u_syste'
        },
        {
            'u_acronym': 'OAM',
            'comments': 'Política de Riscos de Identidade e Acesso de Clientes por meio de ferramentas da informação',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Autenticação e Autorização - CORE',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Gestão de Identidade e Acesso de Clientes por meio de ferramentas da informação',
            'sys_cla': 'u_syste'
        },
        {
            'u_acronym': 'CLAM-CDIR',
            'comments': 'Gestão de Identidade e Acesso de Clientes por meio de ferramentas da informação',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Autenticação e Autorização - CORE',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Diretório de autenticação do PING Identity',
            'sys_cla': 'u_syste'
        },
        {
            'u_acronym': 'OFRD-CGAM-PDIR',
            'comments': 'Diretório de autenticação do PING Identity com componente PDIR',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Autenticação e Autorização - CORE',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Diretório de autenticação do PING Identity com PDIR',
            'sys_cla': 'u_syste'
        },
        {
            'u_acronym': 'CLAM-PFED',
            'comments': 'Federação de autenticação com PING Identity',
            'u_install_status': 'Em Uso',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Prevenção Autenticação e Autorização - CORE',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Federação de autenticação com PING Identity',
            'sys_cla': 'u_syste'
        },
        {
            'u_acronym': 'PLCD-PLTD',
            'comments': 'Sigla que não recebeu os componentes da plataforma de dados referente a área de negócio do PLD',
            'u_install_status': 'Descontinuado',
            'environment': 'Produção',
            'u_service_classification': 'Serviço de gestão de tecnologia',
            'u_tower': 'Atacado - Monitoramento PLD',
            'u_squad_name': 'Prevenção Crimes Financeiros',
            'u_tribe_name': 'Sigla que não recebeu os componentes da plataforma de dados referente a área de negócio do PLD',
            'sys_cla': 'u_syste'
        }
    ]

    # Adicionar timestamps
    timestamp = datetime.now()
    for item in data:
        item['created_date'] = timestamp.strftime('%Y-%m-%d')
        item['last_updated'] = timestamp.strftime('%Y-%m-%d %H:%M:%S')

    # 1. Criar arquivo CSV
    csv_file = 'agents/diagramador/app/samples/acronyms_database.csv'

    # Definir ordem das colunas
    fieldnames = [
        'u_acronym', 'comments', 'u_install_status', 'environment',
        'u_service_classification', 'u_tower', 'u_squad_name',
        'u_tribe_name', 'sys_cla', 'created_date', 'last_updated'
    ]

    try:
        with open(csv_file, 'w', newline='', encoding='utf-8-sig') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        print(f"✅ Arquivo CSV '{csv_file}' criado com sucesso!")

    except Exception as e:
        print(f"❌ Erro ao criar CSV: {e}")
        return None

    # 2. Criar arquivo JSON
    json_file = 'acronyms_database.json'

    try:
        with open(json_file, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=2, ensure_ascii=False)

        print(f"✅ Arquivo JSON '{json_file}' criado com sucesso!")

    except Exception as e:
        print(f"❌ Erro ao criar JSON: {e}")

    # 3. Estatísticas
    print(f"\n📊 Total de siglas: {len(data)}")
    print(f"📋 Colunas incluídas: {', '.join(fieldnames)}")

    ativas = sum(1 for item in data if item['u_install_status'] == 'Em Uso')
    descontinuadas = sum(1 for item in data if item['u_install_status'] == 'Descontinuado')

    print("\n📈 Estatísticas:")
    print(f"  - Siglas ativas: {ativas}")
    print(f"  - Siglas descontinuadas: {descontinuadas}")

    # Torres únicas
    towers = set(item['u_tower'] for item in data)
    print(f"  - Torres únicas: {len(towers)}")

    # Preview dos dados
    print("\n📋 Preview dos dados (primeiras 5 siglas):")
    print("-" * 60)
    for i, item in enumerate(data[:5]):
        print(f"{item['u_acronym']:15} → {item['comments'][:45]}...")

    print("\n✨ Arquivos prontos para uso!")
    print("💡 Use 'acronyms_database.csv' no sistema de mapeamento")

    # Verificar se os arquivos foram criados
    import os
    print("\n📁 Arquivos criados:")
    for file in [csv_file, json_file]:
        if os.path.exists(file):
            size = os.path.getsize(file)
            print(f"  ✓ {file} ({size:,} bytes)")
        else:
            print(f"  ✗ {file} (não encontrado)")

    return data


# Executar
if __name__ == "__main__":
    print("🚀 Iniciando criação dos arquivos de siglas...")
    print("=" * 60)

    result = create_acronym_files()

    if result:
        print("\n✅ Processo concluído com sucesso!")
        print("📌 Os arquivos CSV e JSON estão prontos para uso")
    else:
        print("\n❌ Houve um erro no processo")