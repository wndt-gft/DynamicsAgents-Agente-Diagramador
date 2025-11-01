"""
Template-based Container Diagram Generator
Gera diagramas de Container seguindo estritamente o template fornecido
sem hardcodes de domínio
"""

import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional, Set
from .id_generator import NCNameIDGenerator

# Classes para elementos ArchiMate
class ArchiMateElement:
    """Representa um elemento ArchiMate"""
    def __init__(self, identifier: str, name: str, element_type: str, documentation: str = "", properties: Dict = None):
        self.identifier = identifier
        self.name = name
        self.element_type = element_type
        self.documentation = documentation
        self.properties = properties or {}

class ArchiMateRelationship:
    """Representa um relacionamento ArchiMate"""
    def __init__(self, identifier: str, source: str, target: str, relation_type: str, name: str = ""):
        self.identifier = identifier
        self.source = source
        self.target = target
        self.relation_type = relation_type
        self.name = name

class TemplateBasedContainerGenerator:
    """Gerador de diagramas baseado em template"""

    def __init__(self):
        self.template_root: Optional[ET.Element] = None
        self.id_generator = NCNameIDGenerator()
        self.logger = logging.getLogger(__name__)

        # Inicializar atributos necessários
        self.elements: List[ArchiMateElement] = []
        self.relationships: List[ArchiMateRelationship] = []
        self.template_layout = self._define_template_layout()
        self.template_structure = None

        # Sistema completo de validação de integridade referencial
        self.created_element_ids: Set[str] = set()
        self.created_relationship_ids: Set[str] = set()
        self.validation_errors: List[str] = []
        self.element_id_map: Dict[str, str] = {}
        self.pending_relationships: List[Dict] = []
        # Novo: mapear ID->nome e ID->visualNodeId para conexões corretas
        self.element_name_by_id: Dict[str, str] = {}
        self.visual_node_id_by_element_id: Dict[str, str] = {}
        # Header dinâmico (título/subtítulo) vindo da análise
        self.dynamic_header: Optional[Dict[str, str]] = None

    def _define_template_layout(self) -> Dict[str, Any]:
        """Define the EXACT layout coordinates from Template SDLC 1.xml following official structure"""
        return {
            'canvas': {'width': 1667, 'height': 900},
            'header': {
                # EXACT coordinates from Template SDLC 1.xml
                'title': {'x': 127, 'y': 47, 'w': 707, 'h': 40, 'text': 'Plataforma e Produtos de Dados', 'size': 24, 'style': 'bold'},
                'subtitle': {'x': 127, 'y': 87, 'w': 700, 'h': 33, 'text': 'Visão de container - Ingestões, Transformações, Experimentações, Análises e Visualização de Dados do SDLC', 'size': 16, 'style': 'plain'}
            },
            'layers': {
                # EXACT coordinates from Template SDLC 1.xml - id-1328072
                'channels': {
                    'x': 67, 'y': 193, 'w': 200, 'h': 627,
                    'title': 'CHANNELS',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'elements_per_row': 1,
                    'element_width': 180,
                    'element_height': 50,
                    'vertical_spacing': 15,
                    'horizontal_padding': 10,
                    'vertical_padding': 40
                },
                # EXACT coordinates from Template SDLC 1.xml - id-1328066
                'gateway_inbound': {
                    'x': 273, 'y': 193, 'w': 200, 'h': 627,
                    'title': 'GATEWAY INBOUND',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'elements_per_row': 1,
                    'element_width': 180,
                    'element_height': 50,
                    'vertical_spacing': 15,
                    'horizontal_padding': 10,
                    'vertical_padding': 40
                },
                # EXACT coordinates from Template SDLC 1.xml - id-1328068
                'execution_logic': {
                    'x': 480, 'y': 193, 'w': 533, 'h': 500,
                    'title': 'EXECUTION LOGIC',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'elements_per_row': 2,
                    'element_width': 250,
                    'element_height': 60,
                    'vertical_spacing': 15,
                    'horizontal_spacing': 20,
                    'horizontal_padding': 15,
                    'vertical_padding': 40
                },
                # EXACT coordinates from Template SDLC 1.xml - id-1328078
                'gateway_outbound': {
                    'x': 1020, 'y': 193, 'w': 173, 'h': 627,
                    'title': 'GATEWAY OUTBOUND',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'elements_per_row': 1,
                    'element_width': 153,
                    'element_height': 50,
                    'vertical_spacing': 15,
                    'horizontal_padding': 10,
                    'vertical_padding': 40
                },
                # EXACT coordinates from Template SDLC 1.xml - id-1328074
                'external_integration': {
                    'x': 1200, 'y': 193, 'w': 200, 'h': 627,
                    'title': 'EXTERNAL INTEGRATION LAYER',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'elements_per_row': 1,
                    'element_width': 180,
                    'element_height': 50,
                    'vertical_spacing': 15,
                    'horizontal_padding': 10,
                    'vertical_padding': 40
                },
                # EXACT coordinates from Template SDLC 1.xml - id-1328081
                'data_management': {
                    'x': 480, 'y': 700, 'w': 533, 'h': 120,
                    'title': 'DATA MANAGEMENT',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'elements_per_row': 2,
                    'element_width': 250,
                    'element_height': 40,
                    'vertical_spacing': 10,
                    'horizontal_spacing': 20,
                    'horizontal_padding': 15,
                    'vertical_padding': 35
                },
                # EXACT coordinates from Template SDLC 1.xml - id-1328077
                'etapas': {
                    'x': 1407, 'y': 193, 'w': 260, 'h': 627,
                    'title': 'Etapas',
                    'color': {'fill': (255, 255, 255, 100), 'line': (128, 128, 128, 100)},
                    'note_text': 'Regras Aplicadas:   Observações:',
                    'note_x': 1420, 'note_y': 227, 'note_w': 233, 'note_h': 220
                }
            }
        }

    def load_template(self, template_path: str):
        """Load template from file path (compatibility method)"""
        try:
            self._load_template_structure(template_path)
            self.logger.info(f"✅ Template carregado de: {template_path}")
        except Exception as e:
            self.logger.error(f"❌ Erro ao carregar template: {str(e)}")

    def _load_template_structure(self, template_path: str):
        """Load the official SDLC template structure"""
        try:
            import os
            if not os.path.exists(template_path):
                self.logger.warning(f"⚠️ Template não encontrado: {template_path}")
                return

            tree = ET.parse(template_path)
            self.template_root = tree.getroot()
            self.logger.info("✅ Template SDLC 1.xml carregado com sucesso")

        except Exception as e:
            self.logger.error(f"❌ Erro ao carregar template: {str(e)}")

    def generate_container_diagram_from_template(self, analysis: Dict[str, Any]) -> str:
        """Generate container diagram following EXACT SDLC template layout"""
        try:
            self.logger.info("🎯 Iniciando geração de diagrama baseado no Template SDLC 1.xml oficial")

            # Resetar state
            self._reset_state()

            # Guardar header dinâmico se existir
            self.dynamic_header = analysis.get('header') or None

            # Extrair containers da análise
            containers = self._extract_containers_from_analysis(analysis)
            if not containers:
                raise ValueError("Nenhum container encontrado na análise")

            # Classificar containers por layer seguindo Template SDLC 1.xml
            classified_containers = self._classify_containers_by_layer(containers)

            # Criar elementos por layer
            self._create_layer_containers(classified_containers, analysis.get('system_name', 'Sistema'))

            # Criar relacionamentos
            self._create_relationships_from_analysis(analysis)

            # Gerar XML seguindo template EXATO
            diagram_xml = self._generate_exact_template_xml(analysis.get('system_name', 'Sistema'), header=self.dynamic_header)

            self.logger.info("✅ Diagrama container gerado com sucesso seguindo Template SDLC 1.xml")
            return diagram_xml

        except Exception as e:
            self.logger.error(f"❌ Erro na geração do diagrama: {str(e)}")
            raise

    def _reset_state(self):
        """Reset internal state for new diagram generation"""
        self.elements.clear()
        self.relationships.clear()
        self.created_element_ids.clear()
        self.created_relationship_ids.clear()
        self.validation_errors.clear()
        self.element_id_map.clear()
        self.pending_relationships.clear()
        self.element_name_by_id.clear()
        self.visual_node_id_by_element_id.clear()

    def _extract_containers_from_analysis(self, analysis: Dict[str, Any]) -> List[Dict]:
        """Extract containers from analysis results"""
        containers = []

        # Extrair de containers diretos
        if 'containers' in analysis:
            containers.extend(analysis['containers'])

        # Extrair de componentes identificados
        if 'components' in analysis:
            for comp in analysis['components']:
                container = {
                    'name': comp.get('name', ''),
                    'type': comp.get('type', 'application-component'),
                    'description': comp.get('description', ''),
                    'technology': comp.get('technology', ''),
                    'layer': self._determine_layer_from_component(comp)
                }
                containers.append(container)

        # Extrair de elementos identificados
        if 'elements' in analysis:
            for elem in analysis['elements']:
                if elem.get('type') in ['application-component', 'application-service']:
                    container = {
                        'name': elem.get('name', ''),
                        'type': elem.get('type', 'application-component'),
                        'description': elem.get('description', ''),
                        'technology': elem.get('technology', ''),
                        'layer': self._determine_layer_from_element(elem)
                    }
                    containers.append(container)

        self.logger.info(f"📦 Extraídos {len(containers)} containers da análise")
        return containers

    def _determine_layer_from_component(self, comp: Dict) -> str:
        """Determine the appropriate layer for a component"""
        name = comp.get('name', '').lower()
        comp_type = comp.get('type', '').lower()
        description = comp.get('description', '').lower()

        # Regras de classificação baseadas no Template SDLC 1.xml
        if any(term in name for term in ['api', 'interface', 'endpoint', 'channel']):
            return 'channels'
        elif any(term in name for term in ['gateway', 'proxy', 'load balancer']):
            if any(term in name for term in ['inbound', 'entrada', 'input']):
                return 'gateway_inbound'
            else:
                return 'gateway_outbound'
        elif any(term in name for term in ['external', 'third party', 'terceiro']):
            return 'external_integration'
        elif any(term in name for term in ['database', 'storage', 'dados', 'bd']):
            return 'data_management'
        else:
            return 'execution_logic'

    def _determine_layer_from_element(self, elem: Dict) -> str:
        """Determine the appropriate layer for an element"""
        return self._determine_layer_from_component(elem)

    def _classify_containers_by_layer(self, containers: List[Dict]) -> Dict[str, List[Dict]]:
        """Classify containers by their appropriate layer"""
        classified = {
            'channels': [],
            'gateway_inbound': [],
            'execution_logic': [],
            'gateway_outbound': [],
            'external_integration': [],
            'data_management': []
        }

        for container in containers:
            layer = container.get('layer', 'execution_logic')
            if layer in classified:
                classified[layer].append(container)
            else:
                classified['execution_logic'].append(container)

        # Log da classificação
        for layer, items in classified.items():
            if items:
                self.logger.info(f"🏗️ Layer {layer}: {len(items)} containers")

        return classified

    def _generate_unique_element_id(self, base_name: str) -> str:
        """Generate unique element ID ensuring no conflicts"""
        element_id = self.id_generator.generate_element_id(base_name)

        # Garantir unicidade absoluta
        counter = 1
        original_id = element_id
        while element_id in self.created_element_ids:
            element_id = f"{original_id}_{counter}"
            counter += 1

        self.created_element_ids.add(element_id)
        return element_id

    def _generate_unique_relationship_id(self, source: str, target: str) -> str:
        """Generate unique relationship ID ensuring no conflicts"""
        rel_id = self.id_generator.generate_relationship_id(source, target)

        # Garantir unicidade absoluta
        counter = 1
        original_id = rel_id
        while rel_id in self.created_relationship_ids:
            rel_id = f"{original_id}-{counter}"
            counter += 1

        self.created_relationship_ids.add(rel_id)
        return rel_id

    def _create_layer_containers(self, classified_containers: Dict[str, List[Dict]], system_name: str):
        """Create container elements for each layer seguindo EXATAMENTE o Template SDLC 1.xml"""
        self.logger.info("🏗️ Criando containers por camada seguindo Template SDLC 1.xml oficial")

        for layer_name, containers in classified_containers.items():
            if not containers:
                self.logger.debug(f"⏭️ Pulando layer {layer_name} - sem containers")
                continue

            layer_config = self.template_layout['layers'].get(layer_name, {})
            if not layer_config:
                self.logger.warning(f"⚠️ Configuração de layer não encontrada: {layer_name}")
                continue

            self.logger.info(f"🏗️ Criando {len(containers)} containers para layer {layer_name}")

            for i, container in enumerate(containers):
                element_id = self._generate_unique_element_id(container['name'])

                # Criar elemento ArchiMate
                element = ArchiMateElement(
                    identifier=element_id,
                    name=container['name'],
                    element_type='application-component',
                    documentation=container.get('description', ''),
                    properties={
                        'technology': container.get('technology', ''),
                        'layer': layer_name,
                        'color': layer_config['color']['fill']
                    }
                )

                self.elements.append(element)
                self.element_id_map[container['name']] = element_id
                self.element_name_by_id[element_id] = container['name']

                self.logger.debug(f"✅ Container criado: {container['name']} (ID: {element_id})")

    def _create_relationships_from_analysis(self, analysis: Dict[str, Any]):
        """Create relationships based on analysis"""
        self.logger.info("🔗 Criando relacionamentos entre containers")

        # Processar relacionamentos explícitos
        if 'relationships' in analysis:
            for rel in analysis['relationships']:
                self._create_relationship_from_data(rel)

        # Criar relacionamentos implícitos baseados em padrões
        self._create_implicit_relationships()

        # Garantir ao menos um relacionamento para conformidade com schema
        if not self.relationships and len(self.elements) >= 2:
            src = self.elements[0].identifier
            tgt = self.elements[1].identifier
            rel_id = self._generate_unique_relationship_id(src, tgt)
            name = f"Integração {self.element_name_by_id.get(src, src)} → {self.element_name_by_id.get(tgt, tgt)}"
            self.relationships.append(ArchiMateRelationship(
                identifier=rel_id,
                source=src,
                target=tgt,
                relation_type='Serving',
                name=name
            ))
            self.logger.info("➕ Relacionamento padrão adicionado para atender o schema")

    def _normalize_relation_type(self, rel_type: str) -> str:
        """Normaliza o tipo de relacionamento para o casing esperado (ArchiMate 3.0)"""
        if not rel_type:
            return 'Serving'
        mapping = {
            'serving': 'Serving',
            'triggering': 'Triggering',
            'flow': 'Flow',
            'access': 'Access',
            'association': 'Association',
            'aggregation': 'Aggregation',
            'composition': 'Composition',
            'realization': 'Realization',
            'specialization': 'Specialization',
            'assignment': 'Assignment',
            'influence': 'Influence'
        }
        key = str(rel_type).strip().lower()
        return mapping.get(key, 'Serving')

    def _create_relationship_from_data(self, rel_data: Dict):
        """Create a relationship from relationship data"""
        source_name = rel_data.get('source', '')
        target_name = rel_data.get('target', '')

        # Verificar se os elementos existem
        source_id = self.element_id_map.get(source_name)
        target_id = self.element_id_map.get(target_name)

        if not source_id or not target_id:
            self.logger.warning(f"⚠️ Relacionamento ignorado: {source_name} -> {target_name} (elementos não encontrados)")
            return

        # Criar relacionamento
        rel_id = self._generate_unique_relationship_id(source_id, target_id)
        relationship = ArchiMateRelationship(
            identifier=rel_id,
            source=source_id,
            target=target_id,
            relation_type=self._normalize_relation_type(rel_data.get('type', 'serving')),
            name=rel_data.get('name') or f"Integração {source_name} → {target_name}"
        )

        self.relationships.append(relationship)
        self.logger.debug(f"✅ Relacionamento criado: {source_name} -> {target_name}")

    def _create_implicit_relationships(self):
        """Create implicit relationships between layers to avoid empty relationship sets"""
        if not self.elements:
            return
        # Agrupar elementos por layer
        by_layer: Dict[str, List[ArchiMateElement]] = {}
        for e in self.elements:
            layer = e.properties.get('layer', 'execution_logic')
            by_layer.setdefault(layer, []).append(e)

        # Ordem lógica de camadas
        ordered_layers = ['channels', 'gateway_inbound', 'execution_logic', 'data_management', 'gateway_outbound', 'external_integration']
        # Conectar elementos consecutivos dentro da mesma layer
        for layer, elems in by_layer.items():
            for i in range(len(elems) - 1):
                src, tgt = elems[i].identifier, elems[i + 1].identifier
                rel_id = self._generate_unique_relationship_id(src, tgt)
                name = f"Fluxo {self.element_name_by_id.get(src, src)} → {self.element_name_by_id.get(tgt, tgt)}"
                self.relationships.append(ArchiMateRelationship(identifier=rel_id, source=src, target=tgt, relation_type='Serving', name=name))

        # Conectar primeira ocorrência de cada layer para a próxima layer disponível
        present_layers = [l for l in ordered_layers if l in by_layer and by_layer[l]]
        for i in range(len(present_layers) - 1):
            src_layer = present_layers[i]
            tgt_layer = present_layers[i + 1]
            src_elem = by_layer[src_layer][0]
            tgt_elem = by_layer[tgt_layer][0]
            rel_id = self._generate_unique_relationship_id(src_elem.identifier, tgt_elem.identifier)
            name = f"Integração {self.element_name_by_id.get(src_elem.identifier, src_elem.identifier)} → {self.element_name_by_id.get(tgt_elem.identifier, tgt_elem.identifier)}"
            self.relationships.append(ArchiMateRelationship(identifier=rel_id, source=src_elem.identifier, target=tgt_elem.identifier, relation_type='Serving', name=name))

    def _generate_exact_template_xml(self, system_name: str, header: Optional[Dict[str, str]] = None) -> str:
        """Generate XML following EXACT Template SDLC 1.xml structure"""
        self.logger.info("📄 Gerando XML seguindo estrutura EXATA do Template SDLC 1.xml")

        # Gerar IDs únicos para o modelo e view principal
        model_id = self.id_generator.generate_element_id("model")
        main_view_id = self.id_generator.generate_element_id("main_view")
        container_view_id = self.id_generator.generate_element_id("container_view")

        # Criar estrutura XML base
        root = ET.Element("model")
        root.set("xmlns", "http://www.opengroup.org/xsd/archimate/3.0/")
        root.set("xmlns:dc", "http://purl.org/dc/elements/1.1/")
        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        root.set("xsi:schemaLocation", "http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.0/archimate3_Diagram.xsd http://purl.org/dc/elements/1.1/ http://dublincore.org/schemas/xmls/qdc/2008/02/11/dc.xsd")
        root.set("identifier", model_id)

        # Nome do modelo seguindo padrão Template SDLC 1.xml
        name_elem = ET.SubElement(root, "name")
        name_elem.set("xml:lang", "pt-br")
        name_elem.text = f"25.3T.JT-XXXX.TE-XXXX-Ingestões, Transformações, Experimentações, Análises e Visualização de Dados do SDLC"

        # Elementos
        elements_elem = ET.SubElement(root, "elements")
        for element in self.elements:
            elem = ET.SubElement(elements_elem, "element")
            elem.set("identifier", element.identifier)
            elem.set("xsi:type", "ApplicationComponent")

            elem_name = ET.SubElement(elem, "name")
            elem_name.set("xml:lang", "pt-br")
            elem_name.text = element.name

            if element.documentation:
                doc = ET.SubElement(elem, "documentation")
                doc.set("xml:lang", "pt-br")
                doc.text = element.documentation

        # Relacionamentos
        if self.relationships:
            relationships_elem = ET.SubElement(root, "relationships")
            for relationship in self.relationships:
                rel = ET.SubElement(relationships_elem, "relationship")
                rel.set("identifier", relationship.identifier)
                rel.set("source", relationship.source)
                rel.set("target", relationship.target)
                rel.set("xsi:type", self._normalize_relation_type(relationship.relation_type))

                rel_name = ET.SubElement(rel, "name")
                rel_name.set("xml:lang", "pt-br")
                rel_name.text = relationship.name

        # Views - seguindo EXATAMENTE o Template SDLC 1.xml
        views_elem = ET.SubElement(root, "views")
        diagrams_elem = ET.SubElement(views_elem, "diagrams")

        # View principal
        main_view = ET.SubElement(diagrams_elem, "view")
        main_view.set("identifier", main_view_id)
        main_view.set("viewpoint", "Introductory")

        main_view_name = ET.SubElement(main_view, "name")
        main_view_name.set("xml:lang", "pt-br")
        main_view_name.text = "JT-XXXX.TE-XXXX-Ingestões, Transformações, Experimentações, Análises e Visualização de Dados do SDLC"

        # Container view - NOME EXATO do Template SDLC 1.xml
        container_view = ET.SubElement(diagrams_elem, "view")
        container_view.set("identifier", container_view_id)
        container_view.set("viewpoint", "Introductory")

        container_view_name = ET.SubElement(container_view, "name")
        container_view_name.set("xml:lang", "pt-br")
        container_view_name.text = "1. Ingestões, Transformações, Experimentações, Análises e Visualização de Dados do SDLC"

        # Header labels - EXATOS do Template SDLC 1.xml (mas com textos dinâmicos)
        self._add_header_labels(container_view, header)

        # Layer containers - EXATOS do Template SDLC 1.xml
        self._add_layer_containers(container_view)

        # Elementos dentro das layers
        self._add_container_elements(container_view)

        # Relacionamentos visuais
        self._add_visual_relationships(container_view)

        # Converter para string XML
        ET.register_namespace("", "http://www.opengroup.org/xsd/archimate/3.0/")
        ET.register_namespace("dc", "http://purl.org/dc/elements/1.1/")
        ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")

        xml_str = ET.tostring(root, encoding='unicode', xml_declaration=True)

        # Adicionar declaração XML correta
        xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str[xml_str.find('<model'):]

        self.logger.info("✅ XML gerado seguindo estrutura EXATA do Template SDLC 1.xml")
        return xml_str

    def _add_header_labels(self, view_elem: ET.Element, header: Optional[Dict[str, str]] = None):
        """Add header labels following EXACT Template SDLC 1.xml coordinates"""
        header_cfg = self.template_layout['header']
        title_text_value = (header or {}).get('title') or header_cfg['title']['text']
        subtitle_text_value = (header or {}).get('subtitle') or header_cfg['subtitle']['text']

        # Background label (transparent)
        bg_label = ET.SubElement(view_elem, "node")
        bg_label.set("identifier", self.id_generator.generate_element_id("header_bg"))
        bg_label.set("xsi:type", "Label")
        bg_label.set("x", "0")
        bg_label.set("y", "47")
        bg_label.set("w", "620")
        bg_label.set("h", "80")

        bg_label_text = ET.SubElement(bg_label, "label")
        bg_label_text.set("xml:lang", "pt-br")
        bg_label_text.text = ""

        bg_style = ET.SubElement(bg_label, "style")
        bg_style.set("lineWidth", "1")
        bg_fill = ET.SubElement(bg_label, "fillColor")
        bg_fill.set("r", "255")
        bg_fill.set("g", "255")
        bg_fill.set("b", "255")
        bg_fill.set("a", "0")
        bg_line = ET.SubElement(bg_style, "lineColor")
        bg_line.set("r", "0")
        bg_line.set("g", "0")
        bg_line.set("b", "0")
        bg_line.set("a", "0")
        bg_font = ET.SubElement(bg_label, "font")
        bg_font.set("name", "arial")
        bg_font.set("size", "24")
        bg_font.set("style", "bold")
        bg_font_color = ET.SubElement(bg_font, "color")
        bg_font_color.set("r", "0")
        bg_font_color.set("g", "0")
        bg_font_color.set("b", "0")
        bg_font_color.set("a", "100")

        # Main title - EXACT coordinates from Template SDLC 1.xml
        title_label = ET.SubElement(view_elem, "node")
        title_label.set("identifier", self.id_generator.generate_element_id("title"))
        title_label.set("xsi:type", "Label")
        title_label.set("x", str(header_cfg['title']['x']))
        title_label.set("y", str(header_cfg['title']['y']))
        title_label.set("w", str(header_cfg['title']['w']))
        title_label.set("h", str(header_cfg['title']['h']))

        title_text = ET.SubElement(title_label, "label")
        title_text.set("xml:lang", "pt-br")
        title_text.text = title_text_value

        title_style = ET.SubElement(title_label, "style")
        title_style.set("lineWidth", "1")
        title_fill = ET.SubElement(title_style, "fillColor")
        title_fill.set("r", "255")
        title_fill.set("g", "255")
        title_fill.set("b", "255")
        title_fill.set("a", "0")
        title_line = ET.SubElement(title_style, "lineColor")
        title_line.set("r", "0")
        title_line.set("g", "0")
        title_line.set("b", "0")
        title_line.set("a", "0")
        title_font = ET.SubElement(title_style, "font")
        title_font.set("name", "arial")
        title_font.set("size", str(header_cfg['title']['size']))
        title_font.set("style", header_cfg['title']['style'])
        title_font_color = ET.SubElement(title_font, "color")
        title_font_color.set("r", "0")
        title_font_color.set("g", "0")
        title_font_color.set("b", "0")
        title_font_color.set("a", "100")

        # Subtitle - EXACT coordinates from Template SDLC 1.xml
        subtitle_label = ET.SubElement(view_elem, "node")
        subtitle_label.set("identifier", self.id_generator.generate_element_id("subtitle"))
        subtitle_label.set("xsi:type", "Label")
        subtitle_label.set("x", str(header_cfg['subtitle']['x']))
        subtitle_label.set("y", str(header_cfg['subtitle']['y']))
        subtitle_label.set("w", str(header_cfg['subtitle']['w']))
        subtitle_label.set("h", str(header_cfg['subtitle']['h']))

        subtitle_text = ET.SubElement(subtitle_label, "label")
        subtitle_text.set("xml:lang", "pt-br")
        subtitle_text.text = subtitle_text_value

        subtitle_style = ET.SubElement(subtitle_label, "style")
        subtitle_style.set("lineWidth", "1")
        subtitle_fill = ET.SubElement(subtitle_style, "fillColor")
        subtitle_fill.set("r", "255")
        subtitle_fill.set("g", "255")
        subtitle_fill.set("b", "255")
        subtitle_fill.set("a", "0")
        subtitle_line = ET.SubElement(subtitle_style, "lineColor")
        subtitle_line.set("r", "0")
        subtitle_line.set("g", "0")
        subtitle_line.set("b", "0")
        subtitle_line.set("a", "0")
        subtitle_font = ET.SubElement(subtitle_style, "font")
        subtitle_font.set("name", "arial")
        subtitle_font.set("size", str(header_cfg['subtitle']['size']))
        subtitle_font.set("style", header_cfg['subtitle']['style'])
        subtitle_font_color = ET.SubElement(subtitle_font, "color")
        subtitle_font_color.set("r", "0")
        subtitle_font_color.set("g", "0")
        subtitle_font_color.set("b", "0")
        subtitle_font_color.set("a", "100")

    def _add_layer_containers(self, view_elem: ET.Element):
        """Add layer containers following EXACT Template SDLC 1.xml coordinates and colors"""
        layers = self.template_layout['layers']

        for layer_name, layer_config in layers.items():
            if layer_name == 'etapas':
                # Handle etapas separately as it has special content
                self._add_etapas_container(view_elem, layer_config)
                continue

            container = ET.SubElement(view_elem, "node")
            visual_id = self.id_generator.generate_element_id(f"layer_{layer_name}")
            container.set("identifier", visual_id)
            container.set("xsi:type", "Container")
            container.set("x", str(layer_config['x']))
            container.set("y", str(layer_config['y']))
            container.set("w", str(layer_config['w']))
            container.set("h", str(layer_config['h']))

            container_label = ET.SubElement(container, "label")
            container_label.set("xml:lang", "pt-br")
            container_label.text = layer_config['title']

            container_style = ET.SubElement(container, "style")
            container_style.set("lineWidth", "1")

            # EXACT colors from Template SDLC 1.xml
            fill_color = ET.SubElement(container_style, "fillColor")
            fill_color.set("r", str(layer_config['color']['fill'][0]))
            fill_color.set("g", str(layer_config['color']['fill'][1]))
            fill_color.set("b", str(layer_config['color']['fill'][2]))
            fill_color.set("a", str(layer_config['color']['fill'][3]))

            line_color = ET.SubElement(container_style, "lineColor")
            line_color.set("r", str(layer_config['color']['line'][0]))
            line_color.set("g", str(layer_config['color']['line'][1]))
            line_color.set("b", str(layer_config['color']['line'][2]))
            line_color.set("a", str(layer_config['color']['line'][3]))

            font = ET.SubElement(container_style, "font")
            font.set("name", "arial")
            font.set("size", "10")
            font.set("style", "plain")

            font_color = ET.SubElement(font, "color")
            font_color.set("r", "0")
            font_color.set("g", "0")
            font_color.set("b", "0")
            font_color.set("a", "100")

    def _add_etapas_container(self, view_elem: ET.Element, layer_config: Dict):
        """Add etapas container with note following EXACT Template SDLC 1.xml"""
        # Main etapas container
        container = ET.SubElement(view_elem, "node")
        container.set("identifier", self.id_generator.generate_element_id("layer_etapas"))
        container.set("xsi:type", "Container")
        container.set("x", str(layer_config['x']))
        container.set("y", str(layer_config['y']))
        container.set("w", str(layer_config['w']))
        container.set("h", str(layer_config['h']))

        container_label = ET.SubElement(container, "label")
        container_label.set("xml:lang", "pt-br")
        container_label.text = layer_config['title']

        container_style = ET.SubElement(container, "style")
        container_style.set("lineWidth", "1")

        fill_color = ET.SubElement(container_style, "fillColor")
        fill_color.set("r", str(layer_config['color']['fill'][0]))
        fill_color.set("g", str(layer_config['color']['fill'][1]))
        fill_color.set("b", str(layer_config['color']['fill'][2]))
        fill_color.set("a", str(layer_config['color']['fill'][3]))

        line_color = ET.SubElement(container_style, "lineColor")
        line_color.set("r", str(layer_config['color']['line'][0]))
        line_color.set("g", str(layer_config['color']['line'][1]))
        line_color.set("b", str(layer_config['color']['line'][2]))
        line_color.set("a", str(layer_config['color']['line'][3]))

        font = ET.SubElement(container_style, "font")
        font.set("name", "arial")
        font.set("size", "10")
        font.set("style", "plain")

        font_color = ET.SubElement(font, "color")
        font_color.set("r", "0")
        font_color.set("g", "0")
        font_color.set("b", "0")
        font_color.set("a", "100")

        # Note inside etapas - EXACT coordinates from Template SDLC 1.xml
        note = ET.SubElement(container, "node")
        note.set("identifier", self.id_generator.generate_element_id("etapas_note"))
        note.set("xsi:type", "Label")
        note.set("x", str(layer_config['note_x']))
        note.set("y", str(layer_config['note_y']))
        note.set("w", str(layer_config['note_w']))
        note.set("h", str(layer_config['note_h']))

        note_label = ET.SubElement(note, "label")
        note_label.set("xml:lang", "pt-br")
        note_label.text = layer_config['note_text']

        note_style = ET.SubElement(note, "style")
        note_style.set("lineWidth", "1")

        note_fill = ET.SubElement(note_style, "fillColor")
        note_fill.set("r", "255")
        note_fill.set("g", "255")
        note_fill.set("b", "255")
        note_fill.set("a", "100")

        note_line = ET.SubElement(note_style, "lineColor")
        note_line.set("r", "0")
        note_line.set("g", "0")
        note_line.set("b", "0")
        note_line.set("a", "100")

        note_font = ET.SubElement(note_style, "font")
        note_font.set("name", "arial")
        note_font.set("size", "10")
        note_font.set("style", "plain")

        note_font_color = ET.SubElement(note_font, "color")
        note_font_color.set("r", "0")
        note_font_color.set("g", "0")
        note_font_color.set("b", "0")
        note_font_color.set("a", "100")

    def _add_container_elements(self, view_elem: ET.Element):
        """Add container elements positioned within their layers"""
        layers = self.template_layout['layers']

        # Group elements by layer
        elements_by_layer = {}
        for element in self.elements:
            layer = element.properties.get('layer', 'execution_logic')
            if layer not in elements_by_layer:
                elements_by_layer[layer] = []
            elements_by_layer[layer].append(element)

        # Position elements within each layer
        for layer_name, layer_elements in elements_by_layer.items():
            if layer_name not in layers:
                continue

            layer_config = layers[layer_name]

            for i, element in enumerate(layer_elements):
                # Calculate position within layer
                elements_per_row = layer_config.get('elements_per_row', 1)
                row = i // elements_per_row
                col = i % elements_per_row

                element_x = layer_config['x'] + layer_config.get('horizontal_padding', 10) + \
                           col * (layer_config.get('element_width', 180) + layer_config.get('horizontal_spacing', 20))
                element_y = layer_config['y'] + layer_config.get('vertical_padding', 40) + \
                           row * (layer_config.get('element_height', 50) + layer_config.get('vertical_spacing', 15))

                # Create visual element
                visual_element = ET.SubElement(view_elem, "node")
                visual_id = self.id_generator.generate_element_id(f"visual_{element.identifier}")
                visual_element.set("identifier", visual_id)
                visual_element.set("elementRef", element.identifier)
                visual_element.set("xsi:type", "Element")
                visual_element.set("x", str(element_x))
                visual_element.set("y", str(element_y))
                visual_element.set("w", str(layer_config.get('element_width', 180)))
                visual_element.set("h", str(layer_config.get('element_height', 50)))

                # Mapear para uso nas conexões
                self.visual_node_id_by_element_id[element.identifier] = visual_id

                element_style = ET.SubElement(visual_element, "style")
                element_style.set("lineWidth", "1")

                # Use layer color
                fill_color = ET.SubElement(element_style, "fillColor")
                fill_color.set("r", str(layer_config['color']['fill'][0]))
                fill_color.set("g", str(layer_config['color']['fill'][1]))
                fill_color.set("b", str(layer_config['color']['fill'][2]))
                fill_color.set("a", str(layer_config['color']['fill'][3]))

                line_color = ET.SubElement(element_style, "lineColor")
                line_color.set("r", str(layer_config['color']['line'][0]))
                line_color.set("g", str(layer_config['color']['line'][1]))
                line_color.set("b", str(layer_config['color']['line'][2]))
                line_color.set("a", str(layer_config['color']['line'][3]))

                font = ET.SubElement(element_style, "font")
                font.set("name", "Arial")
                font.set("size", "10")
                font.set("style", "plain")

                font_color = ET.SubElement(font, "color")
                font_color.set("r", "0")
                font_color.set("g", "0")
                font_color.set("b", "0")
                font_color.set("a", "100")

    def _add_visual_relationships(self, view_elem: ET.Element):
        """Add visual relationships between elements using exact visual node IDs"""
        for relationship in self.relationships:
            src_node_id = self.visual_node_id_by_element_id.get(relationship.source)
            tgt_node_id = self.visual_node_id_by_element_id.get(relationship.target)
            if not src_node_id or not tgt_node_id:
                self.logger.warning(f"⚠️ Conexão visual ignorada: nós visuais não encontrados para {relationship.source} → {relationship.target}")
                continue

            connection = ET.SubElement(view_elem, "connection")
            connection.set("identifier", self.id_generator.generate_element_id(f"visual_{relationship.identifier}"))
            connection.set("xsi:type", "Relationship")
            connection.set("relationshipRef", relationship.identifier)
            connection.set("source", src_node_id)
            connection.set("target", tgt_node_id)

            connection_style = ET.SubElement(connection, "style")
            connection_style.set("lineWidth", "1")

            fill_color = ET.SubElement(connection_style, "fillColor")
            fill_color.set("r", "255")
            fill_color.set("g", "255")
            fill_color.set("b", "255")
            fill_color.set("a", "100")

            line_color = ET.SubElement(connection_style, "lineColor")
            line_color.set("r", "0")
            line_color.set("g", "0")
            line_color.set("b", "0")
            line_color.set("a", "100")
