"""
Metamodel Compliant C4 Generator
Gerador de diagramas C4 que segue rigorosamente o metamodelo BiZZdesign
"""

import logging
import os
import sys
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET

# Adicionar path do diretório atual para imports standalone
current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from ..metamodel_validator import BiZZdesignMetamodelValidator, ValidationSeverity

# Import do ID generator
try:
    from .id_generator import NCNameIDGenerator
except ImportError:
    try:
        from id_generator import NCNameIDGenerator  # type: ignore
    except ImportError:  # fallback mock
        class NCNameIDGenerator:  # type: ignore
            def __init__(self):
                self.counter = 0
            def generate_id(self, prefix=""):
                self.counter += 1
                return f"{prefix}_{self.counter}"
            def generate_ncname_id(self, base_name: str, readable_name: str = None):
                # Reusar generate_id simples
                return self.generate_id(base_name or 'id')

logger = logging.getLogger(__name__)


class C4LayerType(Enum):
    """Camadas do modelo C4 mapeadas para o metamodelo"""
    CONTEXT = "context"
    CONTAINER = "container"
    COMPONENT = "component"
    CODE = "code"


@dataclass
class MetamodelCompliantElement:
    """Elemento C4 que respeita o metamodelo"""
    identifier: str
    name: str
    element_type: str  # Tipo exato do metamodelo
    layer: C4LayerType
    documentation: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    position: Optional[Tuple[int, int]] = None

    def validate_against_metamodel(self, validator: BiZZdesignMetamodelValidator) -> bool:
        """Valida se o elemento est�� em conformidade com o metamodelo"""
        allowed_elements = validator.get_allowed_elements()
        return self.element_type in allowed_elements


@dataclass
class MetamodelCompliantRelationship:
    """Relacionamento C4 que respeita o metamodelo"""
    identifier: str
    source: str
    target: str
    relationship_type: str  # Tipo exato do metamodelo
    name: str = ""
    documentation: str = ""

    def validate_against_metamodel(self, validator: BiZZdesignMetamodelValidator,
                                 source_type: str, target_type: str) -> bool:
        """Valida se o relacionamento está em conformidade com o metamodelo"""
        allowed_relationships = validator.get_allowed_relationships(source_type, target_type)
        return any(rel[2] == self.relationship_type for rel in allowed_relationships)


