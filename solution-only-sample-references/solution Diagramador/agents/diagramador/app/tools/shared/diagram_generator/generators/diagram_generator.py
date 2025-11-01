"""
Diagram Generator - Simplified: removed EnhancedIntelligentAnalyzer dependency.
"""

import logging
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

try:
    from ..analyzers.analyzer import analyze_user_story
    from .template_based_generator import TemplateBasedContainerGenerator
    from ..validators.quality_validator import QualityValidator, validate_diagram_quality
    from .id_generator import NCNameIDGenerator
    ENHANCED_TOOLS_AVAILABLE = True
except ImportError:
    ENHANCED_TOOLS_AVAILABLE = False

logger = logging.getLogger(__name__)

class GenericDiagramGenerator:
    """Gerador genérico de diagramas C4 Container baseado em template"""

    def __init__(self, config_path: str = None, template_path: str = None):
        self.config_path = config_path
        self.template_path = template_path or self._get_default_template_path()

        # Inicializar componentes da nova arquitetura
        if ENHANCED_TOOLS_AVAILABLE:
            self.generator = TemplateBasedContainerGenerator()
            self.validator = QualityValidator()
            self.id_generator = NCNameIDGenerator()
        else:
            logger.warning("Ferramentas aprimoradas não disponíveis - usando fallbacks")

        logger.info("Gerador genérico de diagramas C4 inicializado")

    def _get_default_template_path(self) -> str:
        """Retorna caminho padrão do template SDLC"""
        return str(
            Path(__file__).resolve().parents[3] / 'templates' / 'C4-Model' / 'layout_sdlc.xml'
        )

    def generate_container_diagram_from_story(self, user_story: str, **kwargs) -> Dict[str, Any]:
        """
        Gera diagrama C4 Container a partir de história de usuário
        Método principal que integra toda a pipeline genérica

        Args:
            user_story: História de usuário
            **kwargs: Argumentos adicionais (diagram_type, quality_check, etc.)

        Returns:
            Dict com resultado completo da geração
        """
        try:
            logger.info("Iniciando geração de diagrama C4 Container genérico")

            # Validar entrada
            if not user_story or not user_story.strip():
                return {
                    'success': False,
                    'error': 'História de usuário não pode estar vazia'
                }

            # Análise inteligente da história
            logger.info("Executando análise inteligente da história...")
            analysis_result = self._analyze_user_story(user_story)

            if not analysis_result.get('success'):
                return {
                    'success': False,
                    'error': f'Erro na análise: {analysis_result.get("error", "Erro desconhecido")}'

                }

            # Geração do diagrama baseado no template
            logger.info("Gerando diagrama baseado no template SDLC...")
            generation_result = self._generate_diagram_from_analysis(analysis_result)

            if not generation_result.get('success'):
                return {
                    'success': False,
                    'error': f'Erro na geração: {generation_result.get("error", "Erro desconhecido")}'

                }

            # Validação de qualidade (se solicitada)
            quality_result = None
            if kwargs.get('quality_check', True):
                logger.info("Executando validação de qualidade...")
                quality_result = self._validate_diagram_quality(generation_result['xml_content'])

            # Salvar diagrama
            filename = self._save_diagram(
                generation_result['xml_content'],
                kwargs.get('diagram_type', 'container')
            )

            return {
                'success': True,
                'xml_content': generation_result['xml_content'],
                'filename': filename,
                'analysis': analysis_result,
                'quality': quality_result,
                'metadata': {
                    'generated_at': datetime.now().isoformat(),
                    'template_based': True,
                    'domain_agnostic': True,
                    'total_containers': len(analysis_result.get('containers', [])),
                    'total_relationships': len(analysis_result.get('relationships', [])),
                    'layers_used': analysis_result.get('metadata', {}).get('layers_used', [])
                }
            }

        except Exception as e:
            logger.error(f"Erro na geração do diagrama: {str(e)}")
            return {
                'success': False,
                'error': f'Erro interno: {str(e)}'
            }

    def _analyze_user_story(self, user_story: str) -> Dict[str, Any]:
        """Executa análise inteligente da história de usuário"""
        if not ENHANCED_TOOLS_AVAILABLE:
            return self._fallback_analysis(user_story)

        try:
            return analyze_user_story(user_story, "Banking")
        except Exception as e:
            logger.error(f"Erro na análise inteligente: {e}")
            return self._fallback_analysis(user_story)

    def _generate_diagram_from_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Gera diagrama XML a partir da análise"""
        if not ENHANCED_TOOLS_AVAILABLE:
            return self._fallback_generation(analysis)

        try:
            # Carregar template se não foi carregado
            if hasattr(self.generator, 'load_template'):
                self.generator.load_template(self.template_path)

            # Gerar XML do diagrama
            xml_content = self.generator.generate_container_diagram_from_template(analysis)

            return {
                'success': True,
                'xml_content': xml_content
            }

        except Exception as e:
            logger.error(f"Erro na geração do diagrama: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _validate_diagram_quality(self, xml_content: str) -> Dict[str, Any]:
        """Executa validação de qualidade do diagrama"""
        if not ENHANCED_TOOLS_AVAILABLE:
            return {'quality_score': 0.0, 'message': 'Validação não disponível'}

        try:
            quality_report = validate_diagram_quality(xml_content)

            return {
                'quality_score': quality_report.overall_score,
                'quality_level': quality_report.quality_level.name,
                'total_errors': len(quality_report.issues),
                'total_warnings': len(quality_report.recommendations),
                'summary': quality_report.summary,
                'issues': quality_report.issues,
                'recommendations': quality_report.recommendations
            }

        except Exception as e:
            logger.error(f"Erro na validação de qualidade: {e}")
            return {
                'quality_score': 0.0,
                'error': str(e),
                'bizzdesign_compatible': False,
                'template_compliant': False
            }

    def _save_diagram(self, xml_content: str, diagram_type: str) -> str:
        """Salva diagrama em arquivo"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"diagrama_{diagram_type}_generic_{timestamp}.xml"

        # Diretório de saída
        output_dir = os.path.join(
            os.path.dirname(__file__), '..', '..', 'outputs'
        )
        os.makedirs(output_dir, exist_ok=True)

        filepath = os.path.join(output_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(xml_content)

            logger.info(f"Diagrama salvo: {filename}")
            return filename

        except Exception as e:
            logger.error(f"Erro ao salvar diagrama: {e}")
            return f"erro_salvamento_{timestamp}.xml"

    def _fallback_analysis(self, user_story: str) -> Dict[str, Any]:
        """Análise básica de fallback"""
        logger.warning("Usando análise de fallback")

        # Extração básica de entidades
        words = user_story.lower().split()

        # Identificar possíveis containers baseado em palavras-chave
        containers = []
        if any(word in words for word in ['api', 'serviço', 'service']):
            containers.append({
                'name': 'API Service',
                'type': 'application-service',
                'description': 'Serviço de API extraído da história',
                'layer': 'execution_logic'
            })

        if any(word in words for word in ['banco', 'database', 'dados']):
            containers.append({
                'name': 'Database',
                'type': 'data-object',
                'description': 'Base de dados do sistema',
                'layer': 'data_management'
            })

        if any(word in words for word in ['app', 'aplicativo', 'interface']):
            containers.append({
                'name': 'Application Interface',
                'type': 'application-component',
                'description': 'Interface da aplicação',
                'layer': 'channels'
            })

        # Se não encontrou nada, criar container genérico
        if not containers:
            containers.append({
                'name': 'System Component',
                'type': 'application-component',
                'description': 'Componente principal do sistema',
                'layer': 'execution_logic'
            })

        return {
            'success': True,
            'containers': containers,
            'relationships': [],
            'business_entities': [],
            'capabilities': ['processar', 'gerenciar'],
            'quality_score': 5.0,
            'metadata': {
                'total_containers': len(containers),
                'layers_used': [c['layer'] for c in containers],
                'complexity': 'low',
                'fallback_used': True
            }
        }

    def _fallback_generation(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Geração básica de fallback"""
        logger.warning("Usando geração de fallback")

        # Criar XML básico ArchiMate
        xml_content = self._create_basic_archimate_xml(analysis)

        return {
            'success': True,
            'xml_content': xml_content
        }

    def _create_basic_archimate_xml(self, analysis: Dict[str, Any]) -> str:
        """Cria XML ArchiMate básico"""
        # Criar estrutura XML básica
        root = ET.Element('model')
        root.set('xmlns', 'http://www.opengroup.org/xsd/archimate/3.0/')
        root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
        root.set('identifier', f'fallback-model-{datetime.now().strftime("%Y%m%d%H%M%S")}')

        # Nome do modelo
        name_elem = ET.SubElement(root, 'name')
        name_elem.text = 'Diagrama C4 Container - Gerado Genericamente'

        # Elementos
        elements_section = ET.SubElement(root, 'elements')

        containers = analysis.get('containers', [])
        container_ids: List[str] = []
        for i, container in enumerate(containers):
            elem = ET.SubElement(elements_section, 'element')
            elem_id = f'container-{i+1}'
            elem.set('identifier', elem_id)
            elem.set('xsi:type', 'ApplicationComponent')

            elem_name = ET.SubElement(elem, 'name')
            elem_name.text = container.get('name', f'Container {i+1}')

            elem_desc = ET.SubElement(elem, 'documentation')
            elem_desc.text = container.get('description', 'Componente do sistema')

            container_ids.append(elem_id)

        # Relacionamentos: adicionar ao menos um se possível; nunca criar vazio
        if len(container_ids) >= 2:
            relationships_section = ET.SubElement(root, 'relationships')
            rel = ET.SubElement(relationships_section, 'relationship')
            rel.set('identifier', 'rel-1')
            rel.set('source', container_ids[0])
            rel.set('target', container_ids[1])
            rel.set('xsi:type', 'Serving')
            rel_name = ET.SubElement(rel, 'name')
            rel_name.text = f"Integração {containers[0].get('name', 'A')} → {containers[1].get('name', 'B')}"
        # Se não há relacionamentos, omitir o bloco <relationships> para evitar schema error

        # Views (opcional)
        ET.SubElement(root, 'views')

        # Converter para string
        return ET.tostring(root, encoding='unicode')

# Função de conveniência para compatibilidade
def generate_container_diagram(user_story: str, diagram_type: str = "container", **kwargs) -> Dict[str, Any]:
    """
    Função de conveniência para geração de diagrama C4 Container

    Args:
        user_story: História de usuário
        diagram_type: Tipo do diagrama (sempre "container")
        **kwargs: Argumentos adicionais

    Returns:
        Dict com resultado da geração
    """
    generator = GenericDiagramGenerator()
    return generator.generate_container_diagram_from_story(user_story, diagram_type=diagram_type, **kwargs)

# Legacy compatibility alias
DiagramGenerator = GenericDiagramGenerator

# Additional compatibility functions that may be referenced
class C4DiagramEngine:
    """Legacy compatibility class for C4DiagramEngine"""
    def __init__(self):
        self.generator = GenericDiagramGenerator()
    
    def generate(self, *args, **kwargs):
        return self.generator.generate_container_diagram_from_story(*args, **kwargs)

def generate_archimate_container_diagram(user_story: str, **kwargs) -> str:
    """Legacy compatibility function for generate_archimate_container_diagram"""
    generator = GenericDiagramGenerator()
    result = generator.generate_container_diagram_from_story(user_story, **kwargs)
    return result.get('xml_content', '')

def xml_to_plantuml(xml_content: str) -> str:
    """Legacy compatibility function for xml_to_plantuml conversion"""
    # Placeholder implementation - actual conversion would require specific logic
    return f"@startuml\nnote as N1\n  Generated from ArchiMate XML\n  (PlantUML conversion not implemented)\nend note\n@enduml"
