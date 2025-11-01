# architect_agent/tools/analyzer.py
"""
Ferramenta de análise de user stories
Extrai elementos arquiteturais de user stories usando IA
"""

import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import os

# Configure logger first
logger = logging.getLogger(__name__)

# Usar Google Generative AI com fallback
try:
    from google import genai

    # Configurar cliente Vertex AI
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-east5")

    # Modelo correto para Vertex AI
    VERTEX_AI_MODEL = "gemini-2.5-flash"

    # Criar cliente apenas se tivermos projeto configurado
    if project_id:
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location
        )
        AI_AVAILABLE = True
    else:
        AI_AVAILABLE = False

except ImportError:
    AI_AVAILABLE = False
    logger.warning("Google Generative AI não disponível, usando fallback")

# Prompts genéricos e eficientes
ANALYSIS_PROMPTS = {
    "Banking": """
Analise esta user story bancária e extraia elementos arquiteturais seguindo o metamodelo ArchiMate 3.1.

📋 **User Story**:
{story_text}

🎯 **Contexto do domínio bancário brasileiro**:
{patterns}

Extraia e organize TODOS os elementos arquiteturais mencionados ou implícitos na história:

{{
    "business_layer": {{
        "actors": ["todos os atores/stakeholders/personas identificados"],
        "processes": ["processos de negócio mencionados ou necessários"],
        "services": ["serviços de negócio oferecidos aos clientes"],
        "objects": ["objetos/entidades de negócio manipulados"]
    }},
    "application_layer": {{
        "components": ["sistemas/aplicações/módulos necessários"],
        "services": ["APIs/serviços de aplicação mencionados"],
        "interfaces": ["canais de acesso/interfaces de usuário"],
        "data_objects": ["entidades de dados/informações processadas"]
    }},
    "technology_layer": {{
        "nodes": ["infraestrutura física/virtual necessária"],
        "infrastructure_services": ["serviços de infraestrutura/plataforma"],
        "artifacts": ["artefatos deployáveis/componentes técnicos"]
    }},
    "requirements": {{
        "functional": ["requisitos funcionais explícitos"],
        "non_functional": ["requisitos não-funcionais (performance, segurança, etc)"],
        "business_rules": ["regras de negócio/políticas/limites"]
    }},
    "integration_points": [
        {{
            "system": "nome do sistema externo",
            "type": "internal/external/regulatory",
            "protocol": "protocolo/padrão de integração"
        }}
    ],
    "cross_cutting_concerns": {{
        "security": ["aspectos de segurança transversais"],
        "audit": ["requisitos de auditoria e rastreabilidade"],
        "compliance": ["requisitos de conformidade"],
        "monitoring": ["aspectos de monitoramento"]
    }}
}}

📌 **Diretrizes de extração**:
1. Identifique elementos EXPLÍCITOS e IMPLÍCITOS
2. Use nomenclatura padrão do setor bancário brasileiro
3. Considere integrações regulatórias obrigatórias (BACEN, Receita, etc)
4. Inclua componentes de segurança quando relevante
5. Mapeie tecnologias mencionadas para a camada apropriada
6. Extraia TODAS as regras de negócio e limites operacionais
7. Identifique concerns transversais (auditoria, segurança, monitoramento)

Retorne APENAS o JSON estruturado, sem explicações adicionais.
"""
}

# Padrões bancários genéricos
BANKING_PATTERNS = {
    "common_actors": [
        "Cliente (PF/PJ)", "Funcionário Banco", "Gerente", "Auditor",
        "Sistema Regulatório", "Bureau de Crédito", "Parceiro/Fornecedor"
    ],
    "regulatory_systems": [
        "BACEN", "SPB", "SPI", "DICT", "SCR", "CIP", "COAF", "Receita Federal"
    ],
    "common_processes": [
        "Onboarding", "KYC/AML", "Autenticação", "Autorização", "Processamento Transação",
        "Análise de Risco", "Auditoria", "Conciliação", "Compliance"
    ],
    "security_components": [
        "HSM", "Tokenização", "Criptografia", "MFA", "Antifraude", "SIEM"
    ],
    "infrastructure_components": [
        "Kafka", "Redis", "PostgreSQL", "MongoDB", "Elasticsearch", "Prometheus"
    ],
    "common_technologies": [
        "Mainframe", "Microserviços", "API Gateway", "Message Queue", "Cache",
        "Database", "Container", "Cloud", "Mobile", "Web"
    ]
}


