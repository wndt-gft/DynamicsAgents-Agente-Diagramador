"""
Unified Quality Validator - Validador Unificado de Qualidade
Consolida validação de qualidade C4 e aplicação de melhorias de diagrama
Versão consolidada seguindo princípios SRP e eliminando duplicações
"""

import logging
import xml.etree.ElementTree as ET
import os
import re
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


# ===== ENUMS E CLASSES DE QUALIDADE =====

class C4ContainerQuality(Enum):
    """Níveis de qualidade para diagramas C4 Container"""
    EXCELLENT = 10
    VERY_GOOD = 8
    GOOD = 7
    FAIR = 6
    POOR = 4
    INVALID = 0


@dataclass
class QualityMetric:
    """Métrica de qualidade individual"""
    name: str
    score: float
    max_score: float
    description: str
    recommendations: List[str]


@dataclass
class C4QualityReport:
    """Relatório completo de qualidade C4"""
    overall_score: float
    quality_level: C4ContainerQuality
    metrics: List[QualityMetric]
    summary: str
    elements_count: int
    relationships_count: int
    issues: List[str]
    recommendations: List[str]


@dataclass
class ValidationResult:
    """Resultado da validação"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    metadata: Dict[str, Any]


# ===== VALIDADOR PRINCIPAL =====

class QualityValidator:
    """Validador unificado de qualidade para diagramas C4"""

    def __init__(self):
        self.namespaces = {
            'archimate': 'http://www.opengroup.org/xsd/archimate/3.0/',
            'dc': 'http://purl.org/dc/elements/1.1/'
        }
        self.metamodel_validator = MetamodelValidator()

    def validate_diagram(self, xml_content: str) -> C4QualityReport:
        """
        Valida um diagrama C4 Container e retorna relatório de qualidade completo

        Args:
            xml_content: Conteúdo XML do diagrama

        Returns:
            C4QualityReport: Relatório completo de qualidade
        """
        logger.info("🔍 Iniciando validação de qualidade do diagrama")

        try:
            # Parse do XML
            root = ET.fromstring(xml_content)

            # Validação de estrutura XML
            xml_errors = self._validate_xml_structure(root)

            # Validação de metamodelo
            metamodel_errors = self._validate_metamodel_compliance(root)

            # Validação de compatibilidade BiZZdesign
            bizzdesign_errors, bizzdesign_warnings = self._validate_bizzdesign_compatibility(root)

            # Validação de template compliance
            template_errors, template_warnings = self._validate_template_compliance(root)

            # Extrair elementos e relacionamentos
            elements = self._extract_elements(root)
            relationships = self._extract_relationships(root)

            # Executar validações
            metrics = []
            metrics.append(self._validate_structure(elements, relationships))
            metrics.append(self._validate_naming_conventions(elements))
            metrics.append(self._validate_relationships_quality(relationships, elements))
            metrics.append(self._validate_c4_compliance(elements))
            metrics.append(self._validate_diagram_completeness(elements, relationships))

            # Calcular score geral
            total_score = sum(metric.score for metric in metrics)
            max_total_score = sum(metric.max_score for metric in metrics)
            overall_score = (total_score / max_total_score * 100) if max_total_score > 0 else 0

            # Determinar nível de qualidade
            quality_level = self._determine_quality_level(overall_score)

            # Consolidar issues e recomendações
            all_issues = []
            all_recommendations = []
            for metric in metrics:
                all_recommendations.extend(metric.recommendations)

            # Adicionar erros de validação XML, metamodelo e BiZZdesign
            all_issues.extend(xml_errors)
            all_issues.extend(metamodel_errors)
            all_issues.extend(bizzdesign_errors)
            all_issues.extend(template_errors)

            # Validações básicas adicionais
            if len(elements) == 0:
                all_issues.append("Diagrama não possui elementos")
            if len(relationships) == 0 and len(elements) > 1:
                all_issues.append("Diagrama possui elementos mas não possui relacionamentos")
                all_recommendations.append("Adicionar relacionamentos entre os elementos")

            # Gerar resumo
            summary = self._generate_quality_summary(overall_score, quality_level, len(elements), len(relationships))

            return C4QualityReport(
                overall_score=overall_score,
                quality_level=quality_level,
                metrics=metrics,
                summary=summary,
                elements_count=len(elements),
                relationships_count=len(relationships),
                issues=all_issues,
                recommendations=list(set(all_recommendations))  # Remove duplicatas
            )

        except Exception as e:
            logger.error(f"❌ Erro na validação de qualidade: {e}")
            return self._create_error_report(str(e))

    def _extract_elements(self, root: ET.Element) -> List[Dict]:
        """Extrai elementos do XML ArchiMate - CORRIGIDO para funcionar com XML gerado"""
        elements = []

        # Tentar múltiplas estratégias de extração
        # Estratégia 1: Com namespace
        for elem in root.findall(".//element", self.namespaces):
            name_elem = elem.find("name")
            doc_elem = elem.find("documentation")

            elements.append({
                "id": elem.get("identifier", ""),
                "name": name_elem.text if name_elem is not None else "Unnamed",
                "type": elem.get("{http://www.w3.org/2001/XMLSchema-instance}type", "Unknown"),
                "documentation": doc_elem.text if doc_elem is not None else ""
            })

        # Estratégia 2: Sem namespace se não encontrou elementos
        if not elements:
            for elem in root.findall(".//element"):
                name_elem = elem.find("name")
                doc_elem = elem.find("documentation")

                elements.append({
                    "id": elem.get("identifier", ""),
                    "name": name_elem.text if name_elem is not None else "Unnamed",
                    "type": elem.get("{http://www.w3.org/2001/XMLSchema-instance}type", "Unknown"),
                    "documentation": doc_elem.text if doc_elem is not None else ""
                })

        logger.info(f"📊 Extraídos {len(elements)} elementos para validação de qualidade")
        return elements

    def _extract_relationships(self, root: ET.Element) -> List[Dict]:
        """Extrai relacionamentos do XML ArchiMate - CORRIGIDO para funcionar com XML gerado"""
        relationships = []

        # Estratégia 1: Com namespace
        for rel in root.findall(".//relationship", self.namespaces):
            name_elem = rel.find("name")

            relationships.append({
                "id": rel.get("identifier", ""),
                "source": rel.get("source", ""),
                "target": rel.get("target", ""),
                "type": rel.get("{http://www.w3.org/2001/XMLSchema-instance}type", "Unknown"),
                "name": name_elem.text if name_elem is not None else ""
            })

        # Estratégia 2: Sem namespace se não encontrou relacionamentos
        if not relationships:
            for rel in root.findall(".//relationship"):
                name_elem = rel.find("name")

                relationships.append({
                    "id": rel.get("identifier", ""),
                    "source": rel.get("source", ""),
                    "target": rel.get("target", ""),
                    "type": rel.get("{http://www.w3.org/2001/XMLSchema-instance}type", "Unknown"),
                    "name": name_elem.text if name_elem is not None else ""
                })

        logger.info(f"🔗 Extraídos {len(relationships)} relacionamentos para validação de qualidade")
        return relationships

    def _validate_structure(self, elements: List[Dict], relationships: List[Dict]) -> QualityMetric:
        """Valida a estrutura básica do diagrama"""
        score = 0.0
        max_score = 20.0
        recommendations = []

        # Presença de elementos
        if len(elements) > 0:
            score += 5.0
        else:
            recommendations.append("Adicionar elementos ao diagrama")

        # Presença de relacionamentos
        if len(relationships) > 0:
            score += 5.0
        else:
            recommendations.append("Adicionar relacionamentos entre elementos")

        # Proporção elementos/relacionamentos
        if len(elements) > 1:
            ratio = len(relationships) / len(elements)
            if ratio >= 0.5:  # Pelo menos 1 relacionamento para cada 2 elementos
                score += 5.0
            elif ratio >= 0.25:
                score += 2.5
                recommendations.append("Aumentar conectividade entre elementos")
            else:
                recommendations.append("Diagrama com poucos relacionamentos - adicionar mais conexões")

        # Complexidade adequada
        if 3 <= len(elements) <= 12:  # Faixa ideal para diagramas C4 Container
            score += 5.0
        elif len(elements) < 3:
            recommendations.append("Diagrama muito simples - considerar adicionar mais elementos")
        else:
            recommendations.append("Diagrama muito complexo - considerar dividir em múltiplos diagramas")

        return QualityMetric(
            name="Estrutura do Diagrama",
            score=score,
            max_score=max_score,
            description="Avalia a estrutura básica e proporções do diagrama",
            recommendations=recommendations
        )

    def _validate_naming_conventions(self, elements: List[Dict]) -> QualityMetric:
        """Valida convenções de nomenclatura"""
        score = 0.0
        max_score = 15.0
        recommendations = []

        if not elements:
            return QualityMetric("Nomenclatura", 0, max_score, "Sem elementos para validar",
                               ["Adicionar elementos ao diagrama"])

        # Verificar nomes únicos
        names = [elem["name"] for elem in elements if elem["name"]]
        unique_names = set(names)
        if len(unique_names) == len(names):
            score += 5.0
        else:
            recommendations.append("Garantir que todos os elementos tenham nomes únicos")

        # Verificar nomes significativos (não vazios, não genéricos)
        meaningful_names = 0
        generic_patterns = ["container", "component", "element", "system", "unnamed"]

        for elem in elements:
            name = elem["name"].lower()
            if name and not any(pattern in name for pattern in generic_patterns) and len(name) > 2:
                meaningful_names += 1

        if meaningful_names == len(elements):
            score += 5.0
        elif meaningful_names >= len(elements) * 0.8:
            score += 3.0
            recommendations.append("Alguns elementos têm nomes genéricos - usar nomes mais específicos")
        else:
            recommendations.append("Usar nomes mais descritivos e específicos para os elementos")

        # Verificar documentação
        documented_elements = sum(1 for elem in elements if elem.get("documentation", "").strip())
        if documented_elements >= len(elements) * 0.7:
            score += 5.0
        elif documented_elements >= len(elements) * 0.4:
            score += 2.5
            recommendations.append("Adicionar documentação para mais elementos")
        else:
            recommendations.append("Documentar adequadamente os elementos do diagrama")

        return QualityMetric(
            name="Convenções de Nomenclatura",
            score=score,
            max_score=max_score,
            description="Avalia a qualidade dos nomes e documentação dos elementos",
            recommendations=recommendations
        )

    def _validate_relationships_quality(self, relationships: List[Dict], elements: List[Dict]) -> QualityMetric:
        """Valida qualidade dos relacionamentos"""
        score = 0.0
        max_score = 20.0
        recommendations = []

        if not relationships:
            return QualityMetric("Relacionamentos", 0, max_score, "Sem relacionamentos para validar",
                               ["Adicionar relacionamentos entre elementos"])

        element_ids = {elem["id"] for elem in elements}

        # Verificar integridade dos relacionamentos
        valid_relationships = 0
        for rel in relationships:
            if rel["source"] in element_ids and rel["target"] in element_ids:
                valid_relationships += 1

        if valid_relationships == len(relationships):
            score += 8.0
        else:
            recommendations.append("Corrigir relacionamentos com referências inválidas")

        # Verificar nomes dos relacionamentos
        named_relationships = sum(1 for rel in relationships if rel.get("name", "").strip())
        if named_relationships >= len(relationships) * 0.7:
            score += 6.0
        elif named_relationships >= len(relationships) * 0.4:
            score += 3.0
            recommendations.append("Adicionar descrições para mais relacionamentos")
        else:
            recommendations.append("Nomear e descrever adequadamente os relacionamentos")

        # Verificar tipos de relacionamentos apropriados
        appropriate_types = {"Serving", "Access", "Flow", "Triggering", "Composition", "Association"}
        good_types = sum(1 for rel in relationships if rel.get("type") in appropriate_types)
        if good_types >= len(relationships) * 0.8:
            score += 6.0
        else:
            recommendations.append("Usar tipos de relacionamentos mais apropriados para C4")

        return QualityMetric(
            name="Qualidade dos Relacionamentos",
            score=score,
            max_score=max_score,
            description="Avalia a qualidade e adequação dos relacionamentos",
            recommendations=recommendations
        )

    def _validate_c4_compliance(self, elements: List[Dict]) -> QualityMetric:
        """Valida conformidade com padrões C4 Model"""
        score = 0.0
        max_score = 25.0
        recommendations = []

        if not elements:
            return QualityMetric("Conformidade C4", 0, max_score, "Sem elementos para validar",
                               ["Adicionar elementos seguindo padrões C4"])

        # Verificar tipos de elementos apropriados para C4 Container
        c4_container_types = {
            "ApplicationComponent", "ApplicationService", "ApplicationInterface",
            "BusinessActor", "BusinessRole", "DataObject"
        }

        appropriate_elements = sum(1 for elem in elements if elem.get("type") in c4_container_types)
        if appropriate_elements >= len(elements) * 0.9:
            score += 8.0
        elif appropriate_elements >= len(elements) * 0.7:
            score += 5.0
            recommendations.append("Alguns elementos não seguem tipos padrão C4 Container")
        else:
            recommendations.append("Usar tipos de elementos apropriados para diagramas C4 Container")

        # Verificar presença de atores
        actors = [elem for elem in elements if elem.get("type") in ["BusinessActor", "BusinessRole"]]
        if actors:
            score += 5.0
        else:
            recommendations.append("Adicionar pelo menos um ator ao diagrama C4")

        # Verificar presença de containers de aplicação
        app_containers = [elem for elem in elements
                         if elem.get("type") in ["ApplicationComponent", "ApplicationService"]]
        if len(app_containers) >= 2:
            score += 7.0
        elif len(app_containers) == 1:
            score += 3.0
            recommendations.append("Considerar adicionar mais containers de aplicação")
        else:
            recommendations.append("Adicionar containers de aplicação ao diagrama")

        # Verificar presença de dados (opcional mas recomendado)
        data_elements = [elem for elem in elements if elem.get("type") == "DataObject"]
        if data_elements:
            score += 5.0
        else:
            recommendations.append("Considerar adicionar elementos de dados ao diagrama")

        return QualityMetric(
            name="Conformidade C4 Model",
            score=score,
            max_score=max_score,
            description="Avalia aderência aos padrões e práticas do C4 Model",
            recommendations=recommendations
        )

    def _validate_diagram_completeness(self, elements: List[Dict], relationships: List[Dict]) -> QualityMetric:
        """Valida completude do diagrama"""
        score = 0.0
        max_score = 20.0
        recommendations = []

        # Verificar se há elementos órfãos (sem relacionamentos)
        if relationships:
            connected_elements = set()
            for rel in relationships:
                connected_elements.add(rel["source"])
                connected_elements.add(rel["target"])

            orphan_elements = len(elements) - len(connected_elements.intersection({elem["id"] for elem in elements}))
            if orphan_elements == 0:
                score += 8.0
            elif orphan_elements <= len(elements) * 0.2:
                score += 5.0
                recommendations.append("Alguns elementos não estão conectados - verificar se é intencional")
            else:
                recommendations.append("Muitos elementos órfãos - conectar elementos ou remover desnecessários")

        # Verificar diversidade de tipos
        unique_types = len(set(elem.get("type") for elem in elements))
        if unique_types >= 3:
            score += 6.0
        elif unique_types >= 2:
            score += 3.0
            recommendations.append("Considerar adicionar mais diversidade de tipos de elementos")
        else:
            recommendations.append("Diagrama muito homogêneo - adicionar diferentes tipos de elementos")

        # Verificar se há fluxo lógico
        if relationships and len(relationships) >= len(elements) - 1:  # Conectividade mínima
            score += 6.0
        else:
            recommendations.append("Adicionar mais relacionamentos para criar fluxo lógico claro")

        return QualityMetric(
            name="Completude do Diagrama",
            score=score,
            max_score=max_score,
            description="Avalia se o diagrama está completo e bem conectado",
            recommendations=recommendations
        )

    def _determine_quality_level(self, overall_score: float) -> C4ContainerQuality:
        """Determina o nível de qualidade baseado no score"""
        if overall_score >= 90:
            return C4ContainerQuality.EXCELLENT
        elif overall_score >= 80:
            return C4ContainerQuality.VERY_GOOD
        elif overall_score >= 70:
            return C4ContainerQuality.GOOD
        elif overall_score >= 60:
            return C4ContainerQuality.FAIR
        elif overall_score >= 40:
            return C4ContainerQuality.POOR
        else:
            return C4ContainerQuality.INVALID

    def _generate_quality_summary(self, score: float, quality_level: C4ContainerQuality,
                                 elements_count: int, relationships_count: int) -> str:
        """Gera resumo da qualidade"""
        return (f"Diagrama com {elements_count} elementos e {relationships_count} relacionamentos. "
               f"Score de qualidade: {score:.1f}% ({quality_level.name}). "
               f"{'Excelente qualidade!' if score >= 90 else 'Melhorias recomendadas.' if score < 70 else 'Boa qualidade.'}")

    def _create_error_report(self, error_message: str) -> C4QualityReport:
        """Cria relatório de erro"""
        return C4QualityReport(
            overall_score=0.0,
            quality_level=C4ContainerQuality.INVALID,
            metrics=[],
            summary=f"Erro na validação: {error_message}",
            elements_count=0,
            relationships_count=0,
            issues=[f"Erro na validação: {error_message}"],
            recommendations=["Verificar formato e conteúdo do diagrama"]
        )

    def apply_quality_improvements(self, xml_content: str) -> str:
        """
        Aplica melhorias de qualidade automaticamente ao diagrama

        Args:
            xml_content: Conteúdo XML original

        Returns:
            str: XML melhorado
        """
        logger.info("🔧 Aplicando melhorias de qualidade ao diagrama")

        try:
            # Parse do XML
            root = ET.fromstring(xml_content)

            # Aplicar melhorias
            self._improve_element_names(root)
            self._add_missing_documentation(root)
            self._normalize_relationship_types(root)

            # Retornar XML melhorado
            return ET.tostring(root, encoding='unicode', method='xml')

        except Exception as e:
            logger.error(f"❌ Erro na aplicação de melhorias: {e}")
            return xml_content

    def _improve_element_names(self, root: ET.Element):
        """Melhora nomes de elementos genéricos"""
        for elem in root.findall(".//element"):
            name_elem = elem.find("name")
            if name_elem is not None:
                current_name = name_elem.text or ""
                if current_name.lower() in ["container", "component", "element", "system"]:
                    # Tentar melhorar baseado no tipo
                    elem_type = elem.get("{http://www.w3.org/2001/XMLSchema-instance}type", "")
                    if "Application" in elem_type:
                        name_elem.text = f"Aplicação {current_name}"
                    elif "Business" in elem_type:
                        name_elem.text = f"Ator {current_name}"

    def _add_missing_documentation(self, root: ET.Element):
        """Adiciona documentação básica para elementos sem documentação"""
        for elem in root.findall(".//element"):
            doc_elem = elem.find("documentation")
            if doc_elem is None or not doc_elem.text:
                name_elem = elem.find("name")
                elem_type = elem.get("{http://www.w3.org/2001/XMLSchema-instance}type", "")

                if doc_elem is None:
                    doc_elem = ET.SubElement(elem, "documentation")

                name = name_elem.text if name_elem is not None else "Elemento"
                doc_elem.text = f"{name} - {elem_type} do sistema"

    def _normalize_relationship_types(self, root: ET.Element):
        """Normaliza tipos de relacionamentos para padrões C4"""
        type_mapping = {
            "Uses": "Serving",
            "Calls": "Serving",
            "Connects": "Association",
            "Contains": "Composition"
        }

        for rel in root.findall(".//relationship"):
            current_type = rel.get("{http://www.w3.org/2001/XMLSchema-instance}type", "")
            if current_type in type_mapping:
                rel.set("{http://www.w3.org/2001/XMLSchema-instance}type", type_mapping[current_type])

    def _validate_xml_structure(self, root: ET.Element) -> List[str]:
        """Valida estrutura XML básica"""
        errors = []

        # Verificar namespace
        expected_ns = 'http://www.opengroup.org/xsd/archimate/3.0/'
        if not root.tag.startswith(f'{{{expected_ns}}}'):
            errors.append(f"Namespace incorreto. Esperado: {expected_ns}")

        # Verificar seções obrigatórias
        required_sections = ['elements', 'relationships', 'views']
        for section in required_sections:
            if not root.find(f'.//{{{expected_ns}}}{section}'):
                errors.append(f"Seção obrigatória '{section}' não encontrada")

        return errors

    def _validate_metamodel_compliance(self, root: ET.Element) -> List[str]:
        """Valida conformidade com metamodelo"""
        errors = []

        # Validar tipos de elementos
        for element in root.findall('.//element'):
            element_type = element.get('{http://www.w3.org/2001/XMLSchema-instance}type')
            if element_type and element_type not in self.metamodel_validator.allowed_types:
                errors.append(f"Tipo de elemento não permitido: {element_type}")

        # Validar tipos de relacionamentos
        for relationship in root.findall('.//relationship'):
            rel_type = relationship.get('{http://www.w3.org/2001/XMLSchema-instance}type')
            if rel_type and rel_type not in self.metamodel_validator.allowed_relationships:
                errors.append(f"Tipo de relacionamento não permitido: {rel_type}")

        return errors

    def _validate_bizzdesign_compatibility(self, root: ET.Element) -> Tuple[List[str], List[str]]:
        """Valida compatibilidade com BiZZdesign"""
        errors = []
        warnings = []

        # Validar IDs únicos e NCName
        ids_found = set()
        ncname_pattern = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_\-\.]*$')

        for elem in root.iter():
            identifier = elem.get('identifier')
            if identifier:
                # Verificar unicidade
                if identifier in ids_found:
                    errors.append(f"ID duplicado: {identifier}")
                else:
                    ids_found.add(identifier)

                # Verificar formato NCName
                if not ncname_pattern.match(identifier):
                    warnings.append(f"ID pode não ser compatível com NCName: {identifier}")

        # Validar referências
        available_ids = ids_found

        for rel in root.findall('.//relationship'):
            source = rel.get('source')
            target = rel.get('target')

            if source and source not in available_ids:
                errors.append(f"Relacionamento referencia source inexistente: {source}")
            if target and target not in available_ids:
                errors.append(f"Relacionamento referencia target inexistente: {target}")

        return errors, warnings

    def _validate_template_compliance(self, root: ET.Element) -> Tuple[List[str], List[str]]:
        """Valida conformidade com template SDLC"""
        errors = []
        warnings = []

        # Verificar título seguindo padrão do template
        title_found = False
        for name_elem in root.findall('.//name[@xml:lang="pt-br"]', {'xml': 'http://www.w3.org/XML/1998/namespace'}):
            title = name_elem.text or ""
            if "Plataforma e Produtos de Dados" in title:
                title_found = True
                break

        if not title_found:
            warnings.append("Título não segue padrão do template SDLC")

        # Verificar presença de camadas obrigatórias
        required_layers = [
            'CHANNELS', 'GATEWAY INBOUND', 'EXECUTION LOGIC',
            'GATEWAY OUTBOUND', 'EXTERNAL INTEGRATION LAYER', 'DATA MANAGEMENT'
        ]

        found_layers = []
        for label in root.findall('.//label[@xml:lang="pt-br"]', {'xml': 'http://www.w3.org/XML/1998/namespace'}):
            label_text = label.text or ""
            for layer in required_layers:
                if layer in label_text:
                    found_layers.append(layer)

        missing_layers = set(required_layers) - set(found_layers)
        if missing_layers:
            warnings.append(f"Camadas ausentes: {', '.join(missing_layers)}")

        return errors, warnings

    def _calculate_quality_score(self, root: ET.Element) -> float:
        """Calcula score de qualidade do diagrama"""
        score = 0.0
        max_score = 10.0

        # Pontuação por presença de elementos (2 pontos)
        elements = root.findall('.//element')
        if elements:
            score += min(2.0, len(elements) * 0.2)

        # Pontuação por relacionamentos (2 pontos)
        relationships = root.findall('.//relationship')
        if relationships:
            score += min(2.0, len(relationships) * 0.25)

        # Pontuação por views (2 pontos)
        views = root.findall('.//view')
        if views:
            score += min(2.0, len(views) * 0.5)

        # Pontuação por diversidade de tipos (2 pontos)
        element_types = set()
        for elem in elements:
            elem_type = elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
            if elem_type:
                element_types.add(elem_type)

        score += min(2.0, len(element_types) * 0.4)

        # Pontuação por elementos visuais (2 pontos)
        visual_elements = root.findall('.//node')
        if visual_elements:
            score += min(2.0, len(visual_elements) * 0.1)

        return min(score, max_score)


class MetamodelValidator:
    """Validador de conformidade com metamodelo"""

    def __init__(self, metamodel_path: str = None):
        self.metamodel_path = metamodel_path or self._get_default_metamodel_path()
        self.logger = logging.getLogger(__name__)
        self.allowed_types = set()
        self.allowed_relationships = set()
        self._load_metamodel()

    def _get_default_metamodel_path(self) -> str:
        """Retorna caminho padrão do metamodelo (corrigido para subir 2 níveis: validators -> tools -> app)."""
        # validators/quality_validator.py -> parents[0]=validators, [1]=tools, [2]=app
        base = Path(__file__).resolve()
        candidate = (base.parents[2] / 'metamodel' / 'metamodelo.xml').resolve()
        return str(candidate)

    def _load_metamodel(self):
        """Carrega tipos e relacionamentos permitidos do metamodelo"""
        try:
            # Normalizar caminho se passado externamente
            self.metamodel_path = str(Path(self.metamodel_path).resolve())
            if not os.path.exists(self.metamodel_path):
                self.logger.warning(f"Metamodelo não encontrado: {self.metamodel_path}")
                self._load_default_metamodel()
                return
            self.logger.info(f"Carregando metamodelo: {self.metamodel_path}")
            tree = ET.parse(self.metamodel_path)
            root = tree.getroot()

            # Extrair tipos de elementos permitidos
            for element in root.findall('.//element'):
                element_type = element.get('{http://www.w3.org/2001/XMLSchema-instance}type', '')
                if element_type:
                    self.allowed_types.add(element_type)

            # Extrair tipos de relacionamentos permitidos
            for relationship in root.findall('.//relationship'):
                rel_type = relationship.get('{http://www.w3.org/2001/XMLSchema-instance}type', '')
                if rel_type:
                    self.allowed_relationships.add(rel_type)

            self.logger.info(f"✅ Metamodelo carregado: {len(self.allowed_types)} tipos de elementos, {len(self.allowed_relationships)} tipos de relacionamentos")

        except Exception as e:
            self.logger.error(f"Erro ao carregar metamodelo: {e}")
            self._load_default_metamodel()

    def _load_default_metamodel(self):
        """Carrega metamodelo padrão se o arquivo não existir"""
        # Tipos ArchiMate 3.0 padrão
        self.allowed_types = {
            'ApplicationComponent', 'ApplicationService', 'ApplicationInterface',
            'ApplicationFunction', 'ApplicationProcess', 'ApplicationEvent',
            'DataObject', 'BusinessObject', 'TechnologyService', 'Device',
            'SystemSoftware', 'Node', 'CommunicationNetwork', 'Path',
            'Artifact', 'TechnologyInterface', 'TechnologyFunction'
        }

        self.allowed_relationships = {
            'ServingRelationship', 'RealizationRelationship', 'FlowRelationship',
            'AccessRelationship', 'CompositionRelationship', 'AggregationRelationship',
            'AssignmentRelationship', 'AssociationRelationship', 'TriggeringRelationship',
            'SpecializationRelationship', 'InfluenceRelationship'
        }


# ===== FUNÇÕES DE CONVENIÊNCIA =====

def validate_diagram_quality(xml_content: str) -> C4QualityReport:
    """
    Função de conveniência para validação de qualidade

    Args:
        xml_content: Conteúdo XML do diagrama

    Returns:
        C4QualityReport: Relatório de qualidade
    """
    validator = QualityValidator()
    return validator.validate_diagram(xml_content)


def apply_quality_improvements(xml_content: str) -> str:
    """
    Função de conveniência para aplicação de melhorias

    Args:
        xml_content: Conteúdo XML original

    Returns:
        str: XML melhorado
    """
    validator = QualityValidator()
    return validator.apply_quality_improvements(xml_content)


def validate_and_improve_diagram(xml_content: str) -> Tuple[C4QualityReport, str]:
    """
    Função de conveniência para validação e melhoria em uma operação

    Args:
        xml_content: Conteúdo XML original

    Returns:
        Tuple[C4QualityReport, str]: (Relatório de qualidade, XML melhorado)
    """
    validator = QualityValidator()

    # Primeiro valida
    report = validator.validate_diagram(xml_content)

    # Depois aplica melhorias se necessário
    improved_xml = xml_content
    if report.overall_score < 80:  # Aplica melhorias se score < 80%
        improved_xml = validator.apply_quality_improvements(xml_content)

    return report, improved_xml


def scan_for_hardcoded_terms(file_path: str) -> Dict[str, Any]:
    """
    Escaneia arquivo procurando por termos hardcoded proibidos

    Args:
        file_path: Caminho do arquivo para escanear

    Returns:
        Dict com resultado do scan
    """
    # Termos proibidos (hardcodes de domínio específico) - versão mais restritiva
    prohibited_terms = {
        'banking_specific': ['pix', 'bacen', 'banco central', 'swift', 'agencia'],
        'payments_specific': ['mastercard', 'visa'],
        'systems_specific': ['core banking', 'mainframe', 'cobol', 'db2']
    }

    violations = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().lower()

        for category, terms in prohibited_terms.items():
            for term in terms:
                if term.lower() in content:
                    violations.append({
                        'category': category,
                        'term': term,
                        'line_numbers': _find_line_numbers(file_path, term)
                    })

        return {
            'success': True,
            'file_path': file_path,
            'violations_found': len(violations),
            'violations': violations,
            'is_domain_agnostic': len(violations) == 0
        }

    except Exception as e:
        return {
            'success': False,
            'error': f"Erro ao escanear arquivo: {str(e)}"
        }

def _find_line_numbers(file_path: str, term: str) -> List[int]:
    """Encontra números das linhas onde um termo aparece"""
    line_numbers = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if term.lower() in line.lower():
                    line_numbers.append(line_num)
    except Exception:
        pass

    return line_numbers
