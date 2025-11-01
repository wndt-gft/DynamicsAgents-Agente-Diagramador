"""
Diagram Service v2 - Serviço Unificado de Diagramas com Conformidade ao Metamodelo e Template
Integra o MetamodelCompliantC4Generator com Template SDLC para gerar diagramas completos
"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import uuid
import os
import sys

# Configurar logging no início do arquivo
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Fallback para imports relativos
try:
    # Garantir que o path atual está no sys.path
    current_dir = os.path.dirname(__file__)
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    try:
        from .generators.metamodel_compliant_generator import MetamodelCompliantC4Generator
        METAMODEL_GENERATOR_AVAILABLE = True
    except ImportError:
        METAMODEL_GENERATOR_AVAILABLE = False
        logger.warning("MetamodelCompliantC4Generator não disponível")
        class MetamodelCompliantC4Generator:  # fallback stub
            def __init__(self, *_args, **_kwargs):
                pass
            def generate_context_diagram(self, *_a, **_k):
                return ""  # noop
            def generate_container_diagram(self, *_a, **_k):
                return ""
            def generate_component_diagram(self, *_a, **_k):
                return ""
            def get_metamodel_compliance_summary(self):
                return {"compliance_score": 0, "validated_against_metamodel": False}

    try:
        from .validators.c4_quality_validator import C4MetamodelQualityValidator
        QUALITY_VALIDATOR_AVAILABLE = True
    except ImportError:
        QUALITY_VALIDATOR_AVAILABLE = False
        logger.warning("C4MetamodelQualityValidator não disponível")
        class C4MetamodelQualityValidator:  # fallback stub
            def __init__(self, *_a, **_k):
                pass
            def validate_diagram_quality(self, _xml: str):
                class Report:
                    quality_level = type("QL", (), {"value": "unknown"})
                    overall_score = 0
                    metamodel_compliance = {}
                    c4_structure_score = 0
                    naming_conventions_score = 0
                    relationships_score = 0
                    documentation_score = 0
                    is_metamodel_compliant = False
                    recommendations = []
                return Report()
            def generate_quality_badge(self, _level):
                return "N/A"

    try:
        from .generators.id_generator import NCNameIDGenerator
        ID_GENERATOR_AVAILABLE = True
    except ImportError:
        ID_GENERATOR_AVAILABLE = False
        logger.warning("NCNameIDGenerator não disponível")
        class NCNameIDGenerator:  # fallback stub
            def __init__(self):
                self._i = 0
            def generate_ncname_id(self, prefix: str = "id") -> str:
                self._i += 1
                return f"{prefix}_{self._i}"

    try:
        from .utilities.xml_integrity_enforcer import XMLIntegrityEnforcer, enforce_xml_integrity
        XML_ENFORCER_AVAILABLE = True
    except ImportError:
        XML_ENFORCER_AVAILABLE = False
        logger.warning("XMLIntegrityEnforcer não disponível")
        class XMLIntegrityEnforcer:  # fallback stub
            def enforce_integrity(self, xml_content: str, *_a, **_k):
                return True, xml_content, []
        def enforce_xml_integrity(xml_content: str):
            return True, xml_content, []

    try:
        from .utilities.template_layout_enforcer import TemplateLayoutEnforcer
        LAYOUT_ENFORCER_AVAILABLE = True
    except ImportError:
        LAYOUT_ENFORCER_AVAILABLE = False
        logger.warning("TemplateLayoutEnforcer não disponível")
        class TemplateLayoutEnforcer:  # fallback stub
            def apply_layout_from_existing_xml(self, xml: str, *_a, **_k) -> str:
                return xml
            def apply_layout_from_mapped_layers(self, *_a, **_k) -> str:
                # retorna primeiro argumento xml se fornecido, senão string vazia
                return _a[0] if _a else ''

    # Detect optional template-based generator availability
    try:
        from .generators.template_based_generator import TemplateBasedContainerGenerator  # noqa: F401
        TEMPLATE_GENERATOR_AVAILABLE = True
    except ImportError:
        TEMPLATE_GENERATOR_AVAILABLE = False
        logger.warning("TemplateBasedContainerGenerator não disponível")

    # Schema validator
    try:
        from .validators.schema_validator import ArchiMate30SchemaValidator
        SCHEMA_VALIDATOR_AVAILABLE = True
    except ImportError:
        SCHEMA_VALIDATOR_AVAILABLE = False
        logger.warning("ArchiMate30SchemaValidator não disponível")
        class ArchiMate30SchemaValidator:  # fallback stub
            def is_valid_archimate_xml(self, _xml: str) -> bool:
                return True
            def generate_validation_report(self, _xml: str) -> str:
                return ""

    # METAMODEL_AVAILABLE será True se pelo menos os componentes essenciais estiverem disponíveis
    METAMODEL_AVAILABLE = METAMODEL_GENERATOR_AVAILABLE and QUALITY_VALIDATOR_AVAILABLE

except ImportError as e:
    logger.error(f"Failed to import modules (relative): {e}")
    METAMODEL_AVAILABLE = False
    SCHEMA_VALIDATOR_AVAILABLE = False


class DiagramService:
    """Serviço principal para processamento e organização de diagramas com conformidade ao metamodelo e template"""

    def __init__(self):
        self.supported_formats = ["xml", "plantuml", "json"]

        # Initialize ID generator for XML compliance
        self.id_generator = NCNameIDGenerator() if METAMODEL_AVAILABLE else None

        # Initialize XML Integrity Enforcer
        self.xml_integrity_enforcer = XMLIntegrityEnforcer() if METAMODEL_AVAILABLE else None
        if self.xml_integrity_enforcer:
            logger.info("🔒 XML Integrity Enforcer inicializado - validação automática ativa")

        # Inicializar Template Layout Enforcer 
        self.template_enforcer = TemplateLayoutEnforcer() if METAMODEL_AVAILABLE else None
        if self.template_enforcer:
            logger.info("🔥 Template Layout Enforcer inicializado - FORÇANDO layout BV correto")

        # Inicializar gerador conforme metamodelo
        metamodel_path = os.path.join(os.path.dirname(__file__), '..', 'metamodel', 'metamodelo.xml')
        template_path = os.path.join(os.path.dirname(__file__), '..', 'template', 'Template SDLC 1.xml')
        # Normalizar caminhos para absolutos
        metamodel_path = os.path.abspath(metamodel_path)
        template_path = os.path.abspath(template_path)
        logger.info(f"📄 Caminho normalizado do metamodelo: {metamodel_path}")
        logger.info(f"📄 Caminho normalizado do template: {template_path}")

        if METAMODEL_AVAILABLE:
            self.metamodel_generator = MetamodelCompliantC4Generator(metamodel_path)
            self.quality_validator = C4MetamodelQualityValidator(metamodel_path)
            self.use_metamodel = True

            # Inicializar gerador baseado em template (opcional). Mesmo indisponível, o enforcer cobre o layout.
            if TEMPLATE_GENERATOR_AVAILABLE and os.path.exists(template_path):
                logger.info("📋 Gerador baseado em template SDLC disponível (opcional)")
                self.use_template = True
            else:
                if not os.path.exists(template_path):
                    logger.warning("⚠️ Template SDLC não encontrado - prosseguindo com enforcer")
                self.use_template = False

            logger.info("✅ Gerador de metamodelo ativo - Diagramas seguirão padrões Banco BV")
        else:
            logger.warning("⚠️ Metamodelo não disponível - usando fallback")
            self.use_metamodel = False
            self.use_template = False

        # Import generator tradicional como fallback
        try:
            from .generators.diagram_generator import (
                DiagramGenerator,
                C4DiagramEngine,
                generate_archimate_container_diagram,
                xml_to_plantuml
            )
            self.generator = DiagramGenerator()
            self.engine = C4DiagramEngine()
            self.generate_archimate_container_diagram = generate_archimate_container_diagram
            self.xml_to_plantuml = xml_to_plantuml
        except ImportError as e:
            logger.warning(f"⚠️ Diagram generator tradicional não disponível: {e}")
            self.generator = None
            self.engine = None

    def process_user_story(self, user_story: str, diagram_type: str = "container") -> Dict[str, Any]:
        """
        Processa user story completa e gera diagramas conforme metamodelo
        AGNÓSTICO - baseado APENAS no conteúdo da história fornecida

        Args:
            user_story: História do usuário
            diagram_type: Tipo do diagrama (context, container, component)

        Returns:
            Dict: Resultados completos do processamento com conformidade ao metamodelo
        """
        logger.info(f"🎯 Processando user story para diagrama {diagram_type} com conformidade ao metamodelo")

        try:
            # Usar gerador conforme metamodelo baseado na história
            if self.use_metamodel:
                xml_content = self._generate_metamodel_compliant_diagram(user_story, diagram_type)
                compliance_summary = self.metamodel_generator.get_metamodel_compliance_summary()
                logger.info(f"���� Conformidade ao metamodelo: {compliance_summary.get('compliance_score', 0)}%")
            else:
                # Fallback para engine tradicional baseado na história
                logger.warning("⚠️ Usando gerador tradicional - sem conformidade ao metamodelo")
                if self.engine:
                    xml_content, _ = self.engine.generate_diagram(user_story, diagram_type)
                    compliance_summary = {"compliance_score": 0, "message": "Metamodelo não aplicado"}
                else:
                    xml_content = self._fallback_xml_generation(user_story)
                    compliance_summary = {"compliance_score": 0, "message": "Geração de fallback"}

            # Aplicar verificação de integridade XML (corrige problemas básicos sem reordenar indevidamente)
            xml_content = self._enforce_xml_integrity(xml_content)

            # Validar ordem e containers do schema ArchiMate 3.0 - FALHAR cedo se inválido
            if SCHEMA_VALIDATOR_AVAILABLE:
                validator = ArchiMate30SchemaValidator()
                if not validator.is_valid_archimate_xml(xml_content):
                    report = validator.generate_validation_report(xml_content)
                    raise ValueError(f"XML inválido conforme schema ArchiMate 3.0:\n{report}")

            # Validar qualidade com metamodelo
            quality_report = self._validate_diagram_quality(xml_content, diagram_type)

            # Extrair mapa por layers (para a resposta textual)
            try:
                layered_mapping, layered_summary = self._extract_layers_mapping_and_summary(xml_content)
            except Exception as e:
                logger.warning(f"Não foi possível extrair mapeamento por layers: {e}")
                layered_mapping, layered_summary = {}, ""

            # Gerar metadados enriquecidos
            metadata = self._generate_enhanced_metadata(user_story, diagram_type, compliance_summary)
            metadata["layers"] = layered_mapping
            metadata["layered_summary"] = layered_summary

            # Salvar XML na pasta outputs (após passar validações)
            xml_file_path, filename = self._save_xml_to_outputs(xml_content, diagram_type, user_story)

            return {
                "success": True,
                "diagram_type": diagram_type,
                "xml_content": xml_content,
                "plantuml_content": "",  # Não gerar PlantUML por padrão
                "metadata": metadata,
                "quality_report": quality_report,
                "compliance_summary": compliance_summary,
                "metamodel_applied": self.use_metamodel,
                "user_story": user_story,
                "layered_mapping": layered_mapping,
                "layered_summary": layered_summary,
                "local_file_path": xml_file_path,
                "filename": filename
            }

        except Exception as e:
            logger.error(f"❌ Erro no processamento: {e}")
            return {
                "success": False,
                "error": str(e),
                "diagram_type": diagram_type,
                "user_story": user_story,
                "metamodel_applied": False
            }

    def _generate_metamodel_compliant_diagram(self, user_story: str, diagram_type: str) -> str:
        """Gera diagrama usando o gerador conforme metamodelo e aplica SEMPRE o template SDLC em diagramas container"""

        # Extrair nome do sistema da user story
        system_name = self._extract_system_name(user_story)

        logger.info(f"🏗️ Gerando diagrama {diagram_type} conforme metamodelo para sistema: {system_name}")

        # Primeiro, gerar com metamodelo
        xml_content = self._generate_pure_metamodel_diagram(user_story, system_name, diagram_type)

        # Importante: não realizar augmentação fixa aqui; toda inclusão deve ser inferida dinamicamente no analisador/metamodelo

        # Para diagramas de container e context aplicar o layout do template BV se o enforcer estiver disponível
        if self.template_enforcer is not None:
            if diagram_type.lower() == "context":
                logger.info("📋 Aplicando template SDLC CONTEXT VIEW após geração pelo metamodelo")
                xml_content = self.template_enforcer.apply_context_layout_from_existing_xml(xml_content, system_name)
            
            elif diagram_type.lower() == "container":
                logger.info("📋 Aplicando template SDLC CONTAINER VIEW após geração pelo metamodelo")
                xml_content = self._apply_template_layout_to_metamodel_diagram(xml_content, user_story)
        else:
            logger.info("🔧 Template SDLC não disponível - usando apenas metamodelo")

        return xml_content

    def _generate_template_and_metamodel_compliant_diagram(self, user_story: str, system_name: str,
                                                           diagram_type: str) -> str:
        """Gera diagrama que segue tanto o template SDLC quanto o metamodelo"""

        try:
            # 1. Gerar estrutura base usando o gerador de metamodelo
            base_xml = self.metamodel_generator.generate_container_diagram(user_story, system_name)

            # 2. Aplicar layout e estrutura do template SDLC
            enhanced_xml = self._apply_template_layout_to_metamodel_diagram(base_xml, user_story)

            # 3. Validar conformidade com ambos (metamodelo + template)
            self._validate_template_metamodel_integration(enhanced_xml)

            logger.info("✅ Diagrama gerado com sucesso seguindo template SDLC e metamodelo")
            return enhanced_xml

        except Exception as e:
            logger.error(f"❌ Erro na integração template+metamodelo: {e}")
            # Fallback para apenas metamodelo
            logger.info("🔄 Usando fallback apenas com metamodelo")
            return self._generate_pure_metamodel_diagram(user_story, system_name, diagram_type)

    def _generate_pure_metamodel_diagram(self, user_story: str, system_name: str, diagram_type: str) -> str:
        """Gera diagrama usando apenas o metamodelo (método original)"""

        if diagram_type.lower() == "context":
            xml_content = self.metamodel_generator.generate_context_diagram(user_story, system_name)
        elif diagram_type.lower() == "container":
            xml_content = self.metamodel_generator.generate_container_diagram(user_story, system_name)
        elif diagram_type.lower() == "component":
            xml_content = self.metamodel_generator.generate_component_diagram(user_story, system_name)
        else:
            logger.warning(f"⚠️ Tipo de diagrama desconhecido: {diagram_type}. Usando container.")
            xml_content = self.metamodel_generator.generate_container_diagram(user_story, system_name)

        # Não aplicar integridade aqui; deixar para o pipeline principal
        return xml_content

    def _apply_template_layout_to_metamodel_diagram(self, metamodel_xml: str, user_story: str) -> str:
        """FORÇA a aplicação do layout correto do template BV"""

        try:
            logger.info("🔥 FORÇANDO aplicação do template BV - Layout exato da imagem de referência")

            # SOLUÇÃO CRÍTICA: Usar o Template Layout Enforcer para forçar o layout correto
            if self.template_enforcer:
                # Extrair sistema name da user story
                system_name = self._extract_system_name(user_story)

                # APLICAR LAYOUT usando os elementos existentes (sem hardcodes)
                forced_xml = self.template_enforcer.apply_layout_from_existing_xml(metamodel_xml, system_name)

                logger.info("✅ Template BV aplicado usando elementos dinâmicos - sem hardcodes")
                return forced_xml
            else:
                logger.warning("⚠️ Template Layout Enforcer não disponível - retornando XML original")
                return metamodel_xml

        except Exception as e:
            logger.error(f"❌ Erro ao forçar aplicação do template: {e}")
            logger.warning("🔄 Usando XML original do metamodelo como fallback")
            return metamodel_xml

    def _validate_template_metamodel_integration(self, xml_content: str) -> Dict[str, Any]:
        """Valida se o diagrama atende tanto ao template quanto ao metamodelo"""

        validation_results = {
            "metamodel_compliant": False,
            "template_compliant": False,
            "integration_score": 0,
            "issues": []
        }

        try:
            # Validar conformidade com metamodelo
            if self.use_metamodel:
                quality_report = self.quality_validator.validate_diagram_quality(xml_content)
                validation_results["metamodel_compliant"] = quality_report.is_metamodel_compliant

                if not quality_report.is_metamodel_compliant:
                    validation_results["issues"].extend(quality_report.recommendations)

            # Validar conformidade com template (se disponível)
            if self.use_template:
                template_validation = self._validate_template_compliance(xml_content)
                validation_results["template_compliant"] = template_validation["compliant"]

                if not template_validation["compliant"]:
                    validation_results["issues"].extend(template_validation["issues"])

            # Calcular score de integração
            metamodel_weight = 0.7  # Metamodelo tem peso maior
            template_weight = 0.3

            score = 0
            if validation_results["metamodel_compliant"]:
                score += metamodel_weight * 100
            if validation_results["template_compliant"]:
                score += template_weight * 100

            validation_results["integration_score"] = score

            logger.info(f"📊 Score de integração template+metamodelo: {score:.1f}%")

        except Exception as e:
            logger.error(f"❌ Erro na validação de integração: {e}")
            validation_results["issues"].append(f"Erro na validação: {e}")

        return validation_results

    def _validate_template_compliance(self, xml_content: str) -> Dict[str, Any]:
        """Valida se o diagrama segue a estrutura do template SDLC"""

        validation = {
            "compliant": True,
            "issues": [],
            "template_elements_found": 0,
            "required_structure_present": False
        }

        try:
            root = ET.fromstring(xml_content)

            # Verificar se elementos típicos do template SDLC estão presentes
            elements = root.findall('.//element')

            # Elementos esperados no template SDLC
            expected_patterns = [
                'ApplicationCollaboration',  # Sistema principal
                'ApplicationComponent',  # Componentes
                'DataObject',  # Base de dados
                'BusinessActor'  # Usuários
            ]

            found_patterns = set()
            for elem in elements:
                element_type = elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
                if element_type in expected_patterns:
                    found_patterns.add(element_type)

            validation["template_elements_found"] = len(found_patterns)
            validation["required_structure_present"] = len(found_patterns) >= 2

            if not validation["required_structure_present"]:
                validation["compliant"] = False
                validation["issues"].append("Estrutura mínima do template SDLC não encontrada")

            # Verificar se há views (layouts) definidas
            views = root.findall('.//view')
            if not views:
                validation["issues"].append("Nenhuma view (layout) encontrada - template SDLC requer layout específico")

        except Exception as e:
            validation["compliant"] = False
            validation["issues"].append(f"Erro na validação do template: {e}")

        return validation

    def _fallback_xml_generation(self, user_story: str) -> str:
        """Geração XML de fallback quando engine não está disponível"""
        namespace = "http://www.opengroup.org/xsd/archimate/3.0/"

        # Generate valid NCName identifier instead of raw UUID
        model_id = self.id_generator.generate_ncname_id(
            'model') if self.id_generator else f"model_{str(uuid.uuid4()).replace('-', '')}"

        root = ET.Element("model", {
            "xmlns": namespace,
            "identifier": model_id,
            "version": "5.0.0"
        })

        # Nome do modelo
        name_elem = ET.SubElement(root, "name")
        name_elem.set("{http://www.w3.org/XML/1998/namespace}lang", "pt-br")
        name_elem.text = "Diagrama C4 - Fallback"

        # Elementos básicos
        elements_elem = ET.SubElement(root, "elements")

        # Sistema principal
        system_elem = ET.SubElement(elements_elem, "element")
        system_elem.set("identifier", "sys-001")
        system_elem.set("{http://www.w3.org/2001/XMLSchema-instance}type", "ApplicationCollaboration")

        sys_name = ET.SubElement(system_elem, "name")
        sys_name.set("{http://www.w3.org/XML/1998/namespace}lang", "pt-br")
        sys_name.text = "Sistema Principal"

        # Converter para string
        xml_str = ET.tostring(root, encoding='unicode', method='xml')
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
        return xml_declaration + xml_str

    def _extract_system_name(self, user_story: str) -> str:
        """Extrai nome do sistema da user story, evitando stopwords como 'deve'
        Ajuste: se a história mencionar PIX/SPI/DICT, usar um nome PIX claro.
        """
        try:
            story_lower = user_story.lower()
            if any(k in story_lower for k in ["pix", "spi", "dict", "banco central"]):
                return "Transferências Instantâneas via PIX"

            tokens = [t.strip('.,;:!?' ) for t in user_story.split()]
            indicators = {'sistema', 'aplicação', 'aplicacao', 'app', 'plataforma', 'portal'}
            stopwords = {
                'de', 'da', 'do', 'das', 'dos',
                'deve', 'deverá', 'devera', 'dever', 'deverao', 'deverão',
                'permitir', 'realizar', 'efetuar', 'processar', 'executar',
                'um', 'uma', 'o', 'a', 'os', 'as', 'que', 'para'
            }
            for i, tok in enumerate(tokens):
                if tok.lower() in indicators:
                    # scan ahead for first non-stopword alpha token(s)
                    j = i + 1
                    while j < len(tokens) and tokens[j].lower() in stopwords:
                        j += 1
                    if j < len(tokens):
                        name = tokens[j]
                        # include next word if it's not a stopword to make it less generic
                        k = j + 1
                        if k < len(tokens) and tokens[k].lower() not in stopwords:
                            name = f"{name} {tokens[k]}"
                        return f"Sistema {name.title()}".replace('  ', ' ').strip()
            # Fallback coerente com o template
            return "Plataforma e Produtos de Dados"
        except Exception:
            return "Plataforma e Produtos de Dados"

    def _extract_layers_mapping_and_summary(self, xml_content: str) -> tuple[dict, str]:
        """Extrai um mapeamento de elementos por layer com base no XML final.
        Usa a mesma heurística de classificação do TemplateLayoutEnforcer para manter consistência.
        Retorna (mapping, summary_text).
        """
        try:
            import xml.etree.ElementTree as ET
            # Import atualizado para nova localização em utilities
            from .utilities.template_layout_enforcer import TemplateLayoutEnforcer
            root = ET.fromstring(xml_content)
            ns = {'a': 'http://www.opengroup.org/xsd/archimate/3.0/', 'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}

            # Collect element names/types
            elements = []
            for e in root.findall('.//a:element', ns):
                etype = e.get('{http://www.w3.org/2001/XMLSchema-instance}type')
                name_el = e.find('a:name', ns)
                name = name_el.text if name_el is not None else ''
                elements.append((name, etype))

            # Classify
            enforcer = TemplateLayoutEnforcer()
            mapping: dict[str, int] = { 'channels': 0, 'gateway_inbound': 0, 'execution_logic': 0, 'gateway_outbound': 0, 'external_integration': 0, 'data_management': 0 }
            for name, etype in elements:
                layer = enforcer._classify_to_layer(name, etype)  # intentional reuse for consistency
                if layer in mapping:
                    mapping[layer] += 1

            summary = (
                f"Layers: channels={mapping['channels']}, gateway_inbound={mapping['gateway_inbound']}, "
                f"execution_logic={mapping['execution_logic']}, data_management={mapping['data_management']}, "
                f"gateway_outbound={mapping['gateway_outbound']}, external_integration={mapping['external_integration']}"
            )
            return mapping, summary
        except Exception as e:
            logger.warning(f"Falha ao extrair mapeamento por layers: {e}")
            return {}, ""

    def _save_xml_to_outputs(self, xml_content: str, diagram_type: str, user_story: str) -> tuple[str, str]:
        """Salva o XML na pasta outputs com nome único e retorna caminho e nome do arquivo"""
        try:
            # Definir diretório outputs
            outputs_dir = Path(__file__).parent.parent.parent / "outputs"
            outputs_dir.mkdir(exist_ok=True)

            # Gerar nome único do arquivo
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"diagrama_{diagram_type}_{timestamp}.xml"

            # Salvar arquivo
            xml_file_path = outputs_dir / filename
            xml_file_path.write_text(xml_content, encoding="utf-8")

            logger.info(f"💾 XML salvo em: {xml_file_path}")
            return str(xml_file_path), filename

        except Exception as e:
            logger.error(f"❌ Erro ao salvar XML: {e}")
            return "", ""

    def _validate_diagram_quality(self, xml_content: str, diagram_type: str) -> Dict[str, Any]:
        """Valida qualidade do diagrama usando o validador de metamodelo"""

        if not self.use_metamodel:
            return {
                "quality_level": "unknown",
                "score": 0,
                "message": "Validação de qualidade indisponível - metamodelo não carregado"
            }

        try:
            quality_report = self.quality_validator.validate_diagram_quality(xml_content)

            return {
                "quality_level": quality_report.quality_level.value,
                "overall_score": quality_report.overall_score,
                "metamodel_compliance": quality_report.metamodel_compliance,
                "c4_structure_score": quality_report.c4_structure_score,
                "naming_conventions_score": quality_report.naming_conventions_score,
                "relationships_score": quality_report.relationships_score,
                "documentation_score": quality_report.documentation_score,
                "is_metamodel_compliant": quality_report.is_metamodel_compliant,
                "recommendations": quality_report.recommendations,
                "quality_badge": self.quality_validator.generate_quality_badge(quality_report.quality_level)
            }

        except Exception as e:
            logger.error(f"❌ Erro na validação de qualidade: {e}")
            return {
                "quality_level": "error",
                "score": 0,
                "error": str(e)
            }

    def _generate_enhanced_metadata(self, user_story: str, diagram_type: str, compliance_summary: Dict) -> Dict[
        str, Any]:
        """Gera metadados enriquecidos com informações de conformidade"""
        metadata = {
            "diagram_type": diagram_type,
            "user_story_length": len(user_story),
            "generated_at": str(uuid.uuid4()),
            "format": "archimate_3.0",
            "tool": "metamodel_compliant_generator" if self.use_metamodel else "fallback_generator"
        }

        # Adicionar informações de conformidade
        metadata.update({
            "metamodel_compliance": {
                "score": compliance_summary.get('compliance_score', 0),
                "total_elements": compliance_summary.get('total_elements', 0),
                "total_relationships": compliance_summary.get('total_relationships', 0),
                "errors": compliance_summary.get('errors', 0),
                "warnings": compliance_summary.get('warnings', 0),
                "validated_against_metamodel": compliance_summary.get('validated_against_metamodel', False)
            },
            "bizzdesign_standards": {
                "applied": self.use_metamodel,
                "banco_bv_naming": self.use_metamodel,
                "archimate_3_0_compliant": self.use_metamodel
            },
            "template_integration": {
                "template_applied": self.use_template,
                "layout_source": "template_sdlc" if self.use_template else "metamodel_only"
            }
        })

        return metadata

    def _enforce_xml_integrity(self, xml_content: str) -> str:
        """
        Aplica verificação e correção de integridade XML automaticamente no pipeline.
        """
        if not self.xml_integrity_enforcer:
            logger.warning("⚠️ XML Integrity Enforcer não disponível - retornando XML original")
            return xml_content

        try:
            logger.info("🔒 Aplicando verificação de integridade XML...")

            # Aplicar todas as verificações e correções de integridade
            success, fixed_content, messages = self.xml_integrity_enforcer.enforce_integrity(xml_content)

            if success:
                if messages:
                    logger.info(f"✅ XML corrigido com sucesso. Correções aplicadas: {len(messages)}")
                    for message in messages:
                        logger.info(f"   - {message}")
                else:
                    logger.info("✅ XML passou na verificação de integridade sem necessidade de correções")
                return fixed_content
            else:
                logger.warning(f"⚠️ XML não pôde ser completamente corrigido. Problemas encontrados: {len(messages)}")
                for message in messages:
                    logger.warning(f"   - {message}")
                # Retornar o XML com correções parciais mesmo que não seja totalmente válido
                return fixed_content

        except Exception as e:
            logger.error(f"❌ Erro durante verificação de integridade XML: {e}")
            # Em caso de erro, retornar XML original
            return xml_content

    def validate_xml_structure(self, xml_content: str) -> Tuple[bool, List[str]]:
        """Valida estrutura XML"""
        errors = []

        try:
            ET.fromstring(xml_content)
            return True, []
        except ET.ParseError as e:
            errors.append(f"Erro de parsing XML: {e}")
            return False, errors

    def generate_diagram_summary(self, results: Dict[str, Any]) -> str:
        """Gera resumo textual do diagrama"""
        if not results.get("success"):
            return "❌ Falha na geração do diagrama"

        summary_parts = []
        summary_parts.append(f"📊 Diagrama {results.get('diagram_type', 'unknown').title()} gerado com sucesso")

        # Informações de conformidade
        if results.get("metamodel_applied"):
            compliance = results.get("compliance_summary", {})
            score = compliance.get("compliance_score", 0)
            summary_parts.append(f"🎯 Conformidade ao metamodelo: {score}%")

        # Informações de qualidade
        quality = results.get("quality_report", {})
        if quality.get("overall_score"):
            summary_parts.append(f"⭐ Qualidade geral: {quality['overall_score']:.1f}/100")
            summary_parts.append(f"🏆 Nível: {quality.get('quality_level', 'unknown').upper()}")

        return "\n".join(summary_parts)

    def organize_diagram_output(self, results: Dict[str, Any], output_dir: Path) -> List[str]:
        """Organiza saída dos diagramas em arquivos"""
        saved_files = []

        try:
            output_dir.mkdir(parents=True, exist_ok=True)

            # Salvar XML
            xml_file = output_dir / "diagram.xml"
            xml_file.write_text(results.get("xml_content", ""), encoding="utf-8")
            saved_files.append(str(xml_file))

            # Salvar PlantUML
            plantuml_file = output_dir / "diagram.puml"
            plantuml_file.write_text(results.get("plantuml_content", ""), encoding="utf-8")
            saved_files.append(str(plantuml_file))

            # Salvar metadados
            if results.get("metadata"):
                import json
                metadata_file = output_dir / "metadata.json"
                metadata_file.write_text(json.dumps(results["metadata"], indent=2), encoding="utf-8")
                saved_files.append(str(metadata_file))

        except Exception as e:
            logger.error(f"❌ Erro ao salvar arquivos: {e}")

        return saved_files

    def build_text_report(self, results: Dict[str, Any]) -> str:
        """Gera um relatório textual consistente com o XML gerado (sem suposi��ões).
        Usa os metadados calculados e o mapeamento por layers extraído do XML final.
        """
        try:
            if not results.get('success'):
                return '❌ Falha na geração do diagrama.'

            story = results.get('user_story', '')
            system_name = self._extract_system_name(story)
            title = f"DIAGRAMA CONTAINER C4 - {system_name}"

            layers = results.get('layered_mapping') or results.get('metadata', {}).get('layers', {}) or {}
            quality = results.get('quality_report', {})
            compliance = results.get('compliance_summary', {})

            lines = [title, '']
            lines.append('📊 MÉTRICAS DE QUALIDADE E CONFORMIDADE')
            lines.append(f"- Conformidade ao metamodelo: {compliance.get('compliance_score', 0)}%")
            if 'overall_score' in quality:
                lines.append(f"- Qualidade geral: {quality.get('overall_score', 0):.1f}/100 ({quality.get('quality_level', 'desconhecido')})")

            # Camadas (contagem real)
            if layers:
                lines.append('')
                lines.append('🏗️ MAPEAMENTO POR CAMADAS (contagem real)')
                lines.append(f"- Channels: {layers.get('channels', 0)}")
                lines.append(f"- Gateway Inbound: {layers.get('gateway_inbound', 0)}")
                lines.append(f"- Execution Logic: {layers.get('execution_logic', 0)}")
                lines.append(f"- Data Management: {layers.get('data_management', 0)}")
                lines.append(f"- Gateway Outbound: {layers.get('gateway_outbound', 0)}")
                lines.append(f"- External Integration: {layers.get('external_integration', 0)}")

            # Observações úteis
            lines.append('')
            if layers.get('external_integration', 0) == 0:
                lines.append('⚠️ Observação: Nenhum elemento foi classificado em External Integration nesta execução.')
            else:
                lines.append('✅ External Integration populado com integrações externas relevantes.')

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Falha ao gerar relatório textual: {e}")
            return "Relatório indisponível."

    def process_mapped_elements(self, elements: List[Dict[str, Any]], relationships: List[Dict[str, Any]],
                                diagram_type: str = "container", system_name: Optional[str] = None,
                                steps_labels: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Gera diagrama exclusivamente a partir do mapeamento EXPÍCITO do prompt.
        - Não cria elementos adicionais além dos fornecidos.
        - Normaliza IDs para NCName e preserva as referências nas relações.
        - Aplica layout do template BV apenas na view para diagramas de container.
        - Suporta diagramas de contexto (tipo 'context') construindo uma visão simplificada com
          o sistema central e os sistemas externos.
        """
        try:
            # Validação básica
            if not elements or len(elements) == 0:
                return {"success": False, "error": "Lista de elementos vazia. A ferramenta exige mapeamento explícito do prompt."}

            # Se o tipo solicitado for 'context', usar a geração simplificada
            if diagram_type and diagram_type.lower().strip() == "context":
                return self._generate_context_from_mapping(elements, relationships or [], system_name or "Sistema", steps_labels)

            # --------------------------------------------------------------------
            # Geração padrão para diagramas container/component
            # Conjuntos permitidos conforme prompt
            allowed_element_types = {
                'ApplicationCollaboration', 'ApplicationComponent', 'DataObject', 'TechnologyService'
            }
            # BusinessActor removido por requisito: não deve aparecer em nenhum layer
            skipped_actors: List[str] = []
            skipped_actor_pids: set[str] = set()

            allowed_relationship_types = {
                # Apenas versões corretas conforme ArchiMate 3.0 schema
                'Association', 'Serving', 'Aggregation', 'Composition', 'Access', 'Triggering',
                'Realization', 'Assignment', 'Specialization', 'Flow'
            }

            # Função para normalizar tipos de relacionamento para o padrão ArchiMate 3.0
            def _normalize_relationship_type(rtype: str) -> str:
                rtype_lower = rtype.lower().strip()
                normalization_map = {
                    'association': 'Association',
                    'serving': 'Serving',
                    'aggregation': 'Aggregation',
                    'composition': 'Composition',
                    'access': 'Access',
                    'triggering': 'Triggering',
                    "type": "Serving",
                    'realization': 'Realization',
                    'assignment': 'Assignment',
                    'specialization': 'Specialization',
                    'flow': 'Flow',
                    'data_flow': 'Flow',  # mapear variações
                    'dataflow': 'Flow',
                    'uses': 'Serving',
                    'usa': 'Serving',
                    'calls': 'Triggering',
                    'connects': 'Association',
                    'http/rest': 'Serving',
                    'http': 'Serving',
                    'rest': 'Serving',
                    'api': 'Serving',
                    'web service': 'Serving',
                    'webservice': 'Serving',
                }
                return normalization_map.get(rtype_lower, rtype)

            # Mapear IDs do prompt -> IDs NCName válidos para XML
            id_map: Dict[str, str] = {}
            def _gen_id(prefix: str) -> str:
                if self.id_generator:
                    return self.id_generator.generate_ncname_id(prefix)
                import uuid
                return f"{prefix}_{uuid.uuid4().hex}"

            # Criar modelo ArchiMate mínimo com elementos/relacionamentos fornecidos
            ns = {
                'a': 'http://www.opengroup.org/xsd/archimate/3.0/',
                'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
            }
            root = ET.Element('model', {
                'xmlns': ns['a'],
                'xmlns:dc': 'http://purl.org/dc/elements/1.1/',
                'xmlns:xsi': ns['xsi'],
                'identifier': _gen_id('model')
            })
            ET.SubElement(root, 'name', {'xml:lang': 'pt-br'}).text = (system_name or 'Diagrama Container').strip()

            elems_node = ET.SubElement(root, 'elements')

            # Preparar buckets por layer respeitando o mapeamento explícito e ordem de chegada
            def _norm_layer(val: Optional[str]) -> str:
                v = (val or '').strip().lower().replace('-', ' ').replace('_', ' ')
                if v in {'channels', 'canal', 'canais'}:
                    return 'channels'
                if v in {'gateway inbound', 'gatewayinbound', 'inbound', 'entrada'}:
                    return 'gateway_inbound'
                if v in {'execution logic', 'execution', 'logic', 'processamento'}:
                    return 'execution_logic'
                if v in {'data management', 'dados', 'data', 'storage'}:
                    return 'data_management'
                if v in {'gateway outbound', 'gatewayoutbound', 'outbound', 'saida', 'saída'}:
                    return 'gateway_outbound'
                if v in {'external integration layer', 'external integration', 'externo', 'integracao externa', 'integração externa'}:
                    return 'external_integration'
                return 'execution_logic'

            by_layer: Dict[str, List[tuple[str, str, str]]] = {
                'channels': [], 'gateway_inbound': [], 'execution_logic': [],
                'data_management': [], 'gateway_outbound': [], 'external_integration': []
            }

            # Normalizar elementos
            element_name_by_xml_id: Dict[str, str] = {}
            for el in elements:
                pid = str(el.get('id') or el.get('identifier') or _gen_id('e'))
                name = str(el.get('name') or '').strip()
                etype = str(el.get('type') or '').strip()
                layer = str(el.get('layer') or '').strip()
                doc = str(el.get('doc') or el.get('documentation') or '').strip()

                # ignorar BusinessActor completamente
                if etype == 'BusinessActor':
                    skipped_actors.append(name or pid)
                    skipped_actor_pids.add(pid)
                    continue

                if not name or not etype:
                    return {"success": False, "error": f"Elemento inválido (name/type obrigatórios): {el}"}
                if etype not in allowed_element_types:
                    return {"success": False, "error": f"Tipo de elemento não permitido pelo metamodelo: {etype}"}

                xml_id = _gen_id('id')
                id_map[pid] = xml_id
                e = ET.SubElement(elems_node, 'element', {
                    'identifier': xml_id,
                    '{http://www.w3.org/2001/XMLSchema-instance}type': etype
                })
                ET.SubElement(e, 'name', {'xml:lang': 'pt-br'}).text = name
                if doc:
                    ET.SubElement(e, 'documentation').text = doc

                norm_layer = _norm_layer(layer)
                if norm_layer in by_layer:
                    by_layer[norm_layer].append((xml_id, name, etype))
                else:
                    by_layer['execution_logic'].append((xml_id, name, etype))
                element_name_by_xml_id[xml_id] = name

            # Relacionamentos
            rels_node: Optional[ET.Element] = None
            relationships_in: List[tuple[str, str, str, str]] = []
            for rel in relationships or []:
                src_pid = rel.get('source_id') or rel.get('source')
                tgt_pid = rel.get('target_id') or rel.get('target')
                rtype = (rel.get('type') or '').strip()
                rationale = (rel.get('rationale') or rel.get('name') or '').strip()

                normalized_rtype = _normalize_relationship_type(rtype)

                if not src_pid or not tgt_pid or not rtype:
                    return {"success": False, "error": f"Relacionamento inválido (source_id/target_id/type obrigatórios): {rel}"}
                if normalized_rtype not in allowed_relationship_types:
                    return {"success": False, "error": f"Tipo de relacionamento não permitido pelo metamodelo: {rtype} (normalizado: {normalized_rtype})"}
                if src_pid in skipped_actor_pids or tgt_pid in skipped_actor_pids:
                    continue
                src_xml = id_map.get(str(src_pid))
                tgt_xml = id_map.get(str(tgt_pid))
                if not src_xml or not tgt_xml:
                    continue
                rid = _gen_id('rel')
                relationships_in.append((rid, src_xml, tgt_xml, normalized_rtype))
                if rels_node is None:
                    rels_node = ET.SubElement(root, 'relationships')
                r = ET.SubElement(rels_node, 'relationship', {
                    'identifier': rid,
                    'source': src_xml,
                    'target': tgt_xml,
                    '{http://www.w3.org/2001/XMLSchema-instance}type': normalized_rtype
                })
                ET.SubElement(r, 'name', {'xml:lang': 'pt-br'}).text = rationale

            # validação leve de camadas (gateway inbound sem channels)
            try:
                has_channels = len(by_layer['channels']) > 0
                has_inbound = len(by_layer['gateway_inbound']) > 0
                if not has_channels and has_inbound:
                    return {"success": False, "error": "Mapeamento inválido: existe GATEWAY INBOUND sem CHANNELS."}
            except Exception:
                pass

            if skipped_actors:
                logger.info(f"👤 {len(skipped_actors)} BusinessActor(s) removidos do diagrama: {', '.join(skipped_actors[:5])}{'...' if len(skipped_actors) > 5 else ''}")

            # Aplicar verificação de integridade e layout do template somente para container
            xml_content = ET.tostring(root, encoding='unicode', method='xml')
            xml_content = self._enforce_xml_integrity(xml_content)

            if diagram_type.lower() == 'context' and self.template_enforcer is not None:
                logger.info("📋 Aplicando template SDLC CONTEXT VIEW para diagrama de contexto")
                xml_content = self.template_enforcer.apply_context_layout_from_existing_xml(xml_content, system_name or 'Sistema')
                xml_content = self._enforce_xml_integrity(xml_content)
            elif diagram_type.lower() == 'container' and self.template_enforcer is not None:
                logger.info("📋 Aplicando template SDLC CONTAINER VIEW para diagrama container")
                # Usar os buckets por layer EXATAMENTE como fornecidos e etapas textuais do prompt (se fornecidas)
                xml_content = self.template_enforcer.apply_layout_from_mapped_layers(by_layer, relationships_in, system_name or 'Sistema', steps_labels)
                xml_content = self._enforce_xml_integrity(xml_content)
            else:
                logger.info("🔧 Template SDLC não aplicado (tipo não reconhecido ou enforcer indisponível)")

            # validação de schema
            if SCHEMA_VALIDATOR_AVAILABLE:
                validator = ArchiMate30SchemaValidator()
                if not validator.is_valid_archimate_xml(xml_content):
                    report = validator.generate_validation_report(xml_content)
                    return {"success": False, "error": f"XML inválido conforme schema ArchiMate 3.0:\n{report}"}

            # Relatório de qualidade
            quality_report = self._validate_diagram_quality(xml_content, diagram_type)
            try:
                layered_mapping, layered_summary = self._extract_layers_mapping_and_summary(xml_content)
            except Exception:
                layered_mapping, layered_summary = {}, ""

            metadata = {
                "diagram_type": diagram_type,
                "source": "prompt_mapping",
                "total_elements": len(elements),
                "total_relationships": len(relationships or []),
                "layers": layered_mapping,
                "layered_summary": layered_summary,
                "metamodel_applied": self.use_metamodel
            }

            # salvar
            xml_file_path, filename = self._save_xml_to_outputs(xml_content, diagram_type, system_name or '')

            return {
                "success": True,
                "diagram_type": diagram_type,
                "xml_content": xml_content,
                "metadata": metadata,
                "quality_report": quality_report,
                "compliance_summary": self.metamodel_generator.get_metamodel_compliance_summary() if self.use_metamodel else {"compliance_score": 0},
                "metamodel_applied": self.use_metamodel,
                "layered_mapping": layered_mapping,
                "layered_summary": layered_summary,
                "local_file_path": xml_file_path,
                "filename": filename
            }

        except Exception as e:
            logger.error(f"Erro ao processar mapeamento explícito: {e}")
            return {"success": False, "error": str(e)}

    def _generate_context_from_mapping(self, elements: List[Dict[str, Any]], relationships: List[Dict[str, Any]], system_name: str, steps_labels: Optional[List[str]]) -> Dict[str, Any]:
        """
        Gera um diagrama de contexto simplificado a partir de elementos e relacionamentos.

        Considera apenas elementos do tipo ApplicationCollaboration para contexto, onde o primeiro
        elemento desse tipo é tratado como sistema central e os demais como sistemas externos.
        Os relacionamentos entre externos e o sistema central serão do tipo 'Serving'.
        """
        try:
            # Filtrar elementos ApplicationCollaboration
            app_collab = [el for el in elements if str(el.get('type')) == 'ApplicationCollaboration']
            if not app_collab:
                return {"success": False, "error": "Diagrama de contexto requer pelo menos um ApplicationCollaboration."}
            # Primeiro é sistema central
            system_el = app_collab[0]
            external_els = app_collab[1:]

            # Gerar ids determinísticos
            def _gen(prefix: str) -> str:
                if self.id_generator:
                    return self.id_generator.generate_ncname_id(prefix)
                import uuid
                return f"{prefix}_{uuid.uuid4().hex}"

            model_id = _gen('model')
            root = ET.Element('model', {
                'xmlns': 'http://www.opengroup.org/xsd/archimate/3.0/',
                'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
                'xsi:schemaLocation': 'http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.0/archimate3_Diagram.xsd',
                'identifier': model_id
            })
            ET.SubElement(root, 'name', {'xml:lang': 'pt-br'}).text = f"Diagrama de Contexto - {system_name}"

            elems_node = ET.SubElement(root, 'elements')
            rels_node: Optional[ET.Element] = None

            id_map: Dict[str, str] = {}

            # adicionar sistema central
            sys_pid = str(system_el.get('id') or system_el.get('identifier'))
            sys_xml = _gen('id')
            id_map[sys_pid] = sys_xml
            e = ET.SubElement(elems_node, 'element', {
                'identifier': sys_xml,
                '{http://www.w3.org/2001/XMLSchema-instance}type': 'ApplicationCollaboration'
            })
            ET.SubElement(e, 'name', {'xml:lang': 'pt-br'}).text = str(system_el.get('name'))

            # adicionar externos
            for ext in external_els:
                pid = str(ext.get('id') or ext.get('identifier'))
                xml_id = _gen('id')
                id_map[pid] = xml_id
                elem = ET.SubElement(elems_node, 'element', {
                    'identifier': xml_id,
                    '{http://www.w3.org/2001/XMLSchema-instance}type': 'ApplicationCollaboration'
                })
                ET.SubElement(elem, 'name', {'xml:lang': 'pt-br'}).text = str(ext.get('name'))

                # criar relacionamento do externo para o sistema central (Serving)
                rid = _gen('rel')
                if rels_node is None:
                    rels_node = ET.SubElement(root, 'relationships')
                rel = ET.SubElement(rels_node, 'relationship', {
                    'identifier': rid,
                    'source': xml_id,
                    'target': sys_xml,
                    '{http://www.w3.org/2001/XMLSchema-instance}type': 'Serving'
                })
                ET.SubElement(rel, 'name', {'xml:lang': 'pt-br'}).text = 'Interação de alto nível'

            # Construir view
            views = ET.SubElement(root, 'views')
            diagrams = ET.SubElement(views, 'diagrams')
            view_id = _gen('view')
            view = ET.SubElement(diagrams, 'view', {
                'identifier': view_id,
                '{http://www.opengroup.org/xsd/archimate/3.0/}viewpoint': 'Introductory',
                '{http://www.w3.org/2001/XMLSchema-instance}type': 'Diagram'
            })
            ET.SubElement(view, 'name', {'xml:lang': 'pt-br'}).text = f"Visão de Contexto – {system_name}"

            # posicional externos
            for i, ext in enumerate(external_els):
                pid = str(ext.get('id') or ext.get('identifier'))
                node = ET.SubElement(view, 'node', {
                    'identifier': _gen('vis'),
                    'elementRef': id_map[pid],
                    'x': str(60),
                    'y': str(200 + i*60),
                    'w': '200', 'h': '50',
                    '{http://www.w3.org/2001/XMLSchema-instance}type': 'Element'
                })
                style = ET.SubElement(node, 'style')
                ET.SubElement(style, 'fillColor', {'r':'184','g':'231','b':'252','a':'100'})
                ET.SubElement(style, 'lineColor', {'r':'128','g':'128','b':'128','a':'100'})
                font = ET.SubElement(style, 'font', {'name':'Arial','size':'10'})
                ET.SubElement(font, 'color', {'r':'0','g':'0','b':'0'})

            # sistema central
            node_sys = ET.SubElement(view, 'node', {
                'identifier': _gen('vis'),
                'elementRef': sys_xml,
                'x': '400', 'y': '300', 'w': '250', 'h': '80',
                '{http://www.w3.org/2001/XMLSchema-instance}type': 'Element'
            })
            style = ET.SubElement(node_sys, 'style')
            ET.SubElement(style, 'fillColor', {'r':'184','g':'231','b':'252','a':'100'})
            ET.SubElement(style, 'lineColor', {'r':'128','g':'128','b':'128','a':'100'})
            font = ET.SubElement(style, 'font', {'name':'Arial','size':'10'})
            ET.SubElement(font, 'color', {'r':'0','g':'0','b':'0'})

            # etapas se houverem
            if steps_labels:
                container = ET.SubElement(view, 'node', {
                    'identifier': _gen('cont'),
                    'x': '700', 'y': '180', 'w': '300', 'h': '300',
                    '{http://www.w3.org/2001/XMLSchema-instance}type': 'Container'
                })
                ET.SubElement(container, 'label', {'xml:lang': 'pt-br'}).text = 'Etapas'
                style = ET.SubElement(container, 'style')
                ET.SubElement(style, 'fillColor', {'r':'255','g':'255','b':'255','a':'100'})
                ET.SubElement(style, 'lineColor', {'r':'128','g':'128','b':'128','a':'100'})
                font = ET.SubElement(style, 'font', {'name':'Arial','size':'10'})
                ET.SubElement(font, 'color', {'r':'0','g':'0','b':'0'})
                for idx, step in enumerate(steps_labels, start=1):
                    s_node = ET.SubElement(view, 'node', {
                        'identifier': _gen('etapa'),
                        'x': '720', 'y': str(210 + 20*(idx-1)), 'w': '260', 'h': '20',
                        '{http://www.w3.org/2001/XMLSchema-instance}type': 'Label'
                    })
                    ET.SubElement(s_node, 'label', {'xml:lang': 'pt-br'}).text = f'{idx}. {step}'
                    st = ET.SubElement(s_node, 'style')
                    ET.SubElement(st, 'fillColor', {'r':'255','g':'255','b':'255','a':'0'})
                    ET.SubElement(st, 'lineColor', {'r':'0','g':'0','b':'0','a':'0'})
                    font = ET.SubElement(st, 'font', {'name':'arial','size':'10','style':'plain'})
                    ET.SubElement(font, 'color', {'r':'0','g':'0','b':'0','a':'100'})

            # Enforce integrity
            xml_content = ET.tostring(root, encoding='unicode')
            xml_content = self._enforce_xml_integrity(xml_content)


        # ============================================================================
        # 🔥 CRÍTICO: APLICAR TEMPLATE ENFORCER ANTES DE SALVAR
        # ============================================================================
            if self.template_enforcer is not None:
                logger.info("📋 Aplicando template SDLC CONTEXT VIEW para diagrama de contexto gerado por mapeamento")
                try:
                    xml_content = self.template_enforcer.apply_context_layout_from_existing_xml(xml_content, system_name)
                    logger.info("✅ Template SDLC CONTEXT VIEW aplicado com sucesso")
                    
                    # IMPORTANTE: Re-aplicar integrity após template enforcer (ele pode adicionar novos elementos)
                    xml_content = self._enforce_xml_integrity(xml_content)
                except Exception as e:
                    logger.error(f"❌ Erro ao aplicar template context: {e}")
                    logger.warning("⚠️  Continuando com XML sem template")
            else:
                logger.warning("🔧 Template enforcer não disponível - XML sem layout do template")

            # Salvar arquivo na pasta outputs
            xml_file_path, filename = self._save_xml_to_outputs(xml_content, 'context', system_name)
            return {
                "success": True,
                "diagram_type": "context",
                "xml_content": xml_content,
                "metadata": {
                    "diagram_type": 'context',
                    "total_elements": len(app_collab),
                    "total_relationships": len(external_els),
                    "metamodel_applied": self.use_metamodel
                },
                "quality_report": self._validate_diagram_quality(xml_content, 'context'),
                "compliance_summary": {"compliance_score": 0},
                "metamodel_applied": self.use_metamodel,
                "layered_mapping": {},
                "layered_summary": "",
                "local_file_path": xml_file_path,
                "filename": filename
            }
        except Exception as ex:
            logger.error(f"Erro ao gerar contexto: {ex}")
            return {"success": False, "error": str(ex)}

