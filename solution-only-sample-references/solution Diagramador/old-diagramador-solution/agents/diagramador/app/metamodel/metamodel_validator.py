"""
Validador de Metamodelo BiZZdesign
Melhora a qualidade dos diagramas validando contra o metamodelo organizacional.
Versão independente sem dependências externas.
"""

import xml.etree.ElementTree as ET
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import logging
import os

logger = logging.getLogger(__name__)


@dataclass
class MetamodelElement:
    """Elemento do metamodelo com regras de uso"""
    identifier: str
    element_type: str
    name: str
    documentation: Optional[str] = None
    usage_rules: List[str] = None


@dataclass
class MetamodelRelationship:
    """Relacionamento do metamodelo com regras de conexão"""
    identifier: str
    source_type: str
    target_type: str
    relationship_type: str
    name: Optional[str] = None
    documentation: Optional[str] = None
    is_directed: bool = False
    access_type: Optional[str] = None


class ValidationSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationResult:
    """Resultado de validação contra o metamodelo"""
    severity: ValidationSeverity
    message: str
    element_id: Optional[str] = None
    suggestion: Optional[str] = None


class BiZZdesignMetamodelValidator:
    """Validador que usa o metamodelo BiZZdesign para melhorar qualidade"""

    def __init__(self, metamodel_path: str):
        self.metamodel_path = metamodel_path
        self.metamodel_elements: Dict[str, MetamodelElement] = {}
        self.metamodel_relationships: List[MetamodelRelationship] = []
        self.valid_relationship_patterns: Set[Tuple[str, str, str]] = set()
        self.naming_conventions: Dict[str, str] = {}
        self.mandatory_layers: Set[str] = set()
        self.element_type_mapping: Dict[str, str] = {}
        self._load_metamodel()
        self._initialize_bv_standards()

    def _load_metamodel(self):
        """Carrega o metamodelo BiZZdesign"""
        try:
            if not os.path.exists(self.metamodel_path):
                logger.warning(f"Metamodelo não encontrado: {self.metamodel_path}")
                return

            tree = ET.parse(self.metamodel_path)
            root = tree.getroot()

            logger.info(f"Carregando metamodelo de: {self.metamodel_path}")

            # Namespace do ArchiMate 3.0
            ns = {'archimate': 'http://www.opengroup.org/xsd/archimate/3.0/',
                  'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}

            # Carregar elementos do metamodelo
            elements = root.findall('.//archimate:element', ns)
            logger.info(f"Encontrados {len(elements)} elementos no metamodelo")

            for elem in elements:
                try:
                    identifier = elem.get('identifier')
                    element_type = elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')

                    name_elem = elem.find('archimate:name', ns)
                    name = name_elem.text if name_elem is not None else element_type

                    doc_elem = elem.find('archimate:documentation', ns)
                    documentation = doc_elem.text if doc_elem is not None else None

                    if element_type and identifier:
                        meta_elem = MetamodelElement(
                            identifier=identifier,
                            element_type=element_type,
                            name=name,
                            documentation=documentation
                        )
                        self.metamodel_elements[element_type] = meta_elem
                        
                        # Store mapping for validation
                        self.element_type_mapping[name] = element_type

                except Exception as e:
                    logger.warning(f"Erro ao processar elemento: {e}")

            # Carregar relacionamentos do metamodelo
            relationships = root.findall('.//archimate:relationship', ns)
            logger.info(f"Encontrados {len(relationships)} relacionamentos no metamodelo")

            for rel in relationships:
                try:
                    identifier = rel.get('identifier')
                    source = rel.get('source')
                    target = rel.get('target')
                    rel_type = rel.get('{http://www.w3.org/2001/XMLSchema-instance}type')
                    is_directed = rel.get('isDirected', 'false') == 'true'
                    access_type = rel.get('accessType')

                    name_elem = rel.find('archimate:name', ns)
                    name = name_elem.text if name_elem is not None else ""

                    doc_elem = rel.find('archimate:documentation', ns)
                    documentation = doc_elem.text if doc_elem is not None else None

                    # Find source and target element types
                    source_type = self._get_element_type_by_id(source, root, ns)
                    target_type = self._get_element_type_by_id(target, root, ns)

                    if source_type and target_type and rel_type:
                        meta_rel = MetamodelRelationship(
                            identifier=identifier,
                            source_type=source_type,
                            target_type=target_type,
                            relationship_type=rel_type,
                            name=name,
                            documentation=documentation,
                            is_directed=is_directed,
                            access_type=access_type
                        )
                        self.metamodel_relationships.append(meta_rel)
                        
                        # Add to valid patterns
                        self.valid_relationship_patterns.add((source_type, target_type, rel_type))

                except Exception as e:
                    logger.warning(f"Erro ao processar relacionamento: {e}")

            logger.info(f"Metamodelo carregado: {len(self.metamodel_elements)} elementos, {len(self.metamodel_relationships)} relacionamentos")

        except Exception as e:
            logger.error(f"Erro ao carregar metamodelo: {e}")

    def _get_element_type_by_id(self, element_id: str, root: ET.Element, ns: dict) -> Optional[str]:
        """Encontra o tipo de elemento pelo ID"""
        elem = root.find(f".//archimate:element[@identifier='{element_id}']", ns)
        if elem is not None:
            return elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
        return None

    def _initialize_bv_standards(self):
        """Inicializa padrões específicos do Banco BV baseados no metamodelo"""
        
        # Naming conventions baseadas no metamodelo
        self.naming_conventions = {
            'ApplicationComponent': 'Componente do Aplicativo',
            'ApplicationCollaboration': 'Sistema Aplicativo', 
            'ApplicationService': 'Serviço de Aplicativo',
            'ApplicationInterface': 'Interface de Aplicativo',
            'ApplicationFunction': 'Função de Aplicativo',
            'ApplicationProcess': 'Processo do Aplicativo',
            'ApplicationEvent': 'Evento do Aplicativo',
            'DataObject': 'Repositório de Dados',
            'BusinessActor': 'Ator de Negócio',
            'BusinessRole': 'Papel de Negócio',
            'BusinessProcess': 'Processo de Negócio',
            'BusinessService': 'Serviço de Negócio',
            'BusinessFunction': 'Função de Negócio',
            'TechnologyService': 'Serviço de Tecnologia',
            'SystemSoftware': 'Sistema de Tecnologia (não-sistema)',
            'Node': 'Nó',
            'Device': 'Infra'
        }
        
        # Mandatory layers for C4 diagrams
        self.mandatory_layers = {
            'Context',
            'Container', 
            'Component',
            'Code'
        }

    def validate_c4_diagram(self, diagram_xml: str) -> List[ValidationResult]:
        """Valida um diagrama C4 contra o metamodelo"""
        results = []
        
        try:
            root = ET.fromstring(diagram_xml)
            
            # Validate elements
            results.extend(self._validate_elements(root))
            
            # Validate relationships
            results.extend(self._validate_relationships(root))
            
            # Validate naming conventions
            results.extend(self._validate_naming_conventions(root))
            
            # Validate mandatory structure
            results.extend(self._validate_mandatory_structure(root))
            
            # Validate Banco BV specific rules
            results.extend(self._validate_bv_specific_rules(root))
            
        except ET.ParseError as e:
            results.append(ValidationResult(
                severity=ValidationSeverity.ERROR,
                message=f"Erro ao analisar XML do diagrama: {e}"
            ))
        
        return results

    def _validate_elements(self, root: ET.Element) -> List[ValidationResult]:
        """Valida elementos contra o metamodelo"""
        results = []
        
        # Namespace do ArchiMate 3.0
        ns = {'archimate': 'http://www.opengroup.org/xsd/archimate/3.0/',
              'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
        
        elements = root.findall('.//archimate:element', ns)
        
        for elem in elements:
            element_type = elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
            element_id = elem.get('identifier')
            
            # Check if element type is allowed in metamodel
            if element_type not in self.metamodel_elements:
                results.append(ValidationResult(
                    severity=ValidationSeverity.ERROR,
                    message=f"Tipo de elemento '{element_type}' não permitido no metamodelo",
                    element_id=element_id,
                    suggestion=f"Use um dos tipos permitidos: {', '.join(self.metamodel_elements.keys())}"
                ))
            
            # Validate element documentation if required
            meta_elem = self.metamodel_elements.get(element_type)
            if meta_elem and meta_elem.documentation:
                doc_elem = elem.find('archimate:documentation', ns)
                if doc_elem is None or not doc_elem.text.strip():
                    results.append(ValidationResult(
                        severity=ValidationSeverity.WARNING,
                        message=f"Elemento '{element_type}' deve ter documentação conforme metamodelo",
                        element_id=element_id,
                        suggestion=f"Adicione documentação: {meta_elem.documentation[:100]}..."
                    ))
        
        return results

    def _validate_relationships(self, root: ET.Element) -> List[ValidationResult]:
        """Valida relacionamentos contra o metamodelo"""
        results = []
        
        ns = {'archimate': 'http://www.opengroup.org/xsd/archimate/3.0/',
              'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
        
        relationships = root.findall('.//archimate:relationship', ns)
        
        for rel in relationships:
            rel_type = rel.get('{http://www.w3.org/2001/XMLSchema-instance}type')
            source_id = rel.get('source')
            target_id = rel.get('target')
            rel_id = rel.get('identifier')
            
            # Find source and target elements
            source_elem = root.find(f".//archimate:element[@identifier='{source_id}']", ns)
            target_elem = root.find(f".//archimate:element[@identifier='{target_id}']", ns)
            
            if source_elem is not None and target_elem is not None:
                source_type = source_elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
                target_type = target_elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
                
                # Check if relationship pattern is allowed
                pattern = (source_type, target_type, rel_type)
                if pattern not in self.valid_relationship_patterns:
                    results.append(ValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message=f"Relacionamento '{rel_type}' entre '{source_type}' e '{target_type}' não permitido no metamodelo",
                        element_id=rel_id,
                        suggestion=self._suggest_valid_relationship(source_type, target_type)
                    ))
        
        return results

    def _validate_naming_conventions(self, root: ET.Element) -> List[ValidationResult]:
        """Valida convenções de nomenclatura do Banco BV"""
        results = []
        
        ns = {'archimate': 'http://www.opengroup.org/xsd/archimate/3.0/',
              'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
        
        elements = root.findall('.//archimate:element', ns)
        
        for elem in elements:
            element_type = elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
            element_id = elem.get('identifier')
            
            name_elem = elem.find('archimate:name', ns)
            if name_elem is not None:
                name = name_elem.text
                
                # Check naming convention compliance
                expected_pattern = self.naming_conventions.get(element_type)
                if expected_pattern and not self._check_naming_pattern(name, element_type):
                    results.append(ValidationResult(
                        severity=ValidationSeverity.WARNING,
                        message=f"Nome '{name}' não segue convenção do Banco BV para '{element_type}'",
                        element_id=element_id,
                        suggestion=f"Use padrão: {expected_pattern}"
                    ))
        
        return results

    def _validate_mandatory_structure(self, root: ET.Element) -> List[ValidationResult]:
        """Valida estrutura obrigatória para diagramas C4"""
        results = []
        
        # Check for required elements in C4 diagrams
        required_elements = [
            'ApplicationCollaboration',  # System
            'ApplicationComponent',      # Container/Component
            'BusinessActor'             # Person/Actor
        ]
        
        ns = {'archimate': 'http://www.opengroup.org/xsd/archimate/3.0/',
              'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
        
        for req_type in required_elements:
            elements = root.findall(f".//archimate:element[@{{{ns['xsi']}}}type='{req_type}']", ns)
            if not elements:
                results.append(ValidationResult(
                    severity=ValidationSeverity.WARNING,
                    message=f"Diagrama C4 deve conter pelo menos um elemento do tipo '{req_type}'",
                    suggestion=f"Adicione um elemento '{self.naming_conventions.get(req_type, req_type)}'"
                ))
        
        return results

    def _validate_bv_specific_rules(self, root: ET.Element) -> List[ValidationResult]:
        """Valida regras específicas do Banco BV baseadas no metamodelo"""
        results = []
        
        ns = {'archimate': 'http://www.opengroup.org/xsd/archimate/3.0/',
              'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
        
        # Rule 1: Sistema Aplicativo deve ter componentes
        app_systems = root.findall(f".//archimate:element[@{{{ns['xsi']}}}type='ApplicationCollaboration']", ns)
        for sys in app_systems:
            sys_id = sys.get('identifier')
            # Check if system has components
            comp_rels = root.findall(f".//archimate:relationship[@source='{sys_id}'][@{{{ns['xsi']}}}type='Aggregation']", ns)
            if not comp_rels:
                results.append(ValidationResult(
                    severity=ValidationSeverity.WARNING,
                    message=f"Sistema Aplicativo deve ter componentes agregados",
                    element_id=sys_id,
                    suggestion="Adicione componentes usando relacionamento de Agregação"
                ))
        
        # Rule 2: Repositório de Dados deve ter acesso definido
        data_objects = root.findall(f".//archimate:element[@{{{ns['xsi']}}}type='DataObject']", ns)
        for data in data_objects:
            data_id = data.get('identifier')
            access_rels = root.findall(f".//archimate:relationship[@target='{data_id}'][@{{{ns['xsi']}}}type='Access']", ns)
            if not access_rels:
                results.append(ValidationResult(
                    severity=ValidationSeverity.WARNING,
                    message=f"Repositório de Dados deve ter relacionamentos de acesso definidos",
                    element_id=data_id,
                    suggestion="Defina quais componentes acessam este repositório"
                ))
        
        return results

    def _check_naming_pattern(self, name: str, element_type: str) -> bool:
        """Verifica se o nome segue o padrão para o tipo de elemento"""
        # Simplified pattern checking - can be enhanced with regex
        if not name:
            return False
        
        # Check for appropriate Portuguese naming
        if element_type == 'ApplicationCollaboration':
            return any(keyword in name.lower() for keyword in ['sistema', 'aplicativo', 'plataforma'])
        elif element_type == 'ApplicationComponent':
            return any(keyword in name.lower() for keyword in ['componente', 'módulo', 'serviço'])
        elif element_type == 'DataObject':
            return any(keyword in name.lower() for keyword in ['repositório', 'dados', 'base'])
        elif element_type == 'BusinessActor':
            return any(keyword in name.lower() for keyword in ['usuário', 'cliente', 'ator', 'operador'])
        
        return True  # Default to valid for other types

    def _suggest_valid_relationship(self, source_type: str, target_type: str) -> str:
        """Sugere relacionamentos válidos entre dois tipos de elementos"""
        valid_rels = []
        for pattern in self.valid_relationship_patterns:
            if pattern[0] == source_type and pattern[1] == target_type:
                valid_rels.append(pattern[2])
        
        if valid_rels:
            return f"Relacionamentos válidos: {', '.join(valid_rels)}"
        else:
            return "Nenhum relacionamento direto permitido entre estes tipos"

    def generate_compliance_report(self, diagram_xml: str) -> Dict:
        """Gera relatório de conformidade completo"""
        validation_results = self.validate_c4_diagram(diagram_xml)
        
        errors = [r for r in validation_results if r.severity == ValidationSeverity.ERROR]
        warnings = [r for r in validation_results if r.severity == ValidationSeverity.WARNING]
        info = [r for r in validation_results if r.severity == ValidationSeverity.INFO]
        
        compliance_score = max(0, 100 - (len(errors) * 20) - (len(warnings) * 5))
        
        return {
            'compliance_score': compliance_score,
            'total_issues': len(validation_results),
            'errors': len(errors),
            'warnings': len(warnings),
            'info': len(info),
            'results': validation_results,
            'recommendations': self._generate_recommendations(validation_results),
            'metamodel_elements_used': len(self.metamodel_elements),
            'valid_relationship_patterns': len(self.valid_relationship_patterns)
        }

    def _generate_recommendations(self, results: List[ValidationResult]) -> List[str]:
        """Gera recomendações baseadas nos resultados da validação"""
        recommendations = []
        
        error_count = len([r for r in results if r.severity == ValidationSeverity.ERROR])
        warning_count = len([r for r in results if r.severity == ValidationSeverity.WARNING])
        
        if error_count > 0:
            recommendations.append(f"Corrija {error_count} erro(s) crítico(s) para garantir conformidade com o metamodelo")
        
        if warning_count > 0:
            recommendations.append(f"Considere resolver {warning_count} aviso(s) para melhorar a qualidade do diagrama")
        
        # Specific recommendations based on common issues
        element_type_errors = [r for r in results if "não permitido no metamodelo" in r.message]
        if element_type_errors:
            recommendations.append("Use apenas tipos de elementos definidos no metamodelo Bizzdesign")
        
        naming_warnings = [r for r in results if "convenção do Banco BV" in r.message]
        if naming_warnings:
            recommendations.append("Siga as convenções de nomenclatura do Banco BV para melhor padronização")
        
        return recommendations

    def get_allowed_elements(self) -> List[str]:
        """Retorna lista de tipos de elementos permitidos (interface usada pelo gerador)."""
        return list(self.metamodel_elements.keys())

    def get_allowed_relationships(self, source_type: str, target_type: str) -> List[Tuple[str, str, str]]:
        """Retorna relacionamentos permitidos (source, target, rel_type) para par fornecido."""
        return [p for p in self.valid_relationship_patterns if p[0] == source_type and p[1] == target_type]