def analyze_user_story_tool(story_text: str, domain: str = "Banking") -> Dict[str, Any]:
    """
    Tool wrapper para análise de user stories

    Args:
        story_text: Texto da user story
        domain: Domínio da aplicação (default: Banking)

    Returns:
        Dict com elementos arquiteturais extraídos
    """
    return analyze_user_story(story_text, domain)


def analyze_user_story(story_text: str, domain: str = "Banking") -> Dict[str, Any]:
    """
    Analisa uma user story e extrai elementos arquiteturais

    Args:
        story_text: Texto completo da história de usuário
        domain: Domínio da aplicação (Banking, Insurance, etc.)

    Returns:
        Dict contendo elementos extraídos organizados por camadas ArchiMate
    """
    try:
        logger.info(f"Iniciando análise de user story para domínio: {domain}")

        # Validação básica
        if not story_text or len(story_text.strip()) < 10:
            raise ValueError("User story muito curta ou vazia")

        # Verificar se temos cliente configurado
        if not client:
            logger.warning("Cliente Vertex AI não disponível, usando análise avançada local")
            return _create_intelligent_analysis(story_text)

        try:
            # Preparar prompt
            prompt = ANALYSIS_PROMPTS.get(domain, ANALYSIS_PROMPTS["Banking"]).format(
                story_text=story_text,
                patterns=json.dumps(BANKING_PATTERNS, indent=2, ensure_ascii=False)
            )

            # Gerar análise usando o cliente
            response = client.models.generate_content(
                model=VERTEX_AI_MODEL,
                contents=prompt
            )

            # Processar resposta
            response_text = response.text

            # Procurar por JSON na resposta
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                # Se não encontrar JSON, criar estrutura inteligente
                analysis = _create_intelligent_analysis(story_text)

        except Exception as e:
            logger.warning(f"Erro ao usar Vertex AI: {str(e)}. Usando análise avançada local.")
            analysis = _create_intelligent_analysis(story_text)

        # Enriquecer com metadados
        analysis["story_id"] = f"story_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        analysis["timestamp"] = datetime.now().isoformat()
        analysis["domain"] = domain
        analysis["story_text"] = story_text
        analysis["success"] = True  # CRUCIAL: Indicar que a análise foi bem-sucedida

        # Validar e limpar análise
        analysis = _validate_and_clean_analysis(analysis)

        logger.info(f"Análise concluída: {analysis['story_id']}")
        return analysis

    except Exception as e:
        logger.error(f"Erro na análise da user story: {str(e)}")
        return {
            "error": str(e),
            "success": False,  # CRUCIAL: Indicar falha na análise
            "story_id": f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": datetime.now().isoformat(),
            "domain": domain
        }