# ===== FUNÇÕES DE CONVENIÊNCIA =====

def process_user_story_to_diagram(user_story: str, output_dir: Path = None,
                                  diagram_type: str = "container") -> Dict[str, Any]:
    """
    Função de conveniência para processamento completo de user story
    """
    service = DiagramService()
    results = service.process_user_story(user_story, diagram_type)

    if output_dir and results.get("success"):
        saved_files = service.organize_diagram_output(results, output_dir)
        results["saved_files"] = saved_files

    return results


def validate_diagram_xml(xml_content: str) -> Tuple[bool, List[str]]:
    """
    Função de conveniência para validação de XML
    """
    service = DiagramService()
    return service.validate_xml_structure(xml_content)


def generate_diagram_summary(xml_content: str) -> str:
    """
    Função de conveniência para gerar resumo do diagrama
    """
    service = DiagramService()
    results = {"success": True, "xml_content": xml_content}
    return service.generate_diagram_summary(results)

def process_mapped_elements(elements: List[Dict[str, Any]], relationships: List[Dict[str, Any]], diagram_type: str = "container", system_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Função de conveniência para gerar diagrama a partir de mapeamento explícito de elementos e relacionamentos
    Respeita regras específicas para canais, gateways e autenticação.

    Args:
        elements: Lista de elementos mapeados
        relationships: Lista de relacionamentos mapeados
        diagram_type: Tipo do diagrama (context, container, component)
        system_name: Nome do sistema (opcional)

    Returns:
        Dict: Resultados do processamento a partir do mapeamento
    """
    service = DiagramService()
    results = service.process_mapped_elements(elements, relationships, diagram_type, system_name)
    return results
