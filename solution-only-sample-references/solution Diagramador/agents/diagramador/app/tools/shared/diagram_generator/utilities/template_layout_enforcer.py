"""
Template Layout Enforcer - Força aplicação do layout BV correto seguindo EXATAMENTE o Template SDLC 1.xml
Este módulo garante que todos os diagramas sigam EXATAMENTE o template de referência
"""

import logging
import uuid
from typing import Dict, List, Tuple, Optional
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class TemplateLayoutEnforcer:
    """Força a aplicação do layout template BV independente de outros geradores"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Layer colors aligned with BV template usage
        # Channels = yellow, Gateways/Execution = blue-ish, External/Data = green-ish
        self.layer_colors = {
            'channels': (250, 240, 135, 100),
            'gateway_inbound': (184, 231, 252, 100),
            'execution_logic': (184, 231, 252, 100),
            'gateway_outbound': (184, 231, 252, 100),
            'external_integration': (214, 248, 184, 100),
            'data_management': (214, 248, 184, 100)
        }

    def apply_layout_from_existing_xml(self, metamodel_xml: str, system_name: str = "Sistema") -> str:
        """Gera um novo XML com o layout do template SDLC utilizando elementos dinâmicos do XML informado.
        - Não cria componentes hardcoded; usa os elementos do metamodelo
        - Aplica título/subtítulo e TODAS as layers do template
        - Aplica cores por layer conforme padrão BV
        """
        self.logger.info("🎯 Aplicando template SDLC usando elementos existentes (sem hardcodes)")

        # 1) Parse input XML and extract elements/relationships
        ns = {'a': 'http://www.opengroup.org/xsd/archimate/3.0/', 'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}
        root_in = ET.fromstring(metamodel_xml)

        elements_in: List[Tuple[str, str, str]] = []  # (id, name, type)
        for elem in root_in.findall('.//a:element', ns):
            elem_id = elem.get('identifier')
            elem_type = elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
            name_el = elem.find('a:name', ns)
            name = name_el.text if name_el is not None else elem_type
            elements_in.append((elem_id, name, elem_type))

        relationships_in: List[Tuple[str, str, str, str]] = []  # (id, sourceId, targetId, type)
        for rel in root_in.findall('.//a:relationship', ns):
            relationships_in.append(
                (
                    rel.get('identifier'),
                    rel.get('source'),
                    rel.get('target'),
                    rel.get('{http://www.w3.org/2001/XMLSchema-instance}type') or 'Serving'
                )
            )

        # 2) Classify elements by template layers
        by_layer: Dict[str, List[Tuple[str, str, str]]] = {
            'channels': [], 'gateway_inbound': [], 'execution_logic': [],
            'gateway_outbound': [], 'external_integration': [], 'data_management': []
        }
        for elem_id, name, elem_type in elements_in:
            layer = self._classify_to_layer(name, elem_type)
            if layer in by_layer:  # ignore 'skip' or unknown buckets
                by_layer[layer].append((elem_id, name, elem_type))

        # NEW: Normalize buckets to avoid wrong placements; keep only the MAIN system hidden
        self._normalize_layer_buckets(by_layer, main_system_name=system_name)

        # 3) Build a fresh ArchiMate XML model using the template layout
        xml_out = self._generate_template_view_from_layers(by_layer, relationships_in, system_name)
        return xml_out

    # -------------------------
    # New helper methods
    # -------------------------
    def _classify_to_layer(self, name: str, elem_type: str) -> str:
        """Classifica um elemento para a layer do template baseada no tipo e nome."""
        n = (name or '').lower()
        t = (elem_type or '').lower()

        # BusinessActor always in channels
        if t == 'businessactor' or any(k in n for k in ['usuário', 'usuario', 'cliente', 'ator']):
            return 'channels'

        # Ignore only if we later identify as the MAIN system; external systems should remain
        if t == 'applicationcollaboration' and n.startswith('sistema '):
            # Tentatively put in execution for now; we'll remove only the main system later
            return 'execution_logic'

        # Channels: ApplicationInterface or UI-ish names
        if t == 'applicationinterface' or any(k in n for k in ['portal', 'web', 'mobile', 'app', 'interface', 'ui']):
            return 'channels'

        # Data management: DataObject or repositories, cache, kafka
        if t == 'dataobject' or any(k in n for k in ['database', 'dados', 'reposit', 'banco', 'cache', 'redis', 'kafka', 'lake', 'warehouse']):
            return 'data_management'

        # Gateways
        if 'gateway' in n or 'api gateway' in n:
            if any(k in n for k in ['inbound', 'entrada', 'input']):
                return 'gateway_inbound'
            if any(k in n for k in ['outbound', 'saída', 'saida', 'output']):
                return 'gateway_outbound'
            return 'gateway_inbound'

        # External integration: treat as external by name regardless of type
        if any(k in n for k in ['extern', 'bacen', 'serasa', 'spc', 'core banking', 'pix', 'hsm', 'bureau', 'dict', 'spi', 'auditoria', 'compliance', 'gateway de notificações', 'notificações push', 'push gateway']):
            return 'external_integration'

        # Outbound services
        if any(k in n for k in ['publisher', 'email', 'notifica', 'push']):
            return 'gateway_outbound'

        # Default: execution logic
        return 'execution_logic'

    def _normalize_layer_buckets(self, by_layer: Dict[str, List[Tuple[str, str, str]]], main_system_name: Optional[str] = None) -> None:
        """Corrige buckets após classificação garantindo:
        - Remover APENAS o sistema principal (ApplicationCollaboration com nome igual/contendo main_system_name)
        - Qualquer BusinessActor fica SEMPRE em Channels
        - Deduplicação por (name, type) em cada layer
        """
        def is_main_system(tpl: Tuple[str, str, str]) -> bool:
            _id, _name, _type = tpl
            if (_type or '').lower() != 'applicationcollaboration':
                return False
            if not main_system_name:
                return False
            n = (_name or '').lower()
            ms = main_system_name.lower()
            # match both exact and common prefixed form
            return n == ms or n == f"sistema {ms}" or ms in n

        # Remove only the main system collaboration from all layers
        for layer in list(by_layer.keys()):
            before = len(by_layer[layer])
            by_layer[layer] = [tpl for tpl in by_layer[layer] if not is_main_system(tpl)]
            after = len(by_layer[layer])
            if before != after:
                self.logger.info(f"🔧 Removido sistema principal do layer {layer}")

        # Move BusinessActors to Channels
        moved: List[Tuple[str, str, str]] = []
        for layer in list(by_layer.keys()):
            if layer == 'channels':
                continue
            keep: List[Tuple[str, str, str]] = []
            for tpl in by_layer[layer]:
                _id, _name, _type = tpl
                if (_type or '').lower() == 'businessactor' or any(k in (_name or '').lower() for k in ['usuário', 'usuario', 'cliente', 'ator']):
                    moved.append(tpl)
                else:
                    keep.append(tpl)
            by_layer[layer] = keep
        if moved:
            existing_keys = {(n, t) for (_i, n, t) in by_layer['channels']}
            for tpl in moved:
                key = (tpl[1], tpl[2])
                if key not in existing_keys:
                    by_layer['channels'].append(tpl)
                    existing_keys.add(key)
            self.logger.info(f"🔧 Movidos {len(moved)} BusinessActor(s) para CHANNELS")

        # Deduplicate per layer
        for layer in list(by_layer.keys()):
            seen = set()
            unique = []
            for tpl in by_layer[layer]:
                key = (tpl[1], tpl[2])
                if key in seen:
                    continue
                seen.add(key)
                unique.append(tpl)
            by_layer[layer] = unique

    def _generate_template_view_from_layers(self, by_layer: Dict[str, List[Tuple[str, str, str]]], relationships_in: List[Tuple[str, str, str, str]], system_name: str, steps_labels: Optional[List[str]] = None) -> str:
        """Gera um novo modelo com view no layout do template, posicionando elementos por layer e mantendo relacionamentos."""
        # IDs base
        model_id = f"id-{uuid.uuid4().hex[:8]}"
        container_view_id = f"id-{uuid.uuid4().hex[:8]}"

        # Início
        root = ET.Element('model', {
            'xmlns': 'http://www.opengroup.org/xsd/archimate/3.0/',
            'xmlns:dc': 'http://purl.org/dc/elements/1.1/',
            'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'xsi:schemaLocation': 'http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.0/archimate3_Diagram.xsd http://purl.org/dc/elements/1.1/ http://dublincore.org/schemas/xmls/qdc/2008/02/11/dc.xsd',
            'identifier': model_id
        })
        ET.SubElement(root, 'name', {'xml:lang': 'pt-br'}).text = f'Visão de Container - {system_name}'

        # Elements section
        elements_map: Dict[str, str] = {}
        name_by_new_id: Dict[str, str] = {}
        type_by_new_id: Dict[str, str] = {}
        elements_elem = ET.SubElement(root, 'elements')
        for layer_name, elems in by_layer.items():
            for old_id, name, elem_type in elems:
                new_id = f"id-element-{uuid.uuid4().hex[:8]}"
                elements_map[old_id] = new_id
                e = ET.SubElement(elements_elem, 'element', {'identifier': new_id, '{http://www.w3.org/2001/XMLSchema-instance}type': elem_type})
                ET.SubElement(e, 'name', {'xml:lang': 'pt-br'}).text = name
                name_by_new_id[new_id] = name
                type_by_new_id[new_id] = elem_type

        # Relationships section
        rels_elem = ET.SubElement(root, 'relationships')
        # Keep direct reference to generated relationship IDs so we don't need
        # to rely on XML namespace lookups later (which were dropping
        # connections in some environments).
        relationship_map: Dict[Tuple[str, str, str], str] = {}
        # Fallback step labels if none explicitly provided
        rel_based_steps: List[str] = []
        for old_rel_id, src_old, tgt_old, rtype in relationships_in:
            src_new = elements_map.get(src_old)
            tgt_new = elements_map.get(tgt_old)
            if not src_new or not tgt_new:
                continue
            rid = f"id-rel-{uuid.uuid4().hex[:8]}"
            rel_type = rtype or 'Serving'
            rel = ET.SubElement(rels_elem, 'relationship', {
                'identifier': rid,
                'source': src_new,
                'target': tgt_new,
                '{http://www.w3.org/2001/XMLSchema-instance}type': rel_type
            })
            ET.SubElement(rel, 'name', {'xml:lang': 'pt-br'}).text = ''
            relationship_map[(src_new, rel_type, tgt_new)] = rid
            # Build a simple step text: Source → Target
            src_name = name_by_new_id.get(src_new, '')
            tgt_name = name_by_new_id.get(tgt_new, '')
            if src_name and tgt_name:
                rel_based_steps.append(f"{src_name} → {tgt_name}")

        # Choose steps: prefer explicit steps_labels if provided
        provided_steps = [s for s in (steps_labels or []) if isinstance(s, str) and s.strip()]
        final_steps = provided_steps if provided_steps else rel_based_steps

        # Views and diagrams
        views = ET.SubElement(root, 'views')
        diagrams = ET.SubElement(views, 'diagrams')

        # Container view
        cont_view = ET.SubElement(diagrams, 'view', {'identifier': container_view_id, 'viewpoint': 'Introductory'})
        ET.SubElement(cont_view, 'name', {'xml:lang': 'pt-br'}).text = f'Visão de Container - {system_name}'

        # Header labels (dynamic using system_name)
        self._emit_header_labels(cont_view, title=self._derive_title(system_name), subtitle='Visão de container — Autenticação, Validações, Integrações e Dados')

        # Layer containers
        layer_configs = {
            'channels': {'x': 67, 'y': 193, 'w': 200, 'h': 627, 'title': 'CHANNELS'},
            'gateway_inbound': {'x': 273, 'y': 193, 'w': 200, 'h': 627, 'title': 'GATEWAY INBOUND'},
            'execution_logic': {'x': 480, 'y': 193, 'w': 533, 'h': 500, 'title': 'EXECUTION LOGIC'},
            'gateway_outbound': {'x': 1020, 'y': 193, 'w': 173, 'h': 627, 'title': 'GATEWAY OUTBOUND'},
            'external_integration': {'x': 1200, 'y': 193, 'w': 200, 'h': 627, 'title': 'EXTERNAL INTEGRATION LAYER'},
            # Make Etapas a bit wider for readability
            'data_management': {'x': 480, 'y': 700, 'w': 533, 'h': 120, 'title': 'DATA MANAGEMENT'},
            'etapas': {'x': 1407, 'y': 193, 'w': 320, 'h': 627, 'title': 'Etapas'}
        }
        # Draw containers
        for lname, cfg in layer_configs.items():
            node = ET.SubElement(cont_view, 'node', {
                'identifier': f"id-layer-{lname}-{uuid.uuid4().hex[:6]}",
                'xsi:type': 'Container',
                'x': str(cfg['x']), 'y': str(cfg['y']), 'w': str(cfg['w']), 'h': str(cfg['h'])
            })
            ET.SubElement(node, 'label', {'xml:lang': 'pt-br'}).text = cfg['title']
            style = ET.SubElement(node, 'style', {'lineWidth': '1'})
            ET.SubElement(style, 'fillColor', {'r': '255', 'g': '255', 'b': '255', 'a': '100'})
            ET.SubElement(style, 'lineColor', {'r': '128', 'g': '128', 'b': '128', 'a': '100'})
            font = ET.SubElement(style, 'font', {'name': 'arial', 'size': '10', 'style': 'plain'})
            ET.SubElement(font, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})
            if lname == 'etapas':
                # Removed the oversized "Regras Aplicadas:   Observações:" note
                # Render a dynamic sequence list from provided steps or relationship-derived fallback
                start_x = 1420
                start_y = 227  # Move list up since the note was removed
                line_h = 22
                max_lines = 28
                for idx, label_text in enumerate(final_steps[:max_lines]):
                    ln = ET.SubElement(node, 'node', {
                        'identifier': f"id-etapa-{idx+1}-{uuid.uuid4().hex[:6]}", 'xsi:type': 'Label',
                        'x': str(start_x), 'y': str(start_y + idx * line_h), 'w': '300', 'h': '20'
                    })
                    # Use provided steps verbatim; only auto-number when using fallback steps
                    text_value = label_text if provided_steps else f"{idx+1}. {label_text}"
                    ET.SubElement(ln, 'label', {'xml:lang': 'pt-br'}).text = text_value
                    lst = ET.SubElement(ln, 'style', {'lineWidth': '1'})
                    ET.SubElement(lst, 'fillColor', {'r': '255', 'g': '255', 'b': '255', 'a': '0'})
                    ET.SubElement(lst, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '0'})
                    lfont = ET.SubElement(lst, 'font', {'name': 'arial', 'size': '10', 'style': 'plain'})
                    ET.SubElement(lfont, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

        # Position elements within layer containers
        positions = {
            'channels': {'start_x': 77, 'start_y': 233, 'spacing': 65, 'per_row': 1, 'w': 180, 'h': 50},
            'gateway_inbound': {'start_x': 283, 'start_y': 233, 'spacing': 65, 'per_row': 1, 'w': 180, 'h': 50},
            'execution_logic': {'start_x': 495, 'start_y': 233, 'spacing': 65, 'per_row': 2, 'w': 250, 'h': 60},
            'gateway_outbound': {'start_x': 1030, 'start_y': 233, 'spacing': 65, 'per_row': 1, 'w': 153, 'h': 50},
            'external_integration': {'start_x': 1210, 'start_y': 233, 'spacing': 65, 'per_row': 1, 'w': 180, 'h': 50},
            'data_management': {'start_x': 495, 'start_y': 735, 'spacing': 45, 'per_row': 2, 'w': 250, 'h': 40}
        }

        visual_by_element: Dict[str, str] = {}
        # Build reverse map name+type to id for quick lookup
        element_index = {}
        for e in root.iter('element'):
            t = e.get('{http://www.w3.org/2001/XMLSchema-instance}type')
            n = e.find('name')
            element_index[(t, n.text if n is not None else '')] = e.get('identifier')

        for lname, elems in by_layer.items():
            if lname not in positions:
                continue
            cfg = positions[lname]
            per_row = cfg.get('per_row', 1)
            for i, (old_id, name, elem_type) in enumerate(elems):
                row, col = divmod(i, per_row)
                x = cfg['start_x'] + col * (cfg['w'] + 10)
                y = cfg['start_y'] + row * cfg['spacing']

                new_id = element_index.get((elem_type, name))
                if not new_id:
                    continue

                node_id = f"id-visual-{uuid.uuid4().hex[:6]}"
                v = ET.SubElement(cont_view, 'node', {
                    'identifier': node_id,
                    'elementRef': new_id,
                    'xsi:type': 'Element',
                    'x': str(x), 'y': str(y), 'w': str(cfg['w']), 'h': str(cfg['h'])
                })
                visual_by_element[new_id] = node_id
                style = ET.SubElement(v, 'style', {'lineWidth': '1'})
                r, g, b, a = self.layer_colors.get(lname, (255, 255, 255, 100))
                ET.SubElement(style, 'fillColor', {'r': str(r), 'g': str(g), 'b': str(b), 'a': str(a)})
                ET.SubElement(style, 'lineColor', {'r': '128', 'g': '128', 'b': '128', 'a': '100'})
                font = ET.SubElement(style, 'font', {'name': 'Arial', 'size': '10', 'style': 'plain'})
                ET.SubElement(font, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

        # Relationship visual connections
        for (src, rtype, tgt), rid in list(relationship_map.items()):
            src_node = visual_by_element.get(src)
            tgt_node = visual_by_element.get(tgt)
            if not src_node or not tgt_node:
                continue
            conn = ET.SubElement(cont_view, 'connection', {
                'identifier': f"id-conn-{uuid.uuid4().hex[:6]}",
                'xsi:type': 'Relationship',
                'relationshipRef': rid,
                'source': src_node,
                'target': tgt_node
            })
            cstyle = ET.SubElement(conn, 'style', {'lineWidth': '1'})
            ET.SubElement(cstyle, 'fillColor', {'r': '255', 'g': '255', 'b': '255', 'a': '100'})
            ET.SubElement(cstyle, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

        xml_str = ET.tostring(root, encoding='unicode')
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

    def _emit_header_labels(self, view_elem: ET.Element, title: str, subtitle: str):
        """Emite título e subtítulo no cabeçalho."""
        # BG
        bg = ET.SubElement(view_elem, 'node', {'identifier': f'id-header-bg-{uuid.uuid4().hex[:6]}', 'xsi:type': 'Label', 'x': '0', 'y': '47', 'w': '620', 'h': '80'})
        ET.SubElement(bg, 'label', {'xml:lang': 'pt-br'}).text = ''
        s = ET.SubElement(bg, 'style', {'lineWidth': '1'})
        ET.SubElement(s, 'fillColor', {'r': '255', 'g': '255', 'b': '255', 'a': '0'})
        ET.SubElement(s, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '0'})
        f = ET.SubElement(s, 'font', {'name': 'arial', 'size': '24', 'style': 'bold'})
        ET.SubElement(f, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

        # Title
        t = ET.SubElement(view_elem, 'node', {'identifier': f'id-title-{uuid.uuid4().hex[:6]}', 'xsi:type': 'Label', 'x': '127', 'y': '47', 'w': '707', 'h': '40'})
        ET.SubElement(t, 'label', {'xml:lang': 'pt-br'}).text = title
        ts = ET.SubElement(t, 'style', {'lineWidth': '1'})
        ET.SubElement(ts, 'fillColor', {'r': '255', 'g': '255', 'b': '255', 'a': '0'})
        ET.SubElement(ts, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '0'})
        tf = ET.SubElement(ts, 'font', {'name': 'arial', 'size': '24', 'style': 'bold'})
        ET.SubElement(tf, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

        # Subtitle
        st = ET.SubElement(view_elem, 'node', {'identifier': f'id-subtitle-{uuid.uuid4().hex[:6]}', 'xsi:type': 'Label', 'x': '127', 'y': '87', 'w': '700', 'h': '33'})
        ET.SubElement(st, 'label', {'xml:lang': 'pt-br'}).text = subtitle
        ss = ET.SubElement(st, 'style', {'lineWidth': '1'})
        ET.SubElement(ss, 'fillColor', {'r': '255', 'g': '255', 'b': '255', 'a': '0'})
        ET.SubElement(ss, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '0'})
        sf = ET.SubElement(ss, 'font', {'name': 'arial', 'size': '16', 'style': 'plain'})
        ET.SubElement(sf, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

    def _derive_title(self, system_name: str) -> str:
        s = (system_name or '').lower()
        if 'pix' in s:
            return 'Transferências Instantâneas via PIX'
        if 'pagamento' in s:
            return 'Pagamentos Bancários'
        return system_name or 'Visão de Container'

    # Existing methods kept below (story-based fallback)

    def _create_bv_containers_from_story(self, user_story: str) -> Dict[str, List[Dict]]:
        """
        Extrai containers dinamicamente da user story - COMPLETAMENTE DINÂMICO
        Sempre gera nomes apropriados de containers C4 baseados no contexto
        """

        # Inicializar containers para todas as camadas
        containers = {
            'channels': [],
            'gateway_inbound': [],
            'execution_logic': [],
            'gateway_outbound': [],
            'external_integration': [],
            'data_management': []
        }

        # SEMPRE usar extração ampla para garantir nomes apropriados de containers
        self._extract_broad_elements(user_story, containers)

        return containers

    def _extract_broad_elements(self, user_story: str, containers: Dict[str, List[Dict]]):
        """
        Extração mais ampla quando elementos específicos não são encontrados
        Gera containers C4 apropriados com nomes técnicos
        """

        story_context = user_story.lower()

        # Inferir elementos baseados no contexto geral - NOMES C4 APROPRIADOS
        if 'pix' in story_context or 'transferência' in story_context:
            # CHANNELS - Interfaces de usuário
            containers['channels'].append({'name': 'Mobile Banking App', 'desc': 'Interface mobile para transferências PIX'})
            containers['channels'].append({'name': 'Internet Banking Portal', 'desc': 'Interface web para transferências PIX'})

            # GATEWAY INBOUND - Pontos de entrada
            containers['gateway_inbound'].append({'name': 'PIX API Gateway', 'desc': 'Gateway para operações PIX'})
            containers['gateway_inbound'].append({'name': 'Authentication Service', 'desc': 'Serviço de autenticação multifator'})

            # EXECUTION LOGIC - Microserviços de negócio
            containers['execution_logic'].extend([
                {'name': 'PIX Transfer Service', 'desc': 'Orquestração de transferências PIX'},
                {'name': 'Balance Validation Service', 'desc': 'Validação de saldo para transferências'},
                {'name': 'PIX Key Service', 'desc': 'Gestão de chaves PIX (CPF, email, telefone)'},
                {'name': 'Limit Control Service', 'desc': 'Controle de limites diários'},
                {'name': 'Fraud Prevention Service', 'desc': 'Análise antifraude em tempo real'}
            ])

            # GATEWAY OUTBOUND - Comunicações externas
            containers['gateway_outbound'].extend([
                {'name': 'Push Notification Service', 'desc': 'Notificações push para mobile'},
                {'name': 'Email Service', 'desc': 'Envio de comprovantes por email'},
                {'name': 'Audit Event Publisher', 'desc': 'Publicação de eventos de auditoria'}
            ])

            # EXTERNAL INTEGRATION - Sistemas externos
            containers['external_integration'].extend([
                {'name': 'PIX/DICT BACEN Interface', 'desc': 'Integração com Sistema PIX do Banco Central'},
                {'name': 'Core Banking Connector', 'desc': 'Conector para sistema legado mainframe'},
                {'name': 'HSM Security Module', 'desc': 'Módulo de segurança para chaves criptográficas'}
            ])

            # DATA MANAGEMENT - Dados
            containers['data_management'].extend([
                {'name': 'PIX Transaction Database', 'desc': 'PostgreSQL - Persistência de transações PIX'},
                {'name': 'Redis Cache', 'desc': 'Cache distribuído para performance'},
                {'name': 'Kafka Message Bus', 'desc': 'Barramento de mensagens assíncronas'}
            ])

        elif 'banking' in story_context or 'conta' in story_context:
            # BANKING DOMAIN
            containers['channels'].extend([
                {'name': 'Mobile Banking App', 'desc': 'App mobile bancário'},
                {'name': 'Internet Banking', 'desc': 'Portal web bancário'}
            ])
            containers['gateway_inbound'].extend([
                {'name': 'Banking API Gateway', 'desc': 'Gateway para APIs bancárias'},
                {'name': 'Authentication Proxy', 'desc': 'Proxy de autenticação'}
            ])
            containers['execution_logic'].extend([
                {'name': 'Account Service', 'desc': 'Serviço de gestão de contas'},
                {'name': 'Transaction Engine', 'desc': 'Motor de processamento de transações'},
                {'name': 'Balance Service', 'desc': 'Serviço de consulta de saldos'}
            ])
            containers['external_integration'].extend([
                {'name': 'Core Banking System', 'desc': 'Sistema bancário central'},
                {'name': 'Credit Bureau API', 'desc': 'Integração com bureaus de crédito'}
            ])
            containers['data_management'].extend([
                {'name': 'Customer Database', 'desc': 'Base de dados de clientes'},
                {'name': 'Transaction Log', 'desc': 'Log de transações'}
            ])

        else:
            # GENERIC DOMAIN - Elementos mínimos mas apropriados
            containers['channels'].append({'name': 'Web Application', 'desc': 'Interface web principal'})
            containers['gateway_inbound'].append({'name': 'API Gateway', 'desc': 'Gateway de entrada para APIs'})
            containers['execution_logic'].extend([
                {'name': 'Business Service', 'desc': 'Serviço principal de negócio'},
                {'name': 'Validation Service', 'desc': 'Serviço de validação de dados'}
            ])
            containers['gateway_outbound'].append({'name': 'Notification Service', 'desc': 'Serviço de notificações'})
            containers['external_integration'].append({'name': 'External System Interface', 'desc': 'Interface com sistemas externos'})
            containers['data_management'].extend([
                {'name': 'Application Database', 'desc': 'Base de dados principal'},
                {'name': 'Cache Layer', 'desc': 'Camada de cache'}
            ])

    def _generate_exact_template_sdlc_xml(self, containers: Dict, system_name: str, user_story: str) -> str:
        """Gera XML seguindo EXATAMENTE a estrutura do Template SDLC 1.xml"""

        model_id = f"id-{uuid.uuid4().hex[:8]}"
        main_view_id = f"id-{uuid.uuid4().hex[:8]}"
        container_view_id = f"id-{uuid.uuid4().hex[:8]}"

        # Início do XML com estrutura EXATA do Template SDLC 1.xml
        xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<model xmlns="http://www.opengroup.org/xsd/archimate/3.0/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.0/archimate3_Diagram.xsd http://purl.org/dc/elements/1.1/ http://dublincore.org/schemas/xmls/qdc/2008/02/11/dc.xsd" identifier="{model_id}">
    <name xml:lang="pt-br">25.3T.JT-XXXX.TE-XXXX-Ingestões, Transformações, Experimentações, Análises e Visualização de Dados do SDLC</name>
    <elements>'''

        # Gerar elementos com IDs únicos
        element_map = {}
        element_counter = 1

        # Gerar elementos para cada layer com TIPOS CORRETOS C4 Container
        for layer_name, layer_containers in containers.items():
            for container in layer_containers:
                element_id = f"id-element-{element_counter}"
                element_map[container['name']] = element_id

                # Determinar tipo correto baseado na camada C4 Container
                element_type = self._get_c4_container_type(layer_name, container['name'])

                xml_content += f'''
        <element identifier="{element_id}" xsi:type="{element_type}">
            <name xml:lang="pt-br">{container['name']}</name>
            <documentation xml:lang="pt-br">{container['desc']}</documentation>
        </element>'''
                element_counter += 1

        xml_content += '''
    </elements>
    <relationships>'''

        # Gerar relacionamentos básicos entre layers
        rel_counter = 1
        for i, (source_layer, source_containers) in enumerate(containers.items()):
            for j, (target_layer, target_containers) in enumerate(containers.items()):
                if i < j and source_containers and target_containers:
                    source_container = source_containers[0]
                    target_container = target_containers[0]
                    rel_id = f"id-rel-{rel_counter}"

                    # Gerar nome descritivo para o relacionamento
                    source_name = source_container['name'].replace(' BV', '').strip()
                    target_name = target_container['name'].replace(' BV', '').strip()
                    rel_name = f"Integração {source_name} → {target_name}"

                    xml_content += f'''
        <relationship identifier="{rel_id}" source="{element_map[source_container['name']]}" target="{element_map[target_container['name']]}" xsi:type="Serving">
            <name xml:lang="pt-br">{rel_name}</name>
        </relationship>'''
                    rel_counter += 1

        xml_content += '''
    </relationships>
    <views>
        <diagrams>'''

        # View principal
        xml_content += f'''
            <view identifier="{main_view_id}" viewpoint="Introductory">
                <name xml:lang="pt-br">JT-XXXX.TE-XXXX-Ingestões, Transformações, Experimentações, Análises e Visualização de Dados do SDLC</name>
            </view>'''

        # Container view com NOME EXATO do Template SDLC 1.xml
        xml_content += f'''
            <view identifier="{container_view_id}" viewpoint="Introductory">
                <name xml:lang="pt-br">1. Ingestões, Transformações, Experimentações, Análises e Visualização de Dados do SDLC</name>'''

        # Header labels - EXATOS do Template SDLC 1.xml
        xml_content += f'''
                <node identifier="id-header-bg-{uuid.uuid4().hex[:6]}" xsi:type="Label" x="0" y="47" w="620" h="80">
                    <label xml:lang="pt-br"></label>
                    <style lineWidth="1">
                        <fillColor r="255" g="255" b="255" a="0"/>
                        <lineColor r="0" g="0" b="0" a="0"/>
                        <font name="arial" size="24" style="bold">
                            <color r="0" g="0" b="0" a="100"/>
                        </font>
                    </style>
                </node>
                <node identifier="id-title-{uuid.uuid4().hex[:6]}" xsi:type="Label" x="127" y="47" w="707" h="40">
                    <label xml:lang="pt-br">Plataforma e Produtos de Dados</label>
                    <style lineWidth="1">
                        <fillColor r="255" g="255" b="255" a="0"/>
                        <lineColor r="0" g="0" b="0" a="0"/>
                        <font name="arial" size="24" style="bold">
                            <color r="0" g="0" b="0" a="100"/>
                        </font>
                    </style>
                </node>
                <node identifier="id-subtitle-{uuid.uuid4().hex[:6]}" xsi:type="Label" x="127" y="87" w="700" h="33">
                    <label xml:lang="pt-br">Visão de container - Ingestões, Transformações, Experimentações, Análises e Visualização de Dados do SDLC</label>
                    <style lineWidth="1">
                        <fillColor r="255" g="255" b="255" a="0"/>
                        <lineColor r="0" g="0" b="0" a="0"/>
                        <font name="arial" size="16" style="plain">
                            <color r="0" g="0" b="0" a="100"/>
                        </font>
                    </style>
                </node>'''

        # Layer containers - EXATAS coordenadas do Template SDLC 1.xml
        layer_configs = {
            'channels': {'x': 67, 'y': 193, 'w': 200, 'h': 627, 'title': 'CHANNELS'},
            'gateway_inbound': {'x': 273, 'y': 193, 'w': 200, 'h': 627, 'title': 'GATEWAY INBOUND'},
            'execution_logic': {'x': 480, 'y': 193, 'w': 533, 'h': 500, 'title': 'EXECUTION LOGIC'},
            'gateway_outbound': {'x': 1020, 'y': 193, 'w': 173, 'h': 627, 'title': 'GATEWAY OUTBOUND'},
            'external_integration': {'x': 1200, 'y': 193, 'w': 200, 'h': 627, 'title': 'EXTERNAL INTEGRATION LAYER'},
            'data_management': {'x': 480, 'y': 700, 'w': 533, 'h': 120, 'title': 'DATA MANAGEMENT'},
            # Wider Etapas lane
            'etapas': {'x': 1407, 'y': 193, 'w': 320, 'h': 627, 'title': 'Etapas'}
        }

        # Adicionar containers das layers
        for layer_name, config in layer_configs.items():
            layer_id = f"id-layer-{layer_name}-{uuid.uuid4().hex[:6]}"
            xml_content += f'''
                <node identifier="{layer_id}" xsi:type="Container" x="{config['x']}" y="{config['y']}" w="{config['w']}" h="{config['h']}">
                    <label xml:lang="pt-br">{config['title']}</label>
                    <style lineWidth="1">
                        <fillColor r="255" g="255" b="255" a="100"/>
                        <lineColor r="128" g="128" b="128" a="100"/>
                        <font name="arial" size="10" style="plain">
                            <color r="0" g="0" b="0" a="100"/>
                        </font>
                    </style>'''

            # Removida a nota "Regras Aplicadas:   Observações:" para economizar espaço
            xml_content += '''
                </node>'''

        # Elementos dentro das layers
        element_positions = {
            'channels': {'start_x': 77, 'start_y': 233, 'spacing': 65, 'per_row': 1, 'w': 180, 'h': 50},
            'gateway_inbound': {'start_x': 283, 'start_y': 233, 'spacing': 65, 'per_row': 1, 'w': 180, 'h': 50},
            'execution_logic': {'start_x': 495, 'start_y': 233, 'spacing': 65, 'per_row': 2, 'w': 250, 'h': 60},
            'gateway_outbound': {'start_x': 1030, 'start_y': 233, 'spacing': 65, 'per_row': 1, 'w': 153, 'h': 50},
            'external_integration': {'start_x': 1210, 'start_y': 233, 'spacing': 65, 'per_row': 1, 'w': 180, 'h': 50},
            'data_management': {'start_x': 495, 'start_y': 735, 'spacing': 45, 'per_row': 2, 'w': 250, 'h': 40}
        }

        # Posicionar elementos nas layers
        for layer_name, layer_containers in containers.items():
            if layer_name in element_positions and layer_containers:
                pos_config = element_positions[layer_name]
                per_row = pos_config.get('per_row', 1)

                for i, container in enumerate(layer_containers):
                    row = i // per_row
                    col = i % per_row

                    element_x = pos_config['start_x'] + col * 260
                    element_y = pos_config['start_y'] + row * pos_config['spacing']

                    element_width = 250 if per_row > 1 else 180
                    element_height = 50

                    visual_id = f"id-visual-{uuid.uuid4().hex[:6]}"
                    xml_content += f'''
                <node identifier="{visual_id}" elementRef="{element_map[container['name']]}" xsi:type="Element" x="{element_x}" y="{element_y}" w="{element_width}" h="{element_height}">
                    <style lineWidth="1">
                        <fillColor r="255" g="255" b="255" a="100"/>
                        <lineColor r="128" g="128" b="128" a="100"/>
                        <font name="Arial" size="10" style="plain">
                            <color r="0" g="0" b="0" a="100"/>
                        </font>
                    </style>
                </node>'''

        xml_content += '''
            </view>
        </diagrams>
    </views>
</model>'''

        return xml_content

    def _get_c4_container_type(self, layer_name: str, container_name: str) -> str:
        """
        Determina o tipo correto de C4 Container baseado na camada e nome do container
        Segue padrões C4 Container apropriados para ArchiMate 3.0
        """
        container_lower = container_name.lower()

        # CHANNELS - Interfaces de usuário (ApplicationInterface)
        if layer_name == 'channels':
            return 'ApplicationInterface'

        # GATEWAY INBOUND - Pontos de entrada (ApplicationService)
        elif layer_name == 'gateway_inbound':
            if 'gateway' in container_lower or 'api' in container_lower:
                return 'ApplicationService'
            else:
                return 'ApplicationComponent'

        # EXECUTION LOGIC - Serviços de negócio (ApplicationComponent)
        elif layer_name == 'execution_logic':
            if 'service' in container_lower or 'serviço' in container_lower:
                return 'ApplicationComponent'
            elif 'engine' in container_lower or 'motor' in container_lower:
                return 'ApplicationComponent'
            else:
                return 'ApplicationComponent'

        # GATEWAY OUTBOUND - Serviços de saída (ApplicationService)
        elif layer_name == 'gateway_outbound':
            if 'service' in container_lower or 'publisher' in container_lower:
                return 'ApplicationService'
            else:
                return 'ApplicationComponent'

        # EXTERNAL INTEGRATION - Sistemas externos (ApplicationInterface)
        elif layer_name == 'external_integration':
            return 'ApplicationInterface'

        # DATA MANAGEMENT - Dados (DataObject para dados, Artifact para artefatos)
        elif layer_name == 'data_management':
            if any(word in container_lower for word in ['database', 'banco', 'dados', 'cache']):
                return 'DataObject'
            elif any(word in container_lower for word in ['kafka', 'queue', 'bus', 'message']):
                return 'ApplicationComponent'  # Message bus é componente
            else:
                return 'Artifact'

        # Default seguro
        return 'ApplicationComponent'

    # -------------------------
    # NEW PUBLIC METHOD: build from mapped layers directly
    # -------------------------
    def apply_layout_from_mapped_layers(self, by_layer: Dict[str, List[Tuple[str, str, str]]], relationships_in: List[Tuple[str, str, str, str]], system_name: str = "Sistema", steps_labels: Optional[List[str]] = None) -> str:
        """Gera um XML ArchiMate já com o view no layout do template usando as camadas fornecidas.
        by_layer: dict com chaves normalizadas ('channels', 'gateway_inbound', 'execution_logic', 'data_management', 'gateway_outbound', 'external_integration').
        relationships_in: lista de tuplas (rel_id, source_old_id, target_old_id, rel_type).
        steps_labels: lista de strings com as etapas textuais do prompt.
        """
        # Sanitize: ensure all expected buckets exist
        expected = ['channels', 'gateway_inbound', 'execution_logic', 'data_management', 'gateway_outbound', 'external_integration']
        layers: Dict[str, List[Tuple[str, str, str]]] = {k: [] for k in expected}
        for k, v in (by_layer or {}).items():
            if k in layers:
                layers[k].extend(v)
        # Do not reclassify; just call generator with provided steps
        return self._generate_template_view_from_layers(layers, relationships_in, system_name, steps_labels)

    # =========================================================================
    # CONTEXT VIEW SUPPORT
    # =========================================================================

    def apply_context_layout_from_existing_xml(
        self,
        metamodel_xml: str,
        system_name: str = "Sistema",
        steps_labels: Optional[List[str]] = None,
    ) -> str:
        """
        Reconstrói o XML aplicando a visão de contexto do template SDLC 1.xml
        a partir dos elementos e relacionamentos já existentes.
        """
        self.logger.info("[Template] Aplicando layout de CONTEXTO com base no XML existente")

        ns = {
            'a': 'http://www.opengroup.org/xsd/archimate/3.0/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        }
        root_in = ET.fromstring(metamodel_xml)

        elements_in: List[Tuple[str, str, str]] = []
        for elem in root_in.findall('.//a:element', ns):
            elem_id = elem.get('identifier')
            elem_type = elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
            name_el = elem.find('a:name', ns)
            name = name_el.text if name_el is not None else elem_type
            elements_in.append((elem_id, name or "", elem_type or ""))

        relationships_in: List[Tuple[str, str, str, str]] = []
        for rel in root_in.findall('.//a:relationship', ns):
            relationships_in.append(
                (
                    rel.get('identifier'),
                    rel.get('source'),
                    rel.get('target'),
                    rel.get('{http://www.w3.org/2001/XMLSchema-instance}type') or 'Serving',
                )
            )

        context_areas = self._classify_for_context_view(elements_in, system_name)
        return self._generate_context_view_from_areas(
            context_areas,
            relationships_in,
            system_name,
            steps_labels or [],
        )

    def _classify_for_context_view(
        self,
        elements: List[Tuple[str, str, str]],
        main_system_name: str,
    ) -> Dict[str, List[Tuple[str, str, str]]]:
        """
        Agrupa elementos em buckets utilizados na visão de contexto.
        """
        areas = {
            'actors': [],
            'channels': [],
            'products': [],
            'external_systems': [],
        }

        main_lower = (main_system_name or '').strip().lower()
        main_candidate: Optional[str] = None

        for elem_id, name, elem_type in elements:
            lower_name = (name or '').strip().lower()
            lower_type = (elem_type or '').strip().lower()

            # Identificar o sistema principal
            if lower_type == 'applicationcollaboration':
                if lower_name == main_lower or lower_name == f"sistema {main_lower}" or (main_lower and main_lower in lower_name):
                    main_candidate = elem_id
                    continue

            if lower_type == 'businessactor' or any(keyword in lower_name for keyword in ['usuario', 'cliente', 'ator', 'stakeholder']):
                areas['actors'].append((elem_id, name, elem_type))
                continue

            if lower_type == 'applicationinterface' or any(keyword in lower_name for keyword in ['portal', 'web', 'mobile', 'app', 'interface']):
                areas['channels'].append((elem_id, name, elem_type))
                continue

            if any(keyword in lower_name for keyword in ['extern', 'bacen', 'serasa', 'spc', 'core banking', 'pix', 'hsm', 'bureau', 'dict', 'spi']):
                areas['external_systems'].append((elem_id, name, elem_type))
                continue

            if lower_type == 'applicationcollaboration':
                areas['external_systems'].append((elem_id, name, elem_type))
                continue

            areas['products'].append((elem_id, name, elem_type))

        if main_candidate:
            for bucket in areas.values():
                bucket[:] = [tpl for tpl in bucket if tpl[0] != main_candidate]

        return areas

    def _generate_context_view_from_areas(
        self,
        by_area: Dict[str, List[Tuple[str, str, str]]],
        relationships_in: List[Tuple[str, str, str, str]],
        system_name: str,
        steps_labels: List[str],
    ) -> str:
        """
        Constrói um novo XML com a visão de contexto seguindo o layout SDLC.
        """
        model_id = f"id-{uuid.uuid4().hex[:8]}"
        context_view_id = f"id-{uuid.uuid4().hex[:8]}"

        root = ET.Element(
            'model',
            {
                'xmlns': 'http://www.opengroup.org/xsd/archimate/3.0/',
                'xmlns:dc': 'http://purl.org/dc/elements/1.1/',
                'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
                'xsi:schemaLocation': 'http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.0/archimate3_Diagram.xsd',
                'identifier': model_id,
            },
        )
        ET.SubElement(root, 'name', {'xml:lang': 'pt-br'}).text = f'Visao de Contexto - {system_name}'

        elements_elem = ET.SubElement(root, 'elements')
        elements_map: Dict[str, str] = {}
        for area_name, elems in by_area.items():
            for old_id, name, elem_type in elems:
                new_id = f"id-element-{uuid.uuid4().hex[:8]}"
                elements_map[old_id] = new_id
                element = ET.SubElement(
                    elements_elem,
                    'element',
                    {
                        'identifier': new_id,
                        '{http://www.w3.org/2001/XMLSchema-instance}type': elem_type,
                    },
                )
                ET.SubElement(element, 'name', {'xml:lang': 'pt-br'}).text = name

        relationship_map: Dict[Tuple[str, str, str], str] = {}
        relationships_elem: Optional[ET.Element] = None
        for rel_id, src_old, tgt_old, rel_type in relationships_in:
            src_new = elements_map.get(src_old)
            tgt_new = elements_map.get(tgt_old)
            if not src_new or not tgt_new:
                continue
            if relationships_elem is None:
                relationships_elem = ET.SubElement(root, 'relationships')
            new_rel_id = f"id-rel-{uuid.uuid4().hex[:8]}"
            rel_elem = ET.SubElement(
                relationships_elem,
                'relationship',
                {
                    'identifier': new_rel_id,
                    'source': src_new,
                    'target': tgt_new,
                    '{http://www.w3.org/2001/XMLSchema-instance}type': rel_type or 'Serving',
                },
            )
            ET.SubElement(rel_elem, 'name', {'xml:lang': 'pt-br'}).text = ''
            relationship_map[(src_new, rel_type or 'Serving', tgt_new)] = new_rel_id

        views = ET.SubElement(root, 'views')
        diagrams = ET.SubElement(views, 'diagrams')

        ctx_view = ET.SubElement(diagrams, 'view', {
            'identifier': context_view_id,
            'viewpoint': 'Introductory'
        })
        ET.SubElement(ctx_view, 'name', {'xml:lang': 'pt-br'}).text = f'Visao de contexto - {system_name}'

        # Header labels de acordo com template
        self._emit_context_header_labels(ctx_view, system_name)

        # Containers principais conforme template SDLC
        actors_container = ET.SubElement(ctx_view, 'node', {
            'identifier': f"id-ctx-actors-{uuid.uuid4().hex[:6]}",
            'xsi:type': 'Container',
            'x': '80', 'y': '180', 'w': '340', 'h': '487'
        })
        ET.SubElement(actors_container, 'label', {'xml:lang': 'pt-br'}).text = 'Contexto atores'
        self._apply_container_style(actors_container)

        ext_env = ET.SubElement(actors_container, 'node', {
            'identifier': f"id-ctx-extenv-{uuid.uuid4().hex[:6]}",
            'xsi:type': 'Label',
            'x': '97', 'y': '200', 'w': '313', 'h': '460'
        })
        ET.SubElement(ext_env, 'label', {'xml:lang': 'pt-br'}).text = 'Ambiente externo'
        self._apply_label_style(ext_env)

        app_container = ET.SubElement(ctx_view, 'node', {
            'identifier': f"id-ctx-app-{uuid.uuid4().hex[:6]}",
            'xsi:type': 'Container',
            'x': '427', 'y': '180', 'w': '753', 'h': '600'
        })
        ET.SubElement(app_container, 'label', {'xml:lang': 'pt-br'}).text = 'Contexto aplicacional interno'
        self._apply_container_style(app_container)

        channels_box = ET.SubElement(app_container, 'node', {
            'identifier': f"id-ctx-channels-{uuid.uuid4().hex[:6]}",
            'xsi:type': 'Label',
            'x': '440', 'y': '200', 'w': '233', 'h': '567'
        })
        ET.SubElement(channels_box, 'label', {'xml:lang': 'pt-br'}).text = 'Canais'
        self._apply_label_style(channels_box)

        products_box = ET.SubElement(app_container, 'node', {
            'identifier': f"id-ctx-products-{uuid.uuid4().hex[:6]}",
            'xsi:type': 'Label',
            'x': '680', 'y': '200', 'w': '487', 'h': '567'
        })
        ET.SubElement(products_box, 'label', {'xml:lang': 'pt-br'}).text = 'Produtos e servicos'
        self._apply_label_style(products_box)

        journey_container = ET.SubElement(ctx_view, 'node', {
            'identifier': f"id-ctx-jornada-{uuid.uuid4().hex[:6]}",
            'xsi:type': 'Label',
            'x': '80', 'y': '673', 'w': '340', 'h': '107'
        })
        ET.SubElement(journey_container, 'label', {'xml:lang': 'pt-br'}).text = 'Jornada Tech / Issue Forum Arquitetura'
        self._apply_label_style(journey_container, bold=True)

        positions = {
            'actors': {'x': 110, 'y': 220, 'spacing': 70, 'w': 280, 'h': 50},
            'channels': {'x': 450, 'y': 220, 'spacing': 70, 'w': 210, 'h': 50},
            'products': {'x': 700, 'y': 220, 'spacing': 70, 'w': 450, 'h': 50},
            'external_systems': {'x': 700, 'y': 500, 'spacing': 70, 'w': 450, 'h': 50},
        }

        visuals_by_element: Dict[str, str] = {}
        for area_name, elems in by_area.items():
            if area_name not in positions:
                continue
            cfg = positions[area_name]
            for idx, (old_id, name, elem_type) in enumerate(elems):
                element_id = elements_map.get(old_id)
                if not element_id:
                    continue
                visual_id = f"id-visual-{uuid.uuid4().hex[:6]}"
                node = ET.SubElement(ctx_view, 'node', {
                    'identifier': visual_id,
                    'elementRef': element_id,
                    'xsi:type': 'Element',
                    'x': str(cfg['x']),
                    'y': str(cfg['y'] + idx * cfg['spacing']),
                    'w': str(cfg['w']),
                    'h': str(cfg['h'])
                })
                visuals_by_element[element_id] = visual_id
                style = ET.SubElement(node, 'style', {'lineWidth': '1'})
                if area_name == 'actors':
                    color = (255, 255, 191, 100)
                elif area_name == 'channels':
                    color = (215, 245, 255, 100)
                elif area_name == 'products':
                    color = (184, 231, 252, 100)
                else:
                    color = (214, 248, 184, 100)
                ET.SubElement(style, 'fillColor', {'r': str(color[0]), 'g': str(color[1]), 'b': str(color[2]), 'a': str(color[3])})
                ET.SubElement(style, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})
                font = ET.SubElement(style, 'font', {'name': 'Arial', 'size': '10'})
                ET.SubElement(font, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

        if steps_labels:
            steps_container = ET.SubElement(ctx_view, 'node', {
                'identifier': f"id-ctx-steps-{uuid.uuid4().hex[:6]}",
                'xsi:type': 'Container',
                'x': '1180', 'y': '200', 'w': '320', 'h': '567'
            })
            ET.SubElement(steps_container, 'label', {'xml:lang': 'pt-br'}).text = 'Etapas'
            self._apply_container_style(steps_container)

            base_y = 230
            line_height = 24
            for idx, step in enumerate(steps_labels[:25], start=1):
                label_node = ET.SubElement(steps_container, 'node', {
                    'identifier': f"id-ctx-step-{uuid.uuid4().hex[:6]}",
                    'xsi:type': 'Label',
                    'x': '1195',
                    'y': str(base_y + (idx - 1) * line_height),
                    'w': '285',
                    'h': '20'
                })
                text = step if step.strip().startswith(f"{idx}.") else f"{idx}. {step}"
                ET.SubElement(label_node, 'label', {'xml:lang': 'pt-br'}).text = text
                label_style = ET.SubElement(label_node, 'style', {'lineWidth': '1'})
                ET.SubElement(label_style, 'fillColor', {'r': '255', 'g': '255', 'b': '255', 'a': '0'})
                ET.SubElement(label_style, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '0'})
                font = ET.SubElement(label_style, 'font', {'name': 'Arial', 'size': '10'})
                ET.SubElement(font, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

        for (src, rel_type, tgt), rel_id in relationship_map.items():
            src_visual = visuals_by_element.get(src)
            tgt_visual = visuals_by_element.get(tgt)
            if not src_visual or not tgt_visual:
                continue
            connection = ET.SubElement(ctx_view, 'connection', {
                'identifier': f"id-conn-{uuid.uuid4().hex[:6]}",
                'xsi:type': 'Relationship',
                'relationshipRef': rel_id,
                'source': src_visual,
                'target': tgt_visual
            })
            cstyle = ET.SubElement(connection, 'style', {'lineWidth': '1'})
            ET.SubElement(cstyle, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

        xml_str = ET.tostring(root, encoding='unicode')
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

    def _emit_context_header_labels(self, view_elem: ET.Element, system_name: str) -> None:
        """Adiciona cabeçalho padrão da visão de contexto."""
        bg = ET.SubElement(
            view_elem,
            'node',
            {
                'identifier': f'id-ctx-header-bg-{uuid.uuid4().hex[:6]}',
                'xsi:type': 'Label',
                'x': '0',
                'y': '40',
                'w': '620',
                'h': '80',
            },
        )
        ET.SubElement(bg, 'label', {'xml:lang': 'pt-br'}).text = ''
        self._apply_transparent_style(bg)

        title = ET.SubElement(
            view_elem,
            'node',
            {
                'identifier': f'id-ctx-title-{uuid.uuid4().hex[:6]}',
                'xsi:type': 'Label',
                'x': '120',
                'y': '40',
                'w': '607',
                'h': '40',
            },
        )
        ET.SubElement(title, 'label', {'xml:lang': 'pt-br'}).text = 'Plataforma e Produtos de Dados'
        self._apply_title_style(title)

        subtitle = ET.SubElement(
            view_elem,
            'node',
            {
                'identifier': f'id-ctx-subtitle-{uuid.uuid4().hex[:6]}',
                'xsi:type': 'Label',
                'x': '120',
                'y': '80',
                'w': '620',
                'h': '33',
            },
        )
        ET.SubElement(subtitle, 'label', {'xml:lang': 'pt-br'}).text = f'Visao de contexto - {system_name}'
        self._apply_subtitle_style(subtitle)

    def _apply_container_style(self, elem: ET.Element) -> None:
        style = ET.SubElement(elem, 'style', {'lineWidth': '1'})
        ET.SubElement(style, 'fillColor', {'r': '251', 'g': '251', 'b': '251', 'a': '100'})
        ET.SubElement(style, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})
        font = ET.SubElement(style, 'font', {'name': 'arial', 'size': '10', 'style': 'bold'})
        ET.SubElement(font, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

    def _apply_label_style(self, elem: ET.Element, bold: bool = False) -> None:
        style = ET.SubElement(elem, 'style', {'lineWidth': '1'})
        ET.SubElement(style, 'fillColor', {'r': '255', 'g': '255', 'b': '255', 'a': '100'})
        ET.SubElement(style, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})
        font_style = 'bold' if bold else 'plain'
        font_size = '10' if bold else '8'
        font = ET.SubElement(style, 'font', {'name': 'arial', 'size': font_size, 'style': font_style})
        ET.SubElement(font, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

    def _apply_transparent_style(self, elem: ET.Element) -> None:
        style = ET.SubElement(elem, 'style', {'lineWidth': '1'})
        ET.SubElement(style, 'fillColor', {'r': '255', 'g': '255', 'b': '255', 'a': '0'})
        ET.SubElement(style, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '0'})
        font = ET.SubElement(style, 'font', {'name': 'arial', 'size': '24', 'style': 'bold'})
        ET.SubElement(font, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

    def _apply_title_style(self, elem: ET.Element) -> None:
        style = ET.SubElement(elem, 'style', {'lineWidth': '1'})
        ET.SubElement(style, 'fillColor', {'r': '255', 'g': '255', 'b': '255', 'a': '0'})
        ET.SubElement(style, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '0'})
        font = ET.SubElement(style, 'font', {'name': 'arial', 'size': '24', 'style': 'bold'})
        ET.SubElement(font, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})

    def _apply_subtitle_style(self, elem: ET.Element) -> None:
        style = ET.SubElement(elem, 'style', {'lineWidth': '1'})
        ET.SubElement(style, 'fillColor', {'r': '255', 'g': '255', 'b': '255', 'a': '0'})
        ET.SubElement(style, 'lineColor', {'r': '0', 'g': '0', 'b': '0', 'a': '0'})
        font = ET.SubElement(style, 'font', {'name': 'arial', 'size': '16', 'style': 'plain'})
        ET.SubElement(font, 'color', {'r': '0', 'g': '0', 'b': '0', 'a': '100'})