def _create_intelligent_analysis(story_text: str) -> Dict[str, Any]:
    """
    Cria análise inteligente baseada em padrões e regras

    Args:
        story_text: Texto da user story

    Returns:
        Dict com estrutura de análise
    """
    logger.info("Executando análise inteligente local")

    story_lower = story_text.lower()

    # Estrutura base com cross-cutting concerns
    analysis = {
        "success": True,  # CRUCIAL: Indicar sucesso da análise local
        "business_layer": {
            "actors": [],
            "processes": [],
            "services": [],
            "objects": []
        },
        "application_layer": {
            "components": [],
            "services": [],
            "interfaces": [],
            "data_objects": []
        },
        "technology_layer": {
            "nodes": [],
            "infrastructure_services": [],
            "artifacts": []
        },
        "requirements": {
            "functional": [],
            "non_functional": [],
            "business_rules": []
        },
        "integration_points": [],
        "cross_cutting_concerns": {
            "security": [],
            "audit": [],
            "compliance": [],
            "monitoring": []
        }
    }

    # EXTRAÇÃO INTELIGENTE DE ELEMENTOS

    # 1. BUSINESS LAYER - Atores
    actor_patterns = [
        (r"como\s+([^,]+)", "actor principal"),
        (r"(?:cliente|usuário|user)\s+(?:pessoa\s+)?(?:física|jurídica|pf|pj)", "tipo cliente"),
        (r"(?:gerente|analista|operador|auditor|funcionário)", "funcionário banco"),
        (r"(?:fornecedor|parceiro|prestador)", "terceiro")
    ]

    for pattern, actor_type in actor_patterns:
        matches = re.findall(pattern, story_lower, re.IGNORECASE)
        for match in matches:
            actor = _normalize_actor_name(match if isinstance(match, str) else match[0])
            if actor and len(actor) > 2:
                analysis["business_layer"]["actors"].append(actor)

    # 2. BUSINESS LAYER - Processos
    process_keywords = {
        "transferir|transferência|enviar|pagamento|pagar": "Processamento de Pagamento",
        "abrir|abertura|criar|cadastrar|onboarding": "Onboarding/Cadastro",
        "autenticar|login|acessar|entrar": "Autenticação",
        "validar|verificar|conferir|checar": "Validação",
        "analisar|análise|avaliar|scoring": "Análise",
        "autorizar|aprovar|liberar": "Autorização",
        "notificar|avisar|informar": "Notificação",
        "gerar|emitir|criar": "Geração de Documento",
        "consultar|buscar|pesquisar": "Consulta",
        "auditar|monitorar|rastrear": "Auditoria"
    }

    for keywords, process in process_keywords.items():
        if re.search(keywords, story_lower):
            analysis["business_layer"]["processes"].append(process)

    # 3. APPLICATION LAYER - Componentes
    # REMOVIDO: Sistema sempre presente - todos os componentes devem ser extraídos da user story

    # Detectar componentes baseados APENAS na análise da user story - sem padrões específicos
    # Análise genérica de componentes será feita dinamicamente
    component_patterns = {
        r"(?:pix|pagamento\s+instantâneo|transferência\s+instantânea)": "Sistema PIX",
        r"(?:mobile|app|aplicativo)": "Mobile Banking",
        r"(?:internet\s+banking|web|portal)": "Internet Banking",
        r"(?:fraude|fraud|antifraude)": "Sistema Antifraude",
        r"(?:notificação|push|sms|email)": "Gateway de Notificações",
        r"(?:autenticação|token|biometria|2fa|mfa)": "Sistema de Autenticação",
        r"(?:crédito|score|análise\s+de\s+risco)": "Sistema de Análise de Crédito",
        r"(?:compliance|conformidade|regulatório)": "Sistema de Compliance",
        r"(?:auditoria|log|rastreamento|trilha)": "Sistema de Auditoria",
        r"(?:monitoramento|monitoring|observabilidade)": "Sistema de Monitoramento"
    }

    for pattern, component in component_patterns.items():
        if re.search(pattern, story_lower):
            analysis["application_layer"]["components"].append(component)

    # 4. TECHNOLOGY LAYER - Incluindo Kafka, Redis, HSM
    tech_patterns = {
        r"(?:java|spring|boot)": {"node": "Servidor de Aplicação Java", "artifact": "Microserviços Spring Boot"},
        r"(?:kafka|mensageria|eventos?|streaming)": {"service": "Apache Kafka", "node": "Kafka Cluster"},
        r"(?:redis|cache)": {"service": "Redis Cache", "node": "Redis Cluster"},
        r"(?:postgres|postgresql|banco\s+relacional)": {"node": "Database Server PostgreSQL"},
        r"(?:kubernetes|k8s|container|docker)": {"node": "Kubernetes Cluster", "service": "Container Orchestration"},
        r"(?:cloud|nuvem|aws|gcp|azure)": {"node": "Cloud Infrastructure"},
        r"(?:criptografia|hsm|hardware\s+security)": {"node": "Hardware Security Module", "service": "HSM Service"},
        r"(?:prometheus|grafana|elastic|monitoring)": {"service": "Sistema de Monitoramento"}
    }

    for pattern, tech_info in tech_patterns.items():
        if re.search(pattern, story_lower):
            if "node" in tech_info:
                analysis["technology_layer"]["nodes"].append(tech_info["node"])
            if "service" in tech_info:
                analysis["technology_layer"]["infrastructure_services"].append(tech_info["service"])
            if "artifact" in tech_info:
                analysis["technology_layer"]["artifacts"].append(tech_info["artifact"])

    # 5. INTEGRATION POINTS - Detecção inteligente
    integrations = []

    # Sistemas regulatórios
    if any(term in story_lower for term in ["pix", "pagamento instantâneo", "transferência instantânea"]):
        integrations.append({
            "system": "Sistema PIX (DICT/SPI)",
            "type": "regulatory",
            "protocol": "ISO 20022"
        })

    if any(term in story_lower for term in ["bacen", "banco central", "spb"]):
        integrations.append({
            "system": "BACEN",
            "type": "regulatory",
            "protocol": "Mensageria SPB"
        })

    if any(term in story_lower for term in ["crédito", "spc", "serasa", "bureau"]):
        integrations.append({
            "system": "Bureau de Crédito",
            "type": "external",
            "protocol": "API REST"
        })

    if any(term in story_lower for term in ["receita", "cpf", "cnpj"]):
        integrations.append({
            "system": "Receita Federal",
            "type": "regulatory",
            "protocol": "WebService SOAP"
        })

    analysis["integration_points"] = integrations

    # 6. CROSS-CUTTING CONCERNS
    # Security
    security_keywords = ["segurança", "criptografia", "autenticação", "token", "biometria",
                         "2fa", "mfa", "fraude", "hsm", "certificado"]
    for keyword in security_keywords:
        if keyword in story_lower:
            if "criptografia" in keyword or "hsm" in keyword:
                analysis["cross_cutting_concerns"]["security"].append("Criptografia de Dados")
            elif "autenticação" in keyword or "2fa" in keyword:
                analysis["cross_cutting_concerns"]["security"].append("Autenticação Multi-Fator")
            elif "fraude" in keyword:
                analysis["cross_cutting_concerns"]["security"].append("Detecção de Fraude")

    # Audit
    if any(term in story_lower for term in ["auditoria", "rastreamento", "log", "trilha"]):
        analysis["cross_cutting_concerns"]["audit"].append("Trilha de Auditoria Completa")
        analysis["cross_cutting_concerns"]["audit"].append("Log de Transações")

    # Compliance
    compliance_terms = {
        "lgpd": "Conformidade LGPD",
        "pci": "Conformidade PCI-DSS",
        "bacen": "Regulação BACEN",
        "compliance": "Compliance Regulatório"
    }

    for term, compliance in compliance_terms.items():
        if term in story_lower:
            analysis["cross_cutting_concerns"]["compliance"].append(compliance)

    # Monitoring
    if any(term in story_lower for term in ["monitorar", "alertas", "observabilidade"]):
        analysis["cross_cutting_concerns"]["monitoring"].append("Monitoramento em Tempo Real")
        analysis["cross_cutting_concerns"]["monitoring"].append("Alertas Automáticos")

    # 7. REQUIREMENTS - Extração inteligente
    # Funcionais
    if "pix" in story_lower:
        analysis["requirements"]["functional"].append("Realizar transferências PIX em tempo real")
    if "consultar" in story_lower:
        analysis["requirements"]["functional"].append("Consultar informações da conta")
    if "autenticar" in story_lower:
        analysis["requirements"]["functional"].append("Autenticar usuário com segurança")

    # Não-funcionais
    if "instantâne" in story_lower or "tempo real" in story_lower:
        analysis["requirements"]["non_functional"].append("Latência máxima de 3 segundos")
    if "disponibilidade" in story_lower or "24x7" in story_lower:
        analysis["requirements"]["non_functional"].append("Disponibilidade 99.9%")
    if "segurança" in story_lower:
        analysis["requirements"]["non_functional"].append("Criptografia AES-256")

    # Business rules
    if "limite" in story_lower:
        analysis["requirements"]["business_rules"].append("Limite diário de transferências PIX")
    if "horário" in story_lower:
        analysis["requirements"]["business_rules"].append("Restrições de horário para operações")

    # 8. ENRIQUECIMENTO FINAL
    # Garantir elementos mínimos
    if not analysis["business_layer"]["actors"]:
        analysis["business_layer"]["actors"] = ["Cliente", "Sistema Bancário"]

    if not analysis["business_layer"]["services"]:
        analysis["business_layer"]["services"] = ["Serviços Bancários Digitais"]

    if not analysis["application_layer"]["services"]:
        analysis["application_layer"]["services"] = ["API Gateway", "Service Bus"]

    if not analysis["technology_layer"]["nodes"]:
        analysis["technology_layer"]["nodes"] = ["Application Server", "Database Server"]

    if not analysis["technology_layer"]["infrastructure_services"]:
        analysis["technology_layer"]["infrastructure_services"] = ["Load Balancer", "Firewall"]

    # Se tem requisitos de segurança críticos, adicionar HSM
    if any("criptografia" in concern.lower() or "hsm" in concern.lower()
           for concern in analysis["cross_cutting_concerns"]["security"]):
        if "Hardware Security Module" not in analysis["technology_layer"]["nodes"]:
            analysis["technology_layer"]["nodes"].append("Hardware Security Module")
            analysis["technology_layer"]["infrastructure_services"].append("HSM Service")

    # Se tem auditoria, garantir que tem sistema de auditoria
    if analysis["cross_cutting_concerns"]["audit"] and "Sistema de Auditoria" not in analysis["application_layer"][
        "components"]:
        analysis["application_layer"]["components"].append("Sistema de Auditoria")

    # Remover duplicatas
    for layer in analysis:
        if isinstance(analysis[layer], dict):
            for key in analysis[layer]:
                if isinstance(analysis[layer][key], list):
                    analysis[layer][key] = list(dict.fromkeys(analysis[layer][key]))

    # Remover duplicatas em integration_points mantendo dicionários únicos
    seen = set()
    unique_integrations = []
    for integration in analysis["integration_points"]:
        key = f"{integration['system']}_{integration['type']}"
        if key not in seen:
            seen.add(key)
            unique_integrations.append(integration)
    analysis["integration_points"] = unique_integrations

    return analysis