class MetamodelCompliantC4Generator:
    """Gerador de diagramas C4 com conformidade estrita ao metamodelo"""

    def __init__(self, metamodel_path: str):
        self.validator = BiZZdesignMetamodelValidator(metamodel_path)
        self.elements: Dict[str, MetamodelCompliantElement] = {}
        self.relationships: List[MetamodelCompliantRelationship] = []
        self.validation_results = []
        self.id_generator = NCNameIDGenerator()  # Add ID generator for XML compliance
        # Layout do template SDLC 1.xml (coordenadas exatas)
        self.template_layout: Dict[str, Any] = {
            'header': {
                'title': {'x': 127, 'y': 47, 'w': 707, 'h': 40, 'text': 'Plataforma e Produtos de Dados', 'size': 24, 'style': 'bold'},
                'subtitle': {'x': 127, 'y': 87, 'w': 700, 'h': 33, 'text': 'Visão de container - Ingestões, Transformações, Experimentações, Análises e Visualização de Dados do SDLC', 'size': 16, 'style': 'plain'}
            },
            'layers': {
                'channels': {
                    'x': 67, 'y': 193, 'w': 200, 'h': 627, 'title': 'CHANNELS',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'elements_per_row': 1, 'element_width': 180, 'element_height': 50,
                    'vertical_spacing': 15, 'horizontal_padding': 10, 'vertical_padding': 40
                },
                'gateway_inbound': {
                    'x': 273, 'y': 193, 'w': 200, 'h': 627, 'title': 'GATEWAY INBOUND',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'elements_per_row': 1, 'element_width': 180, 'element_height': 50,
                    'vertical_spacing': 15, 'horizontal_padding': 10, 'vertical_padding': 40
                },
                'execution_logic': {
                    'x': 480, 'y': 193, 'w': 533, 'h': 500, 'title': 'EXECUTION LOGIC',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'elements_per_row': 2, 'element_width': 250, 'element_height': 60,
                    'vertical_spacing': 15, 'horizontal_spacing': 20,
                    'horizontal_padding': 15, 'vertical_padding': 40
                },
                'gateway_outbound': {
                    'x': 1020, 'y': 193, 'w': 173, 'h': 627, 'title': 'GATEWAY OUTBOUND',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'elements_per_row': 1, 'element_width': 153, 'element_height': 50,
                    'vertical_spacing': 15, 'horizontal_padding': 10, 'vertical_padding': 40
                },
                'external_integration': {
                    'x': 1200, 'y': 193, 'w': 200, 'h': 627, 'title': 'EXTERNAL INTEGRATION LAYER',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'elements_per_row': 1, 'element_width': 180, 'element_height': 50,
                    'vertical_spacing': 15, 'horizontal_padding': 10, 'vertical_padding': 40
                },
                'data_management': {
                    'x': 480, 'y': 700, 'w': 533, 'h': 120, 'title': 'DATA MANAGEMENT',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'elements_per_row': 2, 'element_width': 250, 'element_height': 40,
                    'vertical_spacing': 10, 'horizontal_spacing': 20,
                    'horizontal_padding': 15, 'vertical_padding': 35
                },
                'etapas': {
                    'x': 1407, 'y': 193, 'w': 260, 'h': 627, 'title': 'Etapas',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'note_text': 'Regras Aplicadas:   Observações:',
                    'note_x': 1420, 'note_y': 227, 'note_w': 233, 'note_h': 220
                }
            }
        }
        # Mapa elementId -> visual node id para conexões
        self._visual_node_by_element: Dict[str, str] = {}

        # Mapeamento de tipos C4 para tipos do metamodelo
        self.c4_to_metamodel_mapping = {
            # Context Layer
            'person': 'BusinessActor',
            'external_system': 'ApplicationCollaboration',
            'system': 'ApplicationCollaboration',

            # Container Layer
            'container': 'ApplicationComponent',
            'database': 'DataObject',
            'web_application': 'ApplicationComponent',
            'mobile_app': 'ApplicationComponent',
            'api': 'ApplicationComponent',
            'service': 'ApplicationComponent',

            # Component Layer
            'component': 'ApplicationComponent',
            'service_component': 'ApplicationComponent',
            'repository': 'DataObject',
            'controller': 'ApplicationComponent',

            # Infrastructure
            'infrastructure': 'Device',
            'deployment_node': 'Node',
            'technology_service': 'TechnologyService'
        }

        # Mapeamento CORRIGIDO de relacionamentos C4 para metamodelo - APENAS TIPOS PERMITIDOS
        self.relationship_mapping = {
            'uses': 'Serving',           # ✅ Permitido
            'contains': 'Aggregation',   # ✅ Permitido - mudado de Composition para Aggregation
            'includes': 'Aggregation',   # ✅ Permitido
            'accesses': 'Access',        # ✅ Permitido
            'calls': 'Serving',          # ✅ Permitido
            'triggers': 'Triggering',    # ✅ Permitido
            'serves': 'Serving',         # ✅ Permitido
            'composes': 'Composition',   # ✅ Permitido
            'associates': 'Association'  # ✅ Permitido
            # ❌ REMOVIDOS: 'extends': 'Specialization', 'flows_to': 'Flow', 'realizes': 'Realization'
        }

        # Lista de relacionamentos ESTRITAMENTE permitidos pelo metamodelo
        self.allowed_relationships = {
            'Association',    # Associação
            'Serving',        # Servidão
            'Aggregation',    # Agregação
            'Composition',    # Composição
            'Access',         # Acesso
            'Triggering'      # Disparo
        }
        # Novo: configuração para incluir atores em diagramas de container (desativado por padrão)
        self.include_actors_in_container_diagram: bool = False

    def generate_context_diagram(self, user_story: str, system_name: str) -> str:
        """Gera diagrama de contexto C4 em conformidade com o metamodelo"""
        logger.info(f"Gerando diagrama de contexto para: {system_name}")

        # Resetar elementos e relacionamentos
        self.elements.clear()
        self.relationships.clear()

        # Analisar história do usuário
        analysis = self._analyze_user_story(user_story)

        # Criar sistema principal
        system_id = self._add_compliant_element(
            name=system_name,
            element_type='ApplicationCollaboration',
            layer=C4LayerType.CONTEXT,
            documentation=f"Sistema principal: {system_name}"
        )

        # Adicionar atores de negócio
        for actor in analysis.get('actors', []):
            actor_id = self._add_compliant_element(
                name=actor,
                element_type='BusinessActor',
                layer=C4LayerType.CONTEXT,
                documentation=f"Ator de negócio: {actor}"
            )

            # Relacionamento: Ator usa Sistema
            self._add_compliant_relationship(
                source_id=actor_id,
                target_id=system_id,
                relationship_type='Association',
                name="usa"
            )

        # Adicionar sistemas externos
        for ext_system in analysis.get('external_systems', []):
            ext_id = self._add_compliant_element(
                name=ext_system,
                element_type='ApplicationCollaboration',
                layer=C4LayerType.CONTEXT,
                documentation=f"Sistema externo: {ext_system}"
            )

            # Relacionamento: Sistema usa Sistema Externo
            self._add_compliant_relationship(
                source_id=system_id,
                target_id=ext_id,
                relationship_type='Serving',
                name="integra com"
            )

        # Validar diagrama
        diagram_xml = self._generate_archimate_xml()
        self.validation_results = self.validator.validate_c4_diagram(diagram_xml)

        # Se há erros críticos, corrigi-los
        if any(r.severity == ValidationSeverity.ERROR for r in self.validation_results):
            self._fix_critical_errors()
            diagram_xml = self._generate_archimate_xml()

        return diagram_xml

    def generate_container_diagram(self, user_story: str, system_name: str) -> str:
        """Gera diagrama de containers C4 em conformidade ESTRITA com o metamodelo"""
        logger.info(f"Gerando diagrama de containers para: {system_name}")

        # Resetar elementos e relacionamentos
        self.elements.clear()
        self.relationships.clear()

        # Analisar história do usuário
        analysis = self._analyze_user_story(user_story)

        # 1. Criar sistema principal como ApplicationCollaboration
        system_id = self._add_compliant_element(
            name=system_name,
            element_type='ApplicationCollaboration',
            layer=C4LayerType.CONTAINER,
            documentation=f"Sistema aplicativo principal: {system_name}"
        )

        # 2. Adicionar componentes principais baseados na análise
        components = []

        # Identificar componentes da user story
        api_id = None  # Inicializar variável
        if 'api' in user_story.lower() or 'serviço' in user_story.lower():
            api_id = self._add_compliant_element(
                name=f"API {system_name}",
                element_type='ApplicationComponent',
                layer=C4LayerType.CONTAINER,
                documentation=f"API REST do sistema {system_name}"
            )
            components.append(api_id)

            # Sistema contém API
            self._add_compliant_relationship(
                source_id=system_id,
                target_id=api_id,
                relationship_type='Aggregation',
                name='contém'
            )

        if 'banco' in user_story.lower() or 'dados' in user_story.lower() or 'repositório' in user_story.lower():
            db_id = self._add_compliant_element(
                name=f"Repositório de Dados {system_name}",
                element_type='DataObject',
                layer=C4LayerType.CONTAINER,
                documentation=f"Repositório principal de dados do sistema {system_name}"
            )
            components.append(db_id)

            # Sistema contém repositório
            self._add_compliant_relationship(
                source_id=system_id,
                target_id=db_id,
                relationship_type='Aggregation',
                name='contém'
            )

            # Se houver API, ela acessa o banco
            if api_id is not None:
                self._add_compliant_relationship(
                    source_id=api_id,
                    target_id=db_id,
                    relationship_type='Access',
                    name='acessa'
                )

        if 'interface' in user_story.lower() or 'frontend' in user_story.lower() or 'web' in user_story.lower():
            ui_id = self._add_compliant_element(
                name=f"Interface Web {system_name}",
                element_type='ApplicationComponent',
                layer=C4LayerType.CONTAINER,
                documentation=f"Interface web do sistema {system_name}"
            )
            components.append(ui_id)

            # Sistema contém interface
            self._add_compliant_relationship(
                source_id=system_id,
                target_id=ui_id,
                relationship_type='Aggregation',
                name='contém'
            )

            # Interface usa API (se existir)
            if api_id is not None:
                self._add_compliant_relationship(
                    source_id=ui_id,
                    target_id=api_id,
                    relationship_type='Serving',
                    name='usa'
                )

        # 3. Adicionar atores se mencionados
        for actor in analysis.get('actors', []):
            actor_id = self._add_compliant_element(
                name=actor,
                element_type='BusinessActor',
                layer=C4LayerType.CONTAINER,
                documentation=f"Ator de negócio: {actor}"
            )

            # Ator usa o sistema
            self._add_compliant_relationship(
                source_id=actor_id,
                target_id=system_id,
                relationship_type='Association',
                name='utiliza'
            )

        # 4. Adicionar sistemas externos se mencionados
        external_systems = analysis.get('external_systems', [])
        for ext_system in external_systems:
            ext_id = self._add_compliant_element(
                name=ext_system,
                element_type='ApplicationCollaboration',
                layer=C4LayerType.CONTAINER,
                documentation=f"Sistema externo: {ext_system}"
            )

            # Sistema principal se comunica com sistema externo
            self._add_compliant_relationship(
                source_id=system_id,
                target_id=ext_id,
                relationship_type='Association',
                name='integra-se com'
            )

        # 5. Garantir estrutura mínima se não há componentes suficientes
        if len(components) < 2:
            # Adicionar componente de aplicação básico
            app_id = self._add_compliant_element(
                name=f"Aplicação {system_name}",
                element_type='ApplicationComponent',
                layer=C4LayerType.CONTAINER,
                documentation=f"Componente principal da aplicação {system_name}"
            )

            self._add_compliant_relationship(
                source_id=system_id,
                target_id=app_id,
                relationship_type='Aggregation',
                name='contém'
            )

            # Adicionar repositório básico se não existe
            if not any(self.elements[elem_id].element_type == 'DataObject' for elem_id in self.elements):
                data_id = self._add_compliant_element(
                    name=f"Dados {system_name}",
                    element_type='DataObject',
                    layer=C4LayerType.CONTAINER,
                    documentation=f"Repositório de dados do sistema {system_name}"
                )

                self._add_compliant_relationship(
                    source_id=app_id,
                    target_id=data_id,
                    relationship_type='Access',
                    name='acessa'
                )

        # Gerar XML final
        return self._generate_archimate_xml()

    def generate_component_diagram(self, user_story: str, container_name: str) -> str:
        """Gera diagrama de componente C4 em conformidade com o metamodelo"""
        logger.info(f"Gerando diagrama de componente para: {container_name}")

        # Resetar elementos e relacionamentos
        self.elements.clear()
        self.relationships.clear()

        # Analisar história do usuário
        analysis = self._analyze_user_story(user_story)

        # Criar container principal
        container_id = self._add_compliant_element(
            name=container_name,
            element_type='ApplicationComponent',
            layer=C4LayerType.COMPONENT,
            documentation=f"Container principal: {container_name}"
        )

        # Identificar componentes baseados no metamodelo
        components = self._identify_components(analysis)

        for component in components:
            comp_id = self._add_compliant_element(
                name=component['name'],
                element_type='ApplicationComponent',
                layer=C4LayerType.COMPONENT,
                documentation=component['description']
            )

            # Relacionamento: Container contém Componente
            self._add_compliant_relationship(
                source_id=container_id,
                target_id=comp_id,
                relationship_type='Composition',
                name="composto por"
            )

        # Validar e corrigir
        diagram_xml = self._generate_archimate_xml()
        self.validation_results = self.validator.validate_c4_diagram(diagram_xml)

        if any(r.severity == ValidationSeverity.ERROR for r in self.validation_results):
            self._fix_critical_errors()
            diagram_xml = self._generate_archimate_xml()

        return diagram_xml

    def _add_compliant_element(self, name: str, element_type: str, layer: C4LayerType,
                             documentation: str = "") -> str:
        """Adiciona elemento garantindo conformidade com o metamodelo"""

        # Verificar se o tipo é permitido no metamodelo
        allowed_elements = self.validator.get_allowed_elements()
        if element_type not in allowed_elements:
            logger.warning(f"Tipo de elemento '{element_type}' não permitido. Usando tipo padrão.")
            element_type = 'ApplicationComponent'  # Fallback para tipo válido

        # Aplicar convenções de nomenclatura do Banco BV
        name = self._apply_bv_naming_conventions(name, element_type)

        # CORRIGIDO: Usar ID generator para garantir NCName válido sempre
        element_id = self.id_generator.generate_ncname_id('element', readable_name=name)

        element = MetamodelCompliantElement(
            identifier=element_id,
            name=name,
            element_type=element_type,
            layer=layer,
            documentation=documentation
        )

        self.elements[element_id] = element
        return element_id

    def _add_compliant_relationship(self, source_id: str, target_id: str, relationship_type: str,
                                  name: str = "") -> str:
        """Adiciona relacionamento garantindo conformidade com o metamodelo"""

        # Verificar se o relacionamento é permitido
        source_element = self.elements.get(source_id)
        target_element = self.elements.get(target_id)

        if source_element and target_element:
            allowed_rels = self.validator.get_allowed_relationships(
                source_element.element_type,
                target_element.element_type
            )

            # Se o tipo não é permitido, usar um tipo válido
            if not any(rel[2] == relationship_type for rel in allowed_rels):
                if allowed_rels:
                    relationship_type = allowed_rels[0][2]  # Usar primeiro tipo válido
                    logger.warning(f"Relacionamento ajustado para tipo permitido: {relationship_type}")
                else:
                    logger.warning(f"Nenhum relacionamento permitido entre {source_element.element_type} e {target_element.element_type}")
                    return ""

        # CORRIGIDO: Usar ID generator para garantir NCName válido sempre
        rel_id = self.id_generator.generate_ncname_id('relationship', readable_name=name or relationship_type)

        relationship = MetamodelCompliantRelationship(
            identifier=rel_id,
            source=source_id,
            target=target_id,
            relationship_type=relationship_type,
            name=name
        )

        self.relationships.append(relationship)
        return rel_id

    def _apply_bv_naming_conventions(self, name: str, element_type: str) -> str:
        """Aplica convenções de nomenclatura do Banco BV"""
        naming_conventions = self.validator.naming_conventions

        # Se já segue a convenção, manter
        if element_type in naming_conventions:
            expected_pattern = naming_conventions[element_type]

            # Adicionar prefixos apropriados se necessário
            if element_type == 'ApplicationCollaboration' and 'sistema' not in name.lower():
                name = f"Sistema {name}"
            elif element_type == 'ApplicationComponent' and 'componente' not in name.lower():
                name = f"Componente {name}"
            elif element_type == 'DataObject' and 'repositório' not in name.lower():
                name = f"Repositório {name}"
            elif element_type == 'BusinessActor' and not any(keyword in name.lower() for keyword in ['usuário', 'cliente', 'ator']):
                name = f"Ator {name}"

        return name

    def _fix_critical_errors(self):
        """Corrige erros críticos de conformidade - VERSÃO APRIMORADA"""
        corrected_count = 0

        for result in self.validation_results:
            if result.severity == ValidationSeverity.ERROR:
                logger.warning(f"Corrigindo erro crítico: {result.message}")

                # Correção 1: Relacionamentos não permitidos
                if "não permitido no metamodelo" in result.message:
                    self._fix_invalid_relationships()
                    corrected_count += 1

                # Correção 2: Elementos com tipos inválidos
                if result.element_id and result.element_id in self.elements:
                    element = self.elements[result.element_id]
                    allowed_elements = self.validator.get_allowed_elements()
                    if element.element_type not in allowed_elements:
                        # Usar tipo mais apropriado baseado no nome
                        element.element_type = self._get_best_element_type(element.name)
                        logger.info(f"Elemento {result.element_id} corrigido para tipo {element.element_type}")
                        corrected_count += 1

        if corrected_count > 0:
            logger.info(f"✅ Corrigidos {corrected_count} erros críticos de conformidade ao metamodelo")

    def _fix_invalid_relationships(self):
        """Corrige relacionamentos que não são permitidos pelo metamodelo"""
        fixed_relationships = []

        for rel in self.relationships:
            source_element = self.elements.get(rel.source)
            target_element = self.elements.get(rel.target)

            if source_element and target_element:
                # Verificar se o relacionamento atual é válido
                allowed_rels = self.validator.get_allowed_relationships(
                    source_element.element_type,
                    target_element.element_type
                )

                # Se não é válido, substituir por um válido
                if not any(r[2] == rel.relationship_type for r in allowed_rels):
                    if allowed_rels:
                        old_type = rel.relationship_type
                        rel.relationship_type = allowed_rels[0][2]  # Usar primeiro válido
                        logger.info(f"Relacionamento corrigido: {old_type} → {rel.relationship_type}")
                    else:
                        # Se não há relacionamentos válidos, usar Association como padrão
                        rel.relationship_type = 'Association'
                        logger.info(f"Relacionamento padronizado para Association")

            fixed_relationships.append(rel)

        self.relationships = fixed_relationships

    def _get_best_element_type(self, name: str) -> str:
        """Determina o melhor tipo de elemento baseado no nome"""
        name_lower = name.lower()

        # Mapear baseado em palavras-chave no nome
        if any(keyword in name_lower for keyword in ['sistema', 'aplicativo', 'plataforma']):
            return 'ApplicationCollaboration'
        elif any(keyword in name_lower for keyword in ['componente', 'módulo', 'serviço', 'api', 'interface']):
            return 'ApplicationComponent'
        elif any(keyword in name_lower for keyword in ['repositório', 'dados', 'base', 'banco']):
            return 'DataObject'
        elif any(keyword in name_lower for keyword in ['usuário', 'cliente', 'ator', 'operador']):
            return 'BusinessActor'
        else:
            # Padrão seguro
            return 'ApplicationComponent'

    def _extract_system_name(self, user_story: str) -> str:
        """Extrai nome do sistema da user story com análise mais inteligente"""

        # Análise mais profunda para extrair nome significativo
        story_lower = user_story.lower()
        words = user_story.split()

        # Procurar por domínios específicos de negócio
        banking_keywords = {
            'pix': 'Sistema de Pagamentos Instantâneos PIX',
            'pagamento': 'Sistema de Pagamentos Bancários',
            'conta': 'Sistema de Gestão de Contas',
            'cartão': 'Sistema de Cartões de Crédito/Débito',
            'empréstimo': 'Sistema de Operações de Crédito',
            'investimento': 'Sistema de Investimentos',
            'transação': 'Sistema de Processamento Transacional',
            'cliente': 'Sistema de Relacionamento com Cliente',
            'dados': 'Sistema de Gestão de Dados Corporativos',
            'notificação': 'Sistema de Notificações Multicanal',
            'auditoria': 'Sistema de Auditoria e Compliance',
            'fraude': 'Sistema de Prevenção à Fraude',
            'relatório': 'Sistema de Relatórios Gerenciais',
            'dashboard': 'Sistema de Business Intelligence'
        }

        # Verificar se há palavras-chave específicas do domínio bancário
        for keyword, system_name in banking_keywords.items():
            if keyword in story_lower:
                return system_name

        # Se não encontrou domínio específico, tentar extrair contexto
        if 'sistema' in story_lower:
            # Procurar padrão "sistema de X" ou "sistema X"
            import re
            pattern = r'sistema\s+(?:de\s+)?(\w+(?:\s+\w+)?)'
            match = re.search(pattern, story_lower)
            if match:
                extracted = match.group(1).title()
                return f"Sistema de {extracted}"

        # Análise por verbos de ação para inferir propósito
        action_keywords = {
            'notificar': 'Sistema de Notificações',
            'processar': 'Sistema de Processamento',
            'validar': 'Sistema de Validação',
            'autorizar': 'Sistema de Autorizaç��o',
            'monitorar': 'Sistema de Monitoramento',
            'analisar': 'Sistema de Análise',
            'gerar': 'Sistema de Geração',
            'calcular': 'Sistema de Cálculos'
        }

        for verb, system_name in action_keywords.items():
            if verb in story_lower:
                return f"{system_name} Bancário"

        # Fallback inteligente baseado em contexto financeiro
        if any(word in story_lower for word in ['banco', 'financeiro', 'monetário']):
            return "Sistema Bancário Corporativo"

        # Último fallback
        return "Sistema de Negócio Especializado"

    def _analyze_user_story(self, user_story: str) -> Dict[str, Any]:
        """Analisa história do usuário para extrair elementos arquiteturais - VERSÃO MELHORADA"""
        analysis = {
            'actors': [],
            'external_systems': [],
            'containers': [],
            'components': [],
            'data_objects': [],
            'business_context': '',
            'technology_stack': []
        }

        # Análise mais sofisticada baseada em NLP simples
        words = user_story.lower().split()
        sentences = user_story.lower().split('.')

        # Extrair contexto de negócio
        business_context = self._extract_business_context(user_story)
        analysis['business_context'] = business_context

        # Identificar atores com base no contexto de negócio
        banking_actors = {
            'cliente': 'Cliente Bancário',
            'usuário': 'Usuário do Sistema',
            'operador': 'Operador Bancário',
            'administrador': 'Administrador do Sistema',
            'gerente': 'Gerente de Conta',
            'analista': 'Analista de Negócio',
            'funcionário': 'Funcionário do Banco',
            'auditor': 'Auditor de Compliance',
            'desenvolvedor': 'Desenvolvedor do Sistema'
        }

        for keyword, actor_name in banking_actors.items():
            if keyword in words:
                if actor_name not in analysis['actors']:
                    analysis['actors'].append(actor_name)

        # Se não identificou atores específicos, usar contexto
        if not analysis['actors']:
            if business_context == 'banking':
                analysis['actors'].append('Cliente Bancário')
            else:
                analysis['actors'].append('Usuário do Sistema')

        # Identificar sistemas externos baseados em contexto bancário
        external_systems_patterns = {
            'bacen': 'Sistema do Banco Central (BACEN)',
            'spc': 'Sistema de Proteção ao Crédito (SPC)',
            'serasa': 'Sistema Serasa de Análise de Crédito',
            'pix': 'Sistema PIX do Banco Central',
            'ted': 'Sistema de Transferência Eletrônica',
            'boleto': 'Sistema de Boletos Bancários',
            'cartão': 'Sistema de Adquirência de Cartões',
            'api externa': 'Sistema de APIs Externas',
            'terceiro': 'Sistema de Terceiros',
            'integração': 'Sistema de Integração Externa'
        }

        for pattern, system_name in external_systems_patterns.items():
            if pattern in user_story.lower():
                if system_name not in analysis['external_systems']:
                    analysis['external_systems'].append(system_name)

        # Heurística dinâmica: se houver indícios de crédito/antifraude/validação, inferir bureaus de crédito
        credit_indicators = ['crédito', 'credito', 'score', 'buro', 'bureau', 'validação', 'validacao', 'fraude', 'antifraude', 'risco']
        if any(tok in user_story.lower() for tok in credit_indicators):
            if 'Sistema de Proteção ao Crédito (SPC)' not in analysis['external_systems']:
                analysis['external_systems'].append('Sistema de Proteção ao Crédito (SPC)')
            if 'Sistema Serasa de Análise de Crédito' not in analysis['external_systems']:
                analysis['external_systems'].append('Sistema Serasa de Análise de Crédito')

        # Identificar containers com base em padrões arquiteturais
        containers_identified = self._identify_smart_containers(user_story, business_context)
        analysis['containers'] = containers_identified

        # Identificar stack tecnológico
        analysis['technology_stack'] = self._identify_technology_stack(user_story)

        return analysis

    def _identify_technology_stack(self, user_story: str) -> List[str]:
        """Identifica stack tecnológico baseado na user story"""
        story_lower = user_story.lower()
        tech_stack = []

        # Frontend technologies
        if any(word in story_lower for word in ['web', 'portal', 'site', 'interface']):
            tech_stack.extend(['Angular', 'React', 'TypeScript'])

        if any(word in story_lower for word in ['mobile', 'app', 'aplicativo']):
            tech_stack.extend(['React Native', 'Flutter'])

        # Backend technologies
        if any(word in story_lower for word in ['api', 'serviço', 'microserviço', 'backend']):
            tech_stack.extend(['Spring Boot', 'Java', 'REST API'])

        # Banking specific technologies
        if any(word in story_lower for word in ['banco', 'financeiro', 'pagamento']):
            tech_stack.extend(['Spring Security', 'OAuth2', 'JWT'])

        # Integration technologies
        if any(word in story_lower for word in ['integração', 'notificação', 'mensagem']):
            tech_stack.extend(['Apache Kafka', 'RabbitMQ'])

        # Database technologies
        if any(word in story_lower for word in ['dados', 'banco de dados', 'persistir']):
            tech_stack.extend(['PostgreSQL', 'Redis', 'MongoDB'])

        # Analytics and ML
        if any(word in story_lower for word in ['análise', 'inteligência', 'machine learning', 'ai']):
            tech_stack.extend(['Python', 'TensorFlow', 'Apache Spark'])

        # Cloud technologies
        if any(word in story_lower for word in ['nuvem', 'cloud', 'kubernetes']):
            tech_stack.extend(['Kubernetes', 'Docker', 'Google Cloud'])

        # Monitoring and observability
        if any(word in story_lower for word in ['monitoramento', 'log', 'auditoria']):
            tech_stack.extend(['ELK Stack', 'Prometheus', 'Grafana'])

        # Security
        if any(word in story_lower for word in ['segurança', 'autenticação', 'autorização']):
            tech_stack.extend(['Spring Security', 'Keycloak', 'OAuth2'])

        # Remove duplicates and return
        return list(set(tech_stack)) if tech_stack else ['Spring Boot', 'Java', 'PostgreSQL']

    def _extract_business_context(self, user_story: str) -> str:
        """Extrai contexto de negócio da user story"""
        story_lower = user_story.lower()

        # Contextos específicos do domínio bancário
        banking_indicators = [
            'banco', 'financeiro', 'pagamento', 'conta', 'cartão', 'pix',
            'empréstimo', 'crédito', 'débito', 'transferência', 'saldo',
            'investimento', 'aplicação', 'resgate', 'juros', 'tarifa'
        ]

        if any(indicator in story_lower for indicator in banking_indicators):
            return 'banking'

        # Outros contextos
        if any(word in story_lower for word in ['e-commerce', 'loja', 'venda']):
            return 'ecommerce'

        if any(word in story_lower for word in ['saúde', 'médico', 'paciente']):
            return 'healthcare'

        return 'general'

    def _identify_smart_containers(self, user_story: str, business_context: str) -> List[Dict[str, str]]:
        """Identifica containers de forma inteligente baseada no contexto"""
        containers = []
        story_lower = user_story.lower()

        # Containers específicos para contexto bancário
        if business_context == 'banking':
            # Interface de cliente sempre presente
            containers.append({
                'name': 'Componente Portal Internet Banking BV',
                'type': 'ApplicationComponent',
                'description': 'Portal web institucional para acesso aos serviços bancários',
                'technology': 'Angular/React',
                'layer': 'presentation'
            })

            # Mobile banking
            containers.append({
                'name': 'Componente Aplicativo Mobile Banking BV',
                'type': 'ApplicationComponent',
                'description': 'Aplicativo móvel para operações bancárias dos clientes',
                'technology': 'React Native',
                'layer': 'presentation'
            })

            # Gateway de APIs
            containers.append({
                'name': 'Componente Gateway de APIs Bancárias',
                'type': 'ApplicationComponent',
                'description': 'Gateway centralizado para orquestração e roteamento de APIs',
                'technology': 'Spring Cloud Gateway',
                'layer': 'integration'
            })

            # Serviços de negócio baseados na user story
            notif_signals = ['notificação', 'notificações', 'notificar', 'avisar', 'alerta', 'email', 'e-mail', 'push', 'sms', 'comprovante', 'confirma']
            if any(word in story_lower for word in notif_signals):
                containers.append({
                    'name': 'Componente Serviço de Notificações Multicanal BV',
                    'type': 'ApplicationComponent',
                    'description': 'Serviço responsável pelo envio de notificações por múltiplos canais',
                    'technology': 'Spring Boot + Apache Kafka',
                    'layer': 'business'
                })

            if any(word in story_lower for word in ['validar', 'validação', 'validacao', 'verificar', 'compliance']):
                containers.append({
                    'name': 'Componente Serviço de Validação e Compliance BV',
                    'type': 'ApplicationComponent',
                    'description': 'Serviço de validação de dados e regras de compliance bancário',
                    'technology': 'Spring Boot + Drools',
                    'layer': 'business'
                })

            if any(word in story_lower for word in ['auditoria', 'auditar', 'log', 'rastro', 'monitoramento']):
                containers.append({
                    'name': 'Componente Serviço de Auditoria e Monitoramento BV',
                    'type': 'ApplicationComponent',
                    'description': 'Serviço de auditoria e monitoramento de operações bancárias',
                    'technology': 'Spring Boot + ELK Stack',
                    'layer': 'business'
                })

            if any(word in story_lower for word in ['fraude', 'antifraude', 'suspeita', 'risco']):
                containers.append({
                    'name': 'Componente Motor de Análise Antifraude BV',
                    'type': 'ApplicationComponent',
                    'description': 'Motor de inteligência artificial para detecção de fraudes',
                    'technology': 'Python + TensorFlow + Kafka',
                    'layer': 'business'
                })

            # Fallback dinâmico: se não houve sinal claro mas há canais e processamento, incluir notificações
            has_notifications = any('Notificações' in c['name'] for c in containers)
            if not has_notifications and any(word in story_lower for word in ['auditoria', 'monitoramento', 'evento', 'webhook']):
                containers.append({
                    'name': 'Componente Serviço de Notificações Multicanal BV',
                    'type': 'ApplicationComponent',
                    'description': 'Serviço responsável pelo envio de notificações por múltiplos canais',
                    'technology': 'Spring Boot + Apache Kafka',
                    'layer': 'business'
                })

            # Dados sempre presentes
            containers.append({
                'name': 'Repositório Base de Dados Transacional BV',
                'type': 'DataObject',
                'description': 'Base de dados principal para transações bancárias',
                'technology': 'PostgreSQL Cluster',
                'layer': 'data'
            })

            containers.append({
                'name': 'Repositório Cache Distribuído de Performance BV',
                'type': 'DataObject',
                'description': 'Cache distribuído para otimização de performance',
                'technology': 'Redis Cluster',
                'layer': 'data'
            })

            containers.append({
                'name': 'Repositório Data Lake Corporativo BV',
                'type': 'DataObject',
                'description': 'Repositório centralizado de dados para analytics e BI',
                'technology': 'Apache Hadoop + Spark',
                'layer': 'data'
            })

        return containers

    def _identify_containers(self, analysis: Dict[str, Any]) -> List[Dict[str, str]]:
        """Identifica containers baseados na análise - VERSÃO MELHORADA"""
        containers = analysis.get('containers', [])

        # Se já temos containers da análise inteligente, usar eles
        if containers:
            return containers

        # Fallback para containers básicos bem nomeados conforme padrões BV
        business_context = analysis.get('business_context', 'general')

        if business_context == 'banking':
            containers = [
                {
                    'name': 'Portal Corporativo Banco BV',
                    'type': 'ApplicationComponent',
                    'description': 'Portal web corporativo para acesso aos serviços bancários institucionais',
                    'technology': 'Angular 15 + TypeScript'
                },
                {
                    'name': 'Aplicativo Mobile Banking BV',
                    'type': 'ApplicationComponent',
                    'description': 'Aplicativo móvel nativo para operações bancárias dos clientes',
                    'technology': 'React Native + Expo'
                },
                {
                    'name': 'Gateway de Orquestração de APIs BV',
                    'type': 'ApplicationComponent',
                    'description': 'Gateway centralizado para orquestração, roteamento e segurança de APIs',
                    'technology': 'Spring Cloud Gateway + Eureka'
                },
                {
                    'name': 'Serviço de Processamento de Negócio BV',
                    'type': 'ApplicationComponent',
                    'description': 'Serviço central responsável pelo processamento das regras de negócio bancário',
                    'technology': 'Spring Boot 3.0 + Java 17'
                },
                {
                    'name': 'Serviço de Auditoria e Compliance BV',
                    'type': 'ApplicationComponent',
                    'description': 'Serviço especializado em auditoria e conformidade regulatória bancária',
                    'technology': 'Spring Boot + Apache Kafka'
                },
                {
                    'name': 'Base de Dados Transacional Corporativa BV',
                    'type': 'DataObject',
                    'description': 'Base de dados principal para transações bancárias com alta disponibilidade',
                    'technology': 'PostgreSQL 15 Cluster + PgBouncer'
                },
                {
                    'name': 'Cache Distribuído de Alta Performance BV',
                    'type': 'DataObject',
                    'description': 'Sistema de cache distribuído para otimização de performance das operações',
                    'technology': 'Redis 7 Cluster + Sentinel'
                },
                {
                    'name': 'Data Warehouse Corporativo BV',
                    'type': 'DataObject',
                    'description': 'Repositório centralizado de dados para analytics, BI e relatórios gerenciais',
                    'technology': 'Apache Spark + Delta Lake'
                }
            ]
        else:
            # Containers genéricos para outros contextos
            containers = [
                {
                    'name': 'Interface Web do Sistema',
                    'type': 'ApplicationComponent',
                    'description': 'Interface web principal para interação com usuários',
                    'technology': 'React + TypeScript'
                },
                {
                    'name': 'Serviço de Aplicação Principal',
                    'type': 'ApplicationComponent',
                    'description': 'Serviço central responsável pela lógica de negócio',
                    'technology': 'Spring Boot + Java'
                },
                {
                    'name': 'Repositório de Dados Principal',
                    'type': 'DataObject',
                    'description': 'Repositório centralizado para persistência de dados',
                    'technology': 'PostgreSQL'
                }
            ]

        # Validar e ajustar nomes para seguir convenções BV
        for container in containers:
            container['name'] = self._apply_bv_naming_conventions(container['name'], container['type'])

        return containers

    def _identify_components(self, analysis: Dict[str, Any]) -> List[Dict[str, str]]:
        """Identifica componentes baseados na análise - VERSÃO MELHORADA"""
        business_context = analysis.get('business_context', 'general')

        if business_context == 'banking':
            return [
                {
                    'name': 'Controlador de APIs Bancárias BV',
                    'type': 'ApplicationComponent',
                    'description': 'Controlador principal responsável pelo roteamento e validação de APIs bancárias'
                },
                {
                    'name': 'Processador de Regras de Negócio BV',
                    'type': 'ApplicationComponent',
                    'description': 'Componente especializado no processamento de regras de negócio bancário'
                },
                {
                    'name': 'Validador de Compliance Bancário BV',
                    'type': 'ApplicationComponent',
                    'description': 'Componente dedicado à validação de conformidade regulatória'
                },
                {
                    'name': 'Gerenciador de Transações BV',
                    'type': 'ApplicationComponent',
                    'description': 'Gerenciador de transações bancárias com controle ACID'
                },
                {
                    'name': 'Repositório de Dados Transacionais BV',
                    'type': 'DataObject',
                    'description': 'Repositório otimizado para acesso a dados transacionais'
                },
                {
                    'name': 'Cache de Sessões e Tokens BV',
                    'type': 'DataObject',
                    'description': 'Cache especializado para gerenciamento de sessões e tokens de segurança'
                }
            ]
        else:
            return [
                {
                    'name': 'Controlador Principal do Sistema',
                    'type': 'ApplicationComponent',
                    'description': 'Controlador principal responsável pelo roteamento de requisições'
                },
                {
                    'name': 'Processador de Regras de Negócio',
                    'type': 'ApplicationComponent',
                    'description': 'Componente responsável pelo processamento das regras de negócio'
                },
                {
                    'name': 'Repositório de Dados do Sistema',
                    'type': 'DataObject',
                    'description': 'Repositório para acesso e manipulação de dados'
                }
            ]

    def _add_container_relationships(self, container_ids: List[str], analysis: Dict[str, Any]):
        """Adiciona relacionamentos entre containers - VERSÃO MELHORADA"""
        if len(container_ids) < 2:
            return

        # Criar relacionamentos semanticamente corretos baseados no contexto
        business_context = analysis.get('business_context', 'general')

        if business_context == 'banking':
            # Fluxo típico bancário: Interface → Gateway → Serviços → Dados

            # Interface usa Gateway (se ambos existem)
            interface_containers = [cid for cid in container_ids
                                  if 'portal' in self.elements[cid].name.lower() or
                                     'interface' in self.elements[cid].name.lower()]

            gateway_containers = [cid for cid in container_ids
                                if 'gateway' in self.elements[cid].name.lower() or
                                   'api' in self.elements[cid].name.lower()]

            service_containers = [cid for cid in container_ids
                                if 'serviço' in self.elements[cid].name.lower() or
                                   'processamento' in self.elements[cid].name.lower()]

            data_containers = [cid for cid in container_ids
                             if self.elements[cid].element_type == 'DataObject']

            # Interface → Gateway
            for interface_id in interface_containers:
                for gateway_id in gateway_containers:
                    self._add_compliant_relationship(
                        source_id=interface_id,
                        target_id=gateway_id,
                        relationship_type='Serving',
                        name='consome APIs via'
                    )

            # Gateway → Serviços
            for gateway_id in gateway_containers:
                for service_id in service_containers:
                    self._add_compliant_relationship(
                        source_id=gateway_id,
                        target_id=service_id,
                        relationship_type='Triggering',
                        name='roteia requisições para'
                    )

            # Serviços → Dados
            for service_id in service_containers:
                for data_id in data_containers:
                    self._add_compliant_relationship(
                        source_id=service_id,
                        target_id=data_id,
                        relationship_type='Access',
                        name='persiste e consulta dados em'
                    )

            # Relacionamentos entre serviços (orquestra��ão)
            if len(service_containers) > 1:
                for i, service_id in enumerate(service_containers[:-1]):
                    self._add_compliant_relationship(
                        source_id=service_id,
                        target_id=service_containers[i + 1],
                        relationship_type='Triggering',
                        name='coordena operação com'
                    )
        else:
            # Relacionamentos genéricos
            for i in range(len(container_ids) - 1):
                self._add_compliant_relationship(
                    source_id=container_ids[i],
                    target_id=container_ids[i + 1],
                    relationship_type='Serving',
                    name='utiliza'
                )

    def generate_container_diagram(self, user_story: str, system_name: str) -> str:
        """Gera diagrama de containers C4 MELHORADO em conformidade ESTRITA com o metamodelo
        Regras adicionais: BusinessActor NÃO deve aparecer em diagrama de container (apenas contexto),
        portanto a inclusão de atores é desativada por padrão."""
        logger.info(f"Gerando diagrama de containers para: {system_name}")

        # Resetar elementos e relacionamentos
        self.elements.clear()
        self.relationships.clear()

        # Analisar história do usuário com nova versão melhorada
        analysis = self._analyze_user_story(user_story)

        # 1. Criar sistema principal como ApplicationCollaboration
        system_id = self._add_compliant_element(
            name=system_name,
            element_type='ApplicationCollaboration',
            layer=C4LayerType.CONTAINER,
            documentation=f"Sistema aplicativo principal: {system_name}. Contexto de negócio: {analysis.get('business_context', 'general')}. Stack tecnológico: {', '.join(analysis.get('technology_stack', []))}"
        )

        # 2. Adicionar containers baseados na análise inteligente
        containers_analysis = self._identify_containers(analysis)
        container_ids = []

        for container_info in containers_analysis:
            container_id = self._add_compliant_element(
                name=container_info['name'],
                element_type=container_info['type'],
                layer=C4LayerType.CONTAINER,
                documentation=f"{container_info['description']}. Tecnologia: {container_info.get('technology', 'N/A')}"
            )
            container_ids.append(container_id)

            # Sistema contém container
            self._add_compliant_relationship(
                source_id=system_id,
                target_id=container_id,
                relationship_type='Aggregation',
                name='é composto por'
            )

        # 3. Adicionar relacionamentos inteligentes entre containers
        self._add_container_relationships(container_ids, analysis)

        # 4. (OPCIONAL) Adicionar atores de negócio – DESATIVADO por padrão para diagramas de container
        if self.include_actors_in_container_diagram:
            for actor in analysis.get('actors', []):
                actor_id = self._add_compliant_element(
                    name=actor,
                    element_type='BusinessActor',
                    layer=C4LayerType.CONTAINER,
                    documentation=f"Ator de negócio: {actor}. Contexto: {analysis.get('business_context', 'general')}"
                )
                self._add_compliant_relationship(
                    source_id=actor_id,
                    target_id=system_id,
                    relationship_type='Association',
                    name='opera através do'
                )
        # (Fim passo 4) – atores omitidos quando flag False

        # 5. Adicionar sistemas externos
        for ext_system in analysis.get('external_systems', []):
            ext_id = self._add_compliant_element(
                name=ext_system,
                element_type='ApplicationCollaboration',
                layer=C4LayerType.CONTAINER,
                documentation=f"Sistema externo: {ext_system}. Integração necessária para operações bancárias."
            )

            # Sistema principal integra com sistema externo
            self._add_compliant_relationship(
                source_id=system_id,
                target_id=ext_id,
                relationship_type='Association',
                name='integra-se bidirecionalmente com'
            )

        # 6. Validar e corrigir erros de conformidade
        self._validate_and_fix_diagram()

        # Gerar XML final
        xml_content = self._generate_archimate_xml()

        # NOVO: Validar schema após geração
        self._validate_schema_compliance(xml_content)

        return xml_content

    def _validate_schema_compliance(self, xml_content: str):
        """Valida se o XML gerado segue o schema ArchiMate 3.0"""
        try:
            from .schema_validator import ArchiMate30SchemaValidator

            validator = ArchiMate30SchemaValidator()
            is_valid = validator.is_valid_archimate_xml(xml_content)

            if not is_valid:
                report = validator.generate_validation_report(xml_content)
                logger.error(f"❌ XML gerado não segue schema ArchiMate 3.0:\n{report}")
                raise ValueError("XML gerado viola schema ArchiMate 3.0")
            else:
                logger.info("✅ XML gerado está em conformidade com schema ArchiMate 3.0")

        except ImportError:
            logger.warning("⚠️ Schema validator não disponível - pulando validação de schema")

    def _validate_and_fix_diagram(self):
        """Valida e corrige o diagrama para garantir conformidade total"""
        logger.info("🔍 Validando conformidade do diagrama com o metamodelo...")

        # Primeira rodada de validação
        temp_xml = self._generate_archimate_xml()
        self.validation_results = self.validator.validate_c4_diagram(temp_xml)

        initial_errors = len([r for r in self.validation_results if r.severity == ValidationSeverity.ERROR])
        initial_warnings = len([r for r in self.validation_results if r.severity == ValidationSeverity.WARNING])

        logger.info(f"📊 Validação inicial: {initial_errors} erros, {initial_warnings} warnings")

        # Corrigir erros críticos
        if initial_errors > 0:
            logger.info("🔧 Corrigindo erros críticos de conformidade...")
            self._fix_critical_errors()

            # Segunda rodada de validação
            temp_xml = self._generate_archimate_xml()
            self.validation_results = self.validator.validate_c4_diagram(temp_xml)

            final_errors = len([r for r in self.validation_results if r.severity == ValidationSeverity.ERROR])
            final_warnings = len([r for r in self.validation_results if r.severity == ValidationSeverity.WARNING])

            logger.info(f"📊 Validação final: {final_errors} erros, {final_warnings} warnings")

            if final_errors == 0:
                logger.info("✅ Todos os erros críticos foram corrigidos!")
            else:
                logger.warning(f"⚠️ Ainda restam {final_errors} erros que precisam de atenção manual")

        # Adicionar propriedades de qualidade aos elementos
        self._enhance_elements_with_quality_attributes()

    def _enhance_elements_with_quality_attributes(self):
        """Adiciona atributos de qualidade aos elementos para melhorar a conformidade"""

        for element in self.elements.values():
            # Adicionar propriedades específicas por tipo
            if element.element_type == 'ApplicationCollaboration':
                element.properties.update({
                    'stereotype': 'sistema_principal',
                    'criticality': 'high',
                    'compliance_level': 'regulatory'
                })
            elif element.element_type == 'ApplicationComponent':
                element.properties.update({
                    'stereotype': 'componente_negocio',
                    'performance_requirement': 'high_availability',
                    'security_level': 'enterprise'
                })
            elif element.element_type == 'DataObject':
                element.properties.update({
                    'stereotype': 'repositorio_dados',
                    'data_classification': 'confidential',
                    'backup_strategy': 'real_time'
                })
            elif element.element_type == 'BusinessActor':
                element.properties.update({
                    'stereotype': 'ator_negocio',
                    'access_level': 'authenticated',
                    'role_type': 'primary_user'
                })

        logger.info("✨ Elementos aprimorados com atributos de qualidade")

    def _generate_archimate_xml(self) -> str:
        """Gera XML ArchiMate 3.0 em conformidade com o metamodelo seguindo estrutura do exemplo funcional"""

        # Registrar namespaces conforme exemplo funcional
        ET.register_namespace('', 'http://www.opengroup.org/xsd/archimate/3.0/')
        ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')
        ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')

        # Criar elemento root exatamente como no exemplo funcional
        root = ET.Element("model")
        root.set("xmlns", "http://www.opengroup.org/xsd/archimate/3.0/")
        root.set("xmlns:dc", "http://purl.org/dc/elements/1.1/")
        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        root.set("xsi:schemaLocation",
                "http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.0/archimate3_Diagram.xsd http://purl.org/dc/elements/1.1/ http://dublincore.org/schemas/xmls/qdc/2008/02/11/dc.xsd")

        # Generate valid NCName identifier instead of raw UUID
        model_id = self.id_generator.generate_ncname_id('model')
        root.set("identifier", model_id)

        # Nome do modelo
        name_elem = ET.SubElement(root, "name")
        name_elem.set("{http://www.w3.org/XML/1998/namespace}lang", "pt-br")
        name_elem.text = "Diagrama C4 - Metamodelo Compliant"

        # Elementos
        if self.elements:
            elements_elem = ET.SubElement(root, "elements")
            for element in self.elements.values():
                elem = ET.SubElement(elements_elem, "element")
                elem.set("identifier", element.identifier)
                elem.set("xsi:type", element.element_type)

                # Nome
                name = ET.SubElement(elem, "name")
                name.set("{http://www.w3.org/XML/1998/namespace}lang", "pt-br")
                name.text = element.name

                # Documentação
                if element.documentation:
                    doc = ET.SubElement(elem, "documentation")
                    doc.set("{http://www.w3.org/XML/1998/namespace}lang", "pt-br")
                    doc.text = element.documentation

        # Relacionamentos
        if self.relationships:
            relationships_elem = ET.SubElement(root, "relationships")
            for relationship in self.relationships:
                rel = ET.SubElement(relationships_elem, "relationship")
                rel.set("identifier", relationship.identifier)
                rel.set("source", relationship.source)
                rel.set("target", relationship.target)
                rel.set("xsi:type", relationship.relationship_type)

                # Nome do relacionamento (mesmo que vazio, como no exemplo)
                rel_name = ET.SubElement(rel, "name")
                rel_name.set("{http://www.w3.org/XML/1998/namespace}lang", "pt-br")
                rel_name.text = relationship.name if relationship.name else ""

        # CORRIGIDO: Seguir ordem EXATA do schema ArchiMate 3.0 na raiz
        # Optional: organizations, propertyDefinitions (não adicionar vazios)

        # Views: criar container e, dentro dele, 'diagrams' antes de qualquer <view>
        views_elem = ET.SubElement(root, "views")
        diagrams_container = ET.SubElement(views_elem, "diagrams")

        # Criar view DENTRO de views/diagrams
        view_id = self.id_generator.generate_ncname_id('view')
        view = ET.SubElement(diagrams_container, "view")
        view.set("identifier", view_id)
        # Alguns dialetos usam 'xsi:type' ou 'viewpoint'; manter 'xsi:type' como antes
        view.set("xsi:type", "Diagram")

        # Nome da view
        view_name = ET.SubElement(view, "name")
        view_name.set("{http://www.w3.org/XML/1998/namespace}lang", "pt-br")
        view_name.text = "Vista do Diagrama Container"

        # Adicionar elementos visuais
        x_pos = 50
        y_pos = 50
        elements_per_row = 3
        element_width = 200
        element_height = 100
        row_spacing = 150
        col_spacing = 250

        current_row = 0
        current_col = 0
        element_to_node: Dict[str, str] = {}

        for element_id, element in self.elements.items():
            node_id = self.id_generator.generate_ncname_id('node')
            node = ET.SubElement(view, "node")
            node.set("identifier", node_id)
            node.set("elementRef", element_id)
            node.set("xsi:type", "Element")

            current_x = x_pos + (current_col * col_spacing)
            current_y = y_pos + (current_row * row_spacing)

            node.set("x", str(current_x))
            node.set("y", str(current_y))
            node.set("w", str(element_width))
            node.set("h", str(element_height))

            element_to_node[element_id] = node_id

            current_col += 1
            if current_col >= elements_per_row:
                current_col = 0
                current_row += 1

        for relationship in self.relationships:
            source_node = element_to_node.get(relationship.source)
            target_node = element_to_node.get(relationship.target)

            if source_node and target_node:
                connection_id = self.id_generator.generate_ncname_id('connection')
                connection = ET.SubElement(view, "connection")
                connection.set("identifier", connection_id)
                connection.set("relationshipRef", relationship.identifier)
                connection.set("xsi:type", "Relationship")
                connection.set("source", source_node)
                connection.set("target", target_node)

        # Omit <viewpoints> when targeting archimate3_Diagram.xsd (not allowed in this schema)

        # Converter para string formatada corretamente
        xml_str = ET.tostring(root, encoding='unicode', method='xml')

        # Formatar o XML para facilitar leitura
        try:
            import xml.dom.minidom
            dom = xml.dom.minidom.parseString(xml_str)
            formatted_xml = dom.toprettyxml(indent="\t", encoding=None)
            lines = [line for line in formatted_xml.split('\n') if line.strip()]
            formatted_xml = '\n'.join(lines)
            return formatted_xml
        except Exception:
            xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
            return xml_declaration + xml_str

    def get_metamodel_compliance_summary(self) -> Dict[str, Any]:
        """Retorna resumo da conformidade com o metamodelo"""
        total_elements = len(self.elements)
        total_relationships = len(self.relationships)

        # Calcular conformidade baseada nos resultados de validação
        errors = len([r for r in self.validation_results if r.severity == ValidationSeverity.ERROR])
        warnings = len([r for r in self.validation_results if r.severity == ValidationSeverity.WARNING])

        # Score de conformidade (100% - penalidades por erros e warnings)
        error_penalty = errors * 20  # 20 pontos por erro
        warning_penalty = warnings * 5  # 5 pontos por warning
        compliance_score = max(0, 100 - error_penalty - warning_penalty)

        return {
            'compliance_score': compliance_score,
            'total_elements': total_elements,
            'total_relationships': total_relationships,
            'errors': errors,
            'warnings': warnings,
            'validated_against_metamodel': True,
            'metamodel_elements_used': len(set(elem.element_type for elem in self.elements.values())),
            'relationship_types_used': len(set(rel.relationship_type for rel in self.relationships))
        }

    def _determine_template_layer(self, element: MetamodelCompliantElement) -> str:
        """Mapeia elemento para layer do template SDLC."""
        name = element.name.lower()
        etype = element.element_type.lower()
        # Dados
        if etype == 'dataobject' or any(k in name for k in ['dados', 'database', 'repositório', 'cache', 'lake', 'warehouse']):
            return 'data_management'
        # Channels
        if any(k in name for k in ['portal', 'interface', 'mobile', 'app', 'frontend', 'web']):
            return 'channels'
        # Gateways
        if 'gateway' in name or 'proxy' in name:
            # heurística: inbound se first column; usar inbound como padrão
            return 'gateway_inbound'
        # External integration
        if any(k in name for k in ['externa', 'externo', 'terceiro', 'bacen', 'pix', 'serasa', 'spc']):
            return 'external_integration'
        # Outbound
        if any(k in name for k in ['outbound', 'saída']):
            return 'gateway_outbound'
        # Default
        return 'execution_logic'

    def _add_header_labels(self, view_elem: ET.Element):
        header = self.template_layout['header']
        # Background label (transparent)
        bg = ET.SubElement(view_elem, 'node')
        bg.set('identifier', self.id_generator.generate_ncname_id('header_bg'))
        bg.set('xsi:type', 'Label')
        bg.set('x', '0'); bg.set('y', '47'); bg.set('w', '620'); bg.set('h', '80')
        bg_label = ET.SubElement(bg, 'label'); bg_label.set('{http://www.w3.org/XML/1998/namespace}lang', 'pt-br'); bg_label.text = ''
        style = ET.SubElement(bg, 'style'); style.set('lineWidth', '1')
        fill = ET.SubElement(style, 'fillColor'); fill.set('r', '255'); fill.set('g', '255'); fill.set('b', '255'); fill.set('a', '0')
        line = ET.SubElement(style, 'lineColor'); line.set('r', '0'); line.set('g', '0'); line.set('b', '0'); line.set('a', '0')
        font = ET.SubElement(style, 'font'); font.set('name', 'arial'); font.set('size', '24'); font.set('style', 'bold')
        fcolor = ET.SubElement(font, 'color'); fcolor.set('r', '0'); fcolor.set('g', '0'); fcolor.set('b', '0'); fcolor.set('a', '100')

        # Title
        tcfg = header['title']
        title = ET.SubElement(view_elem, 'node')
        title.set('identifier', self.id_generator.generate_ncname_id('title'))
        title.set('xsi:type', 'Label')
        title.set('x', str(tcfg['x'])); title.set('y', str(tcfg['y']))
        title.set('w', str(tcfg['w'])); title.set('h', str(tcfg['h']))
        tlabel = ET.SubElement(title, 'label'); tlabel.set('{http://www.w3.org/XML/1998/namespace}lang', 'pt-br'); tlabel.text = tcfg['text']
        tstyle = ET.SubElement(title, 'style'); tstyle.set('lineWidth', '1')
        tf = ET.SubElement(tstyle, 'fillColor'); tf.set('r', '255'); tf.set('g', '255'); tf.set('b', '255'); tf.set('a', '0')
        tl = ET.SubElement(tstyle, 'lineColor'); tl.set('r', '0'); tl.set('g', '0'); tl.set('b', '0'); tl.set('a', '0')
        tfont = ET.SubElement(tstyle, 'font'); tfont.set('name', 'arial'); tfont.set('size', str(tcfg['size'])); tfont.set('style', tcfg['style'])
        tc = ET.SubElement(tfont, 'color'); tc.set('r', '0'); tc.set('g', '0'); tc.set('b', '0'); tc.set('a', '100')

        # Subtitle
        scfg = header['subtitle']
        sub = ET.SubElement(view_elem, 'node')
        sub.set('identifier', self.id_generator.generate_ncname_id('subtitle'))
        sub.set('xsi:type', 'Label')
        sub.set('x', str(scfg['x'])); sub.set('y', str(scfg['y']))
        sub.set('w', str(scfg['w'])); sub.set('h', str(scfg['h']))
        slabel = ET.SubElement(sub, 'label'); slabel.set('{http://www.w3.org/XML/1998/namespace}lang', 'pt-br'); slabel.text = scfg['text']
        sstyle = ET.SubElement(sub, 'style'); sstyle.set('lineWidth', '1')
        sf = ET.SubElement(sstyle, 'fillColor'); sf.set('r', '255'); sf.set('g', '255'); sf.set('b', '255'); sf.set('a', '0')
        sl = ET.SubElement(sstyle, 'lineColor'); sl.set('r', '0'); sl.set('g', '0'); sl.set('b', '0'); sl.set('a', '0')
        sfont = ET.SubElement(sstyle, 'font'); sfont.set('name', 'arial'); sfont.set('size', str(scfg['size'])); sfont.set('style', scfg['style'])
        sc = ET.SubElement(sfont, 'color'); sc.set('r', '0'); sc.set('g', '0'); sc.set('b', '0'); sc.set('a', '100')

    def _add_layer_containers(self, view_elem: ET.Element):
        for lname, lcfg in self.template_layout['layers'].items():
            container = ET.SubElement(view_elem, 'node')
            container.set('identifier', self.id_generator.generate_ncname_id(f'layer_{lname}'))
            container.set('xsi:type', 'Container')
            container.set('x', str(lcfg['x'])); container.set('y', str(lcfg['y']))
            container.set('w', str(lcfg['w'])); container.set('h', str(lcfg['h']))
            label = ET.SubElement(container, 'label'); label.set('{http://www.w3.org/XML/1998/namespace}lang', 'pt-br'); label.text = lcfg['title']
            style = ET.SubElement(container, 'style'); style.set('lineWidth', '1')
            fill = ET.SubElement(style, 'fillColor'); fill.set('r', str(lcfg['color']['fill'][0])); fill.set('g', str(lcfg['color']['fill'][1])); fill.set('b', str(lcfg['color']['fill'][2])); fill.set('a', str(lcfg['color']['fill'][3]))
            line = ET.SubElement(style, 'lineColor'); line.set('r', str(lcfg['color']['line'][0])); line.set('g', str(lcfg['color']['line'][1])); line.set('b', str(lcfg['color']['line'][2])); line.set('a', str(lcfg['color']['line'][3]))
            font = ET.SubElement(style, 'font'); font.set('name', 'arial'); font.set('size', '10'); font.set('style', 'plain')
            color = ET.SubElement(font, 'color'); color.set('r', '0'); color.set('g', '0'); color.set('b', '0'); color.set('a', '100')
            if lname == 'etapas':
                note = ET.SubElement(container, 'node')
                note.set('identifier', self.id_generator.generate_ncname_id('etapas_note'))
                note.set('xsi:type', 'Label')
                note.set('x', str(lcfg['note_x'])); note.set('y', str(lcfg['note_y']))
                note.set('w', str(lcfg['note_w'])); note.set('h', str(lcfg['note_h']))
                nlabel = ET.SubElement(note, 'label'); nlabel.set('{http://www.w3.org/XML/1998/namespace}lang', 'pt-br'); nlabel.text = lcfg['note_text']
                nstyle = ET.SubElement(note, 'style'); nstyle.set('lineWidth', '1')
                nf = ET.SubElement(nstyle, 'fillColor'); nf.set('r', '255'); nf.set('g', '255'); nf.set('b', '255'); nf.set('a', '100')
                nl = ET.SubElement(nstyle, 'lineColor'); nl.set('r', '0'); nl.set('g', '0'); nl.set('b', '0'); nl.set('a', '100')
                nfont = ET.SubElement(nstyle, 'font'); nfont.set('name', 'arial'); nfont.set('size', '10'); nfont.set('style', 'plain')
                nc = ET.SubElement(nfont, 'color'); nc.set('r', '0'); nc.set('g', '0'); nc.set('b', '0'); nc.set('a', '100')

    def _add_container_elements_using_template(self, view_elem: ET.Element):
        # Agrupar por layer mapeada
        layers = self.template_layout['layers']
        grouped: Dict[str, List[MetamodelCompliantElement]] = {k: [] for k in layers.keys()}
        for e in self.elements.values():
            lname = self._determine_template_layer(e)
            if lname not in grouped:
                lname = 'execution_logic'
            grouped[lname].append(e)

        for lname, elems in grouped.items():
            if not elems or lname not in layers:
                continue
            cfg = layers[lname]
            per_row = cfg.get('elements_per_row', 1)
            for i, e in enumerate(elems):
                row = i // per_row; col = i % per_row
                x = cfg['x'] + cfg.get('horizontal_padding', 10) + col * (cfg.get('element_width', 180) + cfg.get('horizontal_spacing', 20))
                y = cfg['y'] + cfg.get('vertical_padding', 40) + row * (cfg.get('element_height', 50) + cfg.get('vertical_spacing', 15))
                node = ET.SubElement(view_elem, 'node')
                vid = self.id_generator.generate_ncname_id(f'visual_{e.identifier}')
                node.set('identifier', vid)
                node.set('elementRef', e.identifier)
                node.set('xsi:type', 'Element')
                node.set('x', str(x)); node.set('y', str(y))
                node.set('w', str(cfg.get('element_width', 180))); node.set('h', str(cfg.get('element_height', 50)))
                style = ET.SubElement(node, 'style'); style.set('lineWidth', '1')
                fill = ET.SubElement(style, 'fillColor'); fill.set('r', str(cfg['color']['fill'][0])); fill.set('g', str(cfg['color']['fill'][1])); fill.set('b', str(cfg['color']['fill'][2])); fill.set('a', str(cfg['color']['fill'][3]))
                line = ET.SubElement(style, 'lineColor'); line.set('r', str(cfg['color']['line'][0])); line.set('g', str(cfg['color']['line'][1])); line.set('b', str(cfg['color']['line'][2])); line.set('a', str(cfg['color']['line'][3]))
                font = ET.SubElement(style, 'font'); font.set('name', 'Arial'); font.set('size', '10'); font.set('style', 'plain')
                color = ET.SubElement(font, 'color'); color.set('r', '0'); color.set('g', '0'); color.set('b', '0'); color.set('a', '100')
                self._visual_node_by_element[e.identifier] = vid