def _normalize_actor_name(actor_text: str) -> str:
    """
    Normaliza nome de ator extraído
    """
    if not actor_text:
        return ""

    # Remover caracteres especiais e limpar
    actor = re.sub(r'[^\w\s]', '', actor_text).strip()

    # Capitalizar primeira letra de cada palavra
    actor = ' '.join(word.capitalize() for word in actor.split() if word)

    # Mapeamentos específicos
    mappings = {
        'Cliente': 'Cliente',
        'Usuario': 'Usuário',
        'User': 'Usuário',
        'Pessoa Fisica': 'Cliente PF',
        'Pessoa Juridica': 'Cliente PJ'
    }

    return mappings.get(actor, actor)


def _validate_and_clean_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida e limpa a análise gerada
    """
    # Estrutura padrão
    default_structure = {
        "business_layer": {"actors": [], "processes": [], "services": [], "objects": []},
        "application_layer": {"components": [], "services": [], "interfaces": [], "data_objects": []},
        "technology_layer": {"nodes": [], "infrastructure_services": [], "artifacts": []},
        "requirements": {"functional": [], "non_functional": [], "business_rules": []},
        "integration_points": [],
        "cross_cutting_concerns": {"security": [], "audit": [], "compliance": [], "monitoring": []}
    }

    # Garantir estrutura mínima
    for key, default_value in default_structure.items():
        if key not in analysis:
            analysis[key] = default_value
        elif isinstance(default_value, dict):
            for subkey, subdefault in default_value.items():
                if subkey not in analysis[key]:
                    analysis[key][subkey] = subdefault

    # Remover duplicatas em listas
    for layer_key in analysis:
        if isinstance(analysis[layer_key], dict):
            for sub_key in analysis[layer_key]:
                if isinstance(analysis[layer_key][sub_key], list):
                    analysis[layer_key][sub_key] = list(dict.fromkeys(analysis[layer_key][sub_key]))
        elif isinstance(analysis[layer_key], list):
            # Para integration_points que é uma lista de dicionários
            if layer_key == "integration_points":
                seen = set()
                unique_items = []
                for item in analysis[layer_key]:
                    if isinstance(item, dict):
                        key = item.get('system', str(item))
                        if key not in seen:
                            seen.add(key)
                            unique_items.append(item)
                analysis[layer_key] = unique_items
            else:
                analysis[layer_key] = list(dict.fromkeys(analysis[layer_key]))

    return analysis


def analyze_user_story_for_c4(user_story: str) -> Dict[str, Any]:
    """
    Analisa user story especificamente para geração de diagramas C4

    Args:
        user_story: Texto da história de usuário

    Returns:
        Dict com elementos organizados para diagramas C4
    """
    logger.info("Analisando user story para diagramas C4...")

    # Usar análise principal
    analysis = analyze_user_story(user_story, "Banking")

    # Determinar domínio baseado no conteúdo
    story_lower = user_story.lower()
    domain = _determine_domain(story_lower)

    # Gerar nome do sistema
    system_name = _extract_system_name(story_lower, domain)

    # Extrair atores (mapeamento do business_layer)
    actors = analysis.get("business_layer", {}).get("actors", [])
    if not actors:
        actors = _extract_actors_from_story(story_lower, domain)

    # Extrair sistemas externos das integration_points
    external_systems = [
        integration["system"] for integration in analysis.get("integration_points", [])
        if integration.get("type") in ["external", "regulatory"]
    ]

    if not external_systems:
        external_systems = _extract_external_systems_from_story(story_lower, domain)

    # Gerar containers baseado nos componentes de aplicação
    containers = _generate_containers_from_analysis(analysis, domain, story_lower)

    # Gerar componentes
    components = _generate_components_from_analysis(analysis, domain, story_lower)

    return {
        'system_name': system_name,
        'domain': domain,
        'actors': actors,
        'external_systems': external_systems,
        'containers': containers,
        'main_container': 'Business Logic Service',
        'components': components,
        'full_analysis': analysis  # Manter análise completa para referência
    }


def _determine_domain(story_lower: str) -> str:
    """Determina o domínio baseado no conteúdo da história"""
    domain_patterns = {
        'banking': ['banco', 'bancário', 'conta', 'transferência', 'pix', 'cartão', 'crédito', 'débito'],
        'ecommerce': ['loja', 'produto', 'carrinho', 'pagamento', 'pedido', 'venda'],
        'healthcare': ['paciente', 'médico', 'consulta', 'exame', 'prontuário', 'hospital'],
        'logistics': ['entrega', 'transporte', 'frete', 'rastreamento', 'logística']
    }

    for domain, patterns in domain_patterns.items():
        if any(pattern in story_lower for pattern in patterns):
            return domain
    return 'generic'


def _extract_system_name(story_lower: str, domain: str) -> str:
    """Extrai ou gera nome do sistema"""
    domain_names = {
        'banking': 'Sistema Bancário Digital',
        'ecommerce': 'Plataforma de E-commerce',
        'healthcare': 'Sistema de Gestão Hospitalar',
        'logistics': 'Sistema de Logística',
        'generic': 'Sistema Digital'
    }

    if 'pix' in story_lower:
        return 'Sistema de Pagamentos PIX'
    elif 'cartão' in story_lower and 'crédito' in story_lower:
        return 'Sistema de Cartão de Crédito'

    return domain_names.get(domain, 'Sistema Digital')


def _extract_actors_from_story(story_lower: str, domain: str) -> List[str]:
    """Extrai atores da história baseado no domínio"""
    domain_actors = {
        'banking': ['Cliente Bancário', 'Gerente de Conta', 'Operador'],
        'ecommerce': ['Cliente', 'Vendedor', 'Administrador'],
        'healthcare': ['Paciente', 'Médico', 'Enfermeiro'],
        'logistics': ['Cliente', 'Motorista', 'Operador Logístico'],
        'generic': ['Usuário', 'Administrador']
    }

    actors = domain_actors.get(domain, ['Usuário', 'Administrador'])

    # Adicionar atores específicos encontrados na história
    if 'cliente' in story_lower:
        actors.insert(0, 'Cliente')

    return list(set(actors))  # Remover duplicatas


def _extract_external_systems_from_story(story_lower: str, domain: str) -> List[str]:
    """Extrai sistemas externos baseado no domínio e história"""
    domain_externals = {
        'banking': ['Core Banking System', 'Banco Central', 'SPC/Serasa'],
        'ecommerce': ['Gateway de Pagamento', 'Sistema de Entrega', 'ERP'],
        'healthcare': ['Sistema do SUS', 'Laboratório Externo', 'Convênio'],
        'logistics': ['Transportadora', 'Correios', 'Sistema de Rastreamento'],
        'generic': ['Sistema Externo', 'API Externa']
    }

    externals = domain_externals.get(domain, ['Sistema Externo'])

    # Adicionar sistemas específicos do PIX
    if 'pix' in story_lower:
        externals.extend(['SPI - Sistema de Pagamentos Instantâneos', 'DICT'])

    return list(set(externals))


def _generate_containers_from_analysis(analysis: Dict[str, Any], domain: str, story_lower: str) -> List[Dict[str, Any]]:
    """Gera containers baseado na análise e domínio"""
    base_containers = [
        {
            'name': 'Mobile Application',
            'technology': 'React Native',
            'description': 'Aplicativo móvel para usuários finais'
        },
        {
            'name': 'Web Application',
            'technology': 'Angular',
            'description': 'Aplicação web responsiva'
        },
        {
            'name': 'API Gateway',
            'technology': 'Kong/Nginx',
            'description': 'Gateway de entrada para APIs'
        },
        {
            'name': 'Business Logic Service',
            'technology': 'Java Spring Boot',
            'description': 'Serviços de lógica de negócio principal'
        },
        {
            'name': 'Integration Service',
            'technology': 'Java Spring Boot',
            'description': 'Serviços de integração com sistemas externos'
        },
        {
            'name': 'Database',
            'technology': 'PostgreSQL',
            'description': 'Base de dados relacional principal'
        },
        {
            'name': 'Cache',
            'technology': 'Redis',
            'description': 'Cache distribuído para performance'
        }
    ]

    # Adicionar containers específicos do domínio
    if domain == 'banking' or 'pix' in story_lower:
        base_containers.extend([
            {
                'name': 'Authentication Service',
                'technology': 'OAuth 2.0',
                'description': 'Serviço de autenticação e autorização'
            },
            {
                'name': 'Transaction Processing Service',
                'technology': 'Java Spring Boot',
                'description': 'Processamento de transações financeiras'
            }
        ])

    # Adicionar containers baseados na análise
    app_components = analysis.get("application_layer", {}).get("components", [])
    for component in app_components:
        if 'auditoria' in component.lower():
            base_containers.append({
                'name': 'Audit Service',
                'technology': 'Java Spring Boot',
                'description': 'Serviço de auditoria e conformidade'
            })
        elif 'monitoramento' in component.lower():
            base_containers.append({
                'name': 'Monitoring Service',
                'technology': 'Prometheus/Grafana',
                'description': 'Serviço de monitoramento e observabilidade'
            })

    return base_containers


def _generate_components_from_analysis(analysis: Dict[str, Any], domain: str, story_lower: str) -> List[Dict[str, Any]]:
    """Gera componentes baseado na análise e domínio"""
    base_components = [
        {
            'name': 'Authentication Controller',
            'description': 'Controlador de autenticação',
            'depends_on': ['Authentication Service']
        },
        {
            'name': 'Authentication Service',
            'description': 'Serviço de autenticação',
            'depends_on': ['User Repository']
        },
        {
            'name': 'User Repository',
            'description': 'Repositório de usuários',
            'depends_on': []
        },
        {
            'name': 'Security Service',
            'description': 'Serviço de segurança',
            'depends_on': []
        }
    ]

    # Adicionar componentes específicos do domínio
    if domain == 'banking' or 'pix' in story_lower:
        base_components.extend([
            {
                'name': 'Transaction Controller',
                'description': 'Controlador de transações',
                'depends_on': ['Transaction Service']
            },
            {
                'name': 'Transaction Service',
                'description': 'Serviço de transações',
                'depends_on': ['Transaction Repository']
            },
            {
                'name': 'Transaction Repository',
                'description': 'Repositório de transações',
                'depends_on': []
            },
            {
                'name': 'PIX Integration Service',
                'description': 'Serviço de integração PIX',
                'depends_on': []
            }
        ])

    # Adicionar componentes baseados na análise de auditoria
    if analysis.get("cross_cutting_concerns", {}).get("audit"):
        base_components.extend([
            {
                'name': 'Audit Controller',
                'description': 'Controlador de auditoria',
                'depends_on': ['Audit Service']
            },
            {
                'name': 'Audit Service',
                'description': 'Serviço de auditoria',
                'depends_on': ['Audit Repository']
            },
            {
                'name': 'Audit Repository',
                'description': 'Repositório de trilhas de auditoria',
                'depends_on': []
            }
        ])

    return base_components


# Função de conveniência para backward compatibility
def generate_c4_analysis_from_user_story(user_story: str) -> Dict[str, str]:
    """
    Gera análise C4 a partir de user story - função de conveniência

    Args:
        user_story: Texto da história de usuário

    Returns:
        Dict com informações para geração de diagramas C4
    """
    return analyze_user_story_for_c4(user_story)
