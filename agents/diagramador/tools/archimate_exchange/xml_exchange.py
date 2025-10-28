#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArchiMate Exchange – Copy+Patch generator

Gera um XML ArchiMate válido a partir de:
  1) um template.xml (base),
  2) um datamodel JSON com dados estruturados (elements/relations),
  3) opcionalmente valida o resultado com os XSDs oficiais.

Princípios que evitam erros de import no Archi:
- Trabalha por CÓPIA + PATCH do template (não cria a árvore do zero).
- Mantém as declarações de namespace do template (sem duplicar xmlns).
- Escreve `xsi:type` **SEM prefixo** (ex.: "ApplicationComponent"), igual ao template fornecido.
- Respeita a ordem exigida pelo XSD quando injeta <name>/<documentation>.
- Converte quebras de documentação para "&#xD;" (CR literal), sem &amp;#xD;.

Entrada JSON (exemplo mínimo)
{
  "model_identifier": "id-model-123",
  "model_name": {"text": "Meu Modelo", "lang": "pt-BR"},
  "elements": [
    {
      "id": "id-el-1",
      "type": "ApplicationComponent",
      "name": {"text": "Serviço A"},
      "documentation": {"text": "Linha 1\nLinha 2"}
    }
  ],
  "relations": [
    {
      "id": "id-rel-1",
      "type": "ServingRelationship",
      "source": "id-el-1",
      "target": "id-el-2",
      "documentation": {"text": "Doc da relação"}
    }
  ]
}

Uso (CLI):
  python archimate_template_patcher.py \
      --template template.xml \
      --model-json datamodel.json \
      --out out.xml \
      [--validate-xsd-dir /caminho/para/xsds]

Autor: você
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Dict, Optional

try:
    from lxml import etree as ET  # type: ignore
    LXML_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - fallback for environments sem lxml
    from xml.dom import minidom
    from xml.etree import ElementTree as _ET

    LXML_AVAILABLE = False

    class _CompatET:
        """Fallback mínimo usando xml.etree.ElementTree quando lxml não está disponível."""

        Element = staticmethod(_ET.Element)
        SubElement = staticmethod(_ET.SubElement)
        QName = staticmethod(_ET.QName)
        ParseError = _ET.ParseError
        ElementTree = _ET.ElementTree
        _Element = _ET.Element

        @staticmethod
        def parse(source):
            return _ET.parse(source)

        @staticmethod
        def tostring(element_or_tree, encoding="utf-8", xml_declaration=False, pretty_print=False):
            if isinstance(element_or_tree, _ET.ElementTree):
                tree = element_or_tree
            else:
                tree = _ET.ElementTree(element_or_tree)

            buffer = io.BytesIO()
            tree.write(buffer, encoding=encoding, xml_declaration=xml_declaration)
            data = buffer.getvalue()

            if pretty_print:
                try:
                    parsed = minidom.parseString(data)
                    data = parsed.toprettyxml(indent="  ", encoding=encoding)
                except Exception:
                    # Mantém saída sem pretty print caso a formatação falhe
                    pass

            return data

        @staticmethod
        def XMLSchema(*_args, **_kwargs):
            raise ModuleNotFoundError(
                "A validação XSD requer a dependência opcional 'lxml'."
            )

        @staticmethod
        def fromstring(text):
            return _ET.fromstring(text)

    ET = _CompatET()  # type: ignore

ARCHI_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS   = "http://www.w3.org/2001/XMLSchema-instance"
XML_NS   = "http://www.w3.org/XML/1998/namespace"


def qn(tag: str) -> str:
    """Retorna o QName completo para uma tag dentro do namespace ArchiMate."""

    return str(ET.QName(ARCHI_NS, tag))


def _local_name(tag: str) -> str:
    """Extrai o localname de uma tag potencialmente qualificada."""

    if isinstance(tag, str):
        if tag.startswith("{"):
            return tag.rsplit("}", 1)[-1]
        return tag
    # Compatível com objetos QName do lxml
    return str(tag).rsplit("}", 1)[-1]


def _serialize_tree(tree: "ET.ElementTree") -> str:
    """Serializa uma árvore XML com declaração XML e identação estável."""

    if LXML_AVAILABLE:
        xml_bytes = ET.tostring(tree, encoding="utf-8", xml_declaration=True, pretty_print=True)
        return xml_bytes.decode("utf-8")

    xml_bytes = ET.tostring(tree, encoding="utf-8", xml_declaration=True, pretty_print=True)
    if isinstance(xml_bytes, bytes):
        return xml_bytes.decode("utf-8")
    return xml_bytes

# Ordem de filhos que manipulamos (subset suficiente e seguro)
ORDER: Dict[str, list[str]] = {
    "model": [
        "name", "documentation", "properties", "metadata",
        "elements", "relationships", "organizations", "propertyDefinitions",
        "views"
    ],
    "element": ["name", "documentation", "properties"],
    "relationship": ["documentation", "properties"],
}

# Mapeia "XxxRelationship" -> "Xxx" (valores do RelationshipTypeEnum no XSD)
REL_TYPE_MAP = {
    "CompositionRelationship": "Composition",
    "AggregationRelationship": "Aggregation",
    "AssignmentRelationship": "Assignment",
    "RealizationRelationship": "Realization",
    "ServingRelationship": "Serving",
    "AccessRelationship": "Access",
    "InfluenceRelationship": "Influence",
    "TriggeringRelationship": "Triggering",
    "FlowRelationship": "Flow",
    "SpecializationRelationship": "Specialization",
    "AssociationRelationship": "Association",
}

def _normalize_rel_type(t: str) -> str:
    if not t:
        return t
    local = t.split(":")[-1]
    return REL_TYPE_MAP.get(local, local)

def _normalize_text_payload(payload, default_lang: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """
    Accepts payload as dict {"text": "...", "lang": "..."} or plain string.
    Returns tuple (text, lang). ‘lang’ may be None to indicate no xml:lang attribute.
    """
    if payload is None:
        return None, default_lang
    if isinstance(payload, str):
        text = payload
        lang = default_lang
    elif isinstance(payload, dict):
        text = payload.get("text")
        lang = payload.get("lang", default_lang)
    else:
        text = None
        lang = default_lang
    if text is None:
        return None, lang
    return text, lang

def _encode_doc_cr_entities(s: str | None) -> str | None:
    """Converte quebras de linha para CR literal: '&#xD;' (mantendo \n após, para legibilidade)."""
    if s is None:
        return None
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", "&#xD;\n")
    return s

def _prune_invalid_identifierRefs(root: ET._Element) -> int:
    """Remove <item> inválidos da seção <organizations>, mesmo sem suporte a XPath."""

    organizations = root.find(qn("organizations"))
    if organizations is None:
        return 0

    all_ids = {el.get("identifier") for el in root.iter() if el.get("identifier")}
    removed = 0

    def prune_invalid(parent):
        nonlocal removed
        for child in list(parent):
            prune_invalid(child)
            if _local_name(child.tag) != "item":
                continue
            ref = child.get("identifierRef")
            if ref and ref not in all_ids:
                parent.remove(child)
                removed += 1

    prune_invalid(organizations)

    def remove_empty(parent):
        nonlocal removed
        changed = True
        while changed:
            changed = False

            def walk(node):
                nonlocal changed, removed
                for child in list(node):
                    walk(child)
                    if _local_name(child.tag) != "item":
                        continue
                    has_child_item = any(_local_name(grand.tag) == "item" for grand in child)
                    if child.get("identifierRef") is None and not has_child_item:
                        node.remove(child)
                        removed += 1
                        changed = True

            walk(parent)

    remove_empty(organizations)
    return removed

def _upsert_in_order(parent: ET._Element, tag: str, text: str, lang: Optional[str] = None) -> ET._Element:
    """Insere <tag> mantendo a sequência esperada pelo XSD para o 'parent'.
       Se já existir <tag>, substitui o conteúdo e garante que não tenha filhos indevidos.
    """
    parent_local = _local_name(parent.tag)
    seq = ORDER.get(parent_local, [])

    existing = None
    for ch in parent:
        if _local_name(ch.tag) == tag:
            existing = ch
            break

    if existing is None:
        # cálculo da posição de inserção baseada na ordem declarada
        idx_tag = seq.index(tag) if tag in seq else len(seq)
        insert_pos = len(parent)
        for i, ch in enumerate(list(parent)):
            loc = _local_name(ch.tag)
            if loc in seq and seq.index(loc) > idx_tag:
                insert_pos = i
                break
        el = ET.Element(qn(tag))
        if lang:
            el.set(ET.QName(XML_NS, "lang"), lang)
        el.text = text
        parent.insert(insert_pos, el)
        return el

    # substitui conteúdo
    for c in list(existing):
        existing.remove(c)
    existing.text = text
    # só seta xml:lang se for fornecido (evita mudar o template desnecessariamente)
    if lang is not None:
        existing.set(ET.QName(XML_NS, "lang"), lang)
    return existing

def _upsert_element(el_root: ET._Element, item: dict) -> ET._Element:
    """Upsert de <element> com 'xsi:type' **sem prefixo** e filhos ordenados (<name>, <documentation>)."""
    # localizar pelo identifier
    target = None
    for e in el_root.findall(qn("element")):
        if e.get("identifier") == item.get("id"):
            target = e
            break
    if target is None:
        target = ET.SubElement(el_root, qn("element"))
        if item.get("id"):
            target.set("identifier", item["id"])

    # xsi:type como localname sem prefixo, igual ao template
    t = item.get("type")
    if t:
        local = t.split(":")[-1]
        target.set(ET.QName(XSI_NS, "type"), local)

    # <name> (opcional) no lugar certo
    nm_text, nm_lang = _normalize_text_payload(item.get("name"))
    if nm_text:
        _upsert_in_order(target, "name", nm_text, nm_lang)

    # <documentation> (opcional) – converte CRs
    doc_text, doc_lang = _normalize_text_payload(item.get("documentation"))
    if doc_text:
        _upsert_in_order(target, "documentation", _encode_doc_cr_entities(doc_text), doc_lang)

    return target

def _upsert_relationship(rel_root: ET._Element, rel: dict) -> ET._Element:
    """Upsert de <relationship> com 'xsi:type' **sem prefixo** e só <documentation> (evita <name> em relação)."""
    target = None
    for r in rel_root.findall(qn("relationship")):
        if r.get("identifier") == rel.get("id"):
            target = r
            break
    if target is None:
        target = ET.SubElement(rel_root, qn("relationship"))
        if rel.get("id"):
            target.set("identifier", rel["id"])

    if rel.get("source"):
        target.set("source", rel["source"])
    if rel.get("target"):
        target.set("target", rel["target"])

    t = rel.get("type")
    if t:
        local = _normalize_rel_type(t)
        target.set(ET.QName(XSI_NS, "type"), local)

    # Só documentation (alguns XSDs não aceitam <name> em relationship)
    doc_text, doc_lang = _normalize_text_payload(rel.get("documentation"))
    if doc_text:
        _upsert_in_order(target, "documentation", _encode_doc_cr_entities(doc_text), doc_lang)

    return target


def _build_elements_tree(items: list[dict]) -> ET._Element:
    root = ET.Element(qn("elements"))
    for item in items:
        el = ET.Element(qn("element"))
        if item.get("id"):
            el.set("identifier", item["id"])
        t = item.get("type")
        if t:
            el.set(ET.QName(XSI_NS, "type"), t.split(":")[-1])

        nm_text, nm_lang = _normalize_text_payload(item.get("name"))
        if nm_text:
            _upsert_in_order(el, "name", nm_text, nm_lang)

        doc_text, doc_lang = _normalize_text_payload(item.get("documentation"))
        if doc_text:
            _upsert_in_order(el, "documentation", _encode_doc_cr_entities(doc_text), doc_lang)

        root.append(el)
    return root


def _build_relationships_tree(items: list[dict]) -> ET._Element:
    root = ET.Element(qn("relationships"))
    for rel in items:
        el = ET.Element(qn("relationship"))
        if rel.get("id"):
            el.set("identifier", rel["id"])
        if rel.get("source"):
            el.set("source", rel["source"])
        if rel.get("target"):
            el.set("target", rel["target"])
        t = rel.get("type")
        if t:
            el.set(ET.QName(XSI_NS, "type"), _normalize_rel_type(t))

        doc_text, doc_lang = _normalize_text_payload(rel.get("documentation"))
        if doc_text:
            _upsert_in_order(el, "documentation", _encode_doc_cr_entities(doc_text), doc_lang)

        root.append(el)
    return root


def _replace_child(parent: ET._Element, tag: str, new_child: Optional[ET._Element]) -> None:
    """Substitui o filho <tag> por um novo elemento, respeitando a ordem do XSD se possível."""
    children = list(parent)
    existing = None
    for idx, ch in enumerate(children):
        if _local_name(ch.tag) == tag:
            existing = (idx, ch)
            break

    if existing is not None:
        idx, ch = existing
        parent.remove(ch)
    else:
        seq = ORDER.get(_local_name(parent.tag), [])
        idx = len(children)
        if tag in seq:
            target_pos = seq.index(tag)
            for i, ch in enumerate(children):
                loc = _local_name(ch.tag)
                if loc in seq and seq.index(loc) > target_pos:
                    idx = i
                    break
    if new_child is not None:
        parent.insert(idx, new_child)


def _build_text_element(tag: str, payload, *, encode_doc: bool = False, default_lang: Optional[str] = None) -> Optional[ET._Element]:
    text, lang = _normalize_text_payload(payload, default_lang)
    if not text:
        return None
    el = ET.Element(qn(tag))
    if lang:
        el.set(ET.QName(XML_NS, "lang"), lang)
    el.text = _encode_doc_cr_entities(text) if encode_doc else text
    return el


def _build_style(style: Optional[dict]) -> Optional[ET._Element]:
    if not style:
        return None
    st = ET.Element(qn("style"))
    fill = style.get("fillColor")
    if fill:
        fc = ET.SubElement(st, qn("fillColor"))
        for attr in ("r", "g", "b", "a"):
            if attr in fill:
                fc.set(attr, str(fill[attr]))
    line = style.get("lineColor")
    if line:
        lc = ET.SubElement(st, qn("lineColor"))
        for attr in ("r", "g", "b", "a"):
            if attr in line:
                lc.set(attr, str(line[attr]))
    font = style.get("font")
    if font:
        ft = ET.SubElement(st, qn("font"))
        for attr in ("name", "size", "style"):
            if attr in font:
                ft.set(attr, str(font[attr]))
        color = font.get("color")
        if color:
            col = ET.SubElement(ft, qn("color"))
            for attr in ("r", "g", "b", "a"):
                if attr in color:
                    col.set(attr, str(color[attr]))
    return st


def _build_org_item(data: dict) -> ET._Element:
    item_el = ET.Element(qn("item"))
    attrs = data.get("attrs") or {}
    for key, value in attrs.items():
        item_el.set(key, str(value))

    children = data.get("children") or []
    child_idx = 0
    order = data.get("child_order") or []
    if order:
        for token in order:
            if token == "label":
                label_el = _build_text_element("label", data.get("label"))
                if label_el is not None:
                    item_el.append(label_el)
            elif token == "item":
                if child_idx < len(children):
                    item_el.append(_build_org_item(children[child_idx]))
                    child_idx += 1
    else:
        # fallback: label first, depois todos os filhos
        label_el = _build_text_element("label", data.get("label"))
        if label_el is not None:
            item_el.append(label_el)

    while child_idx < len(children):
        item_el.append(_build_org_item(children[child_idx]))
        child_idx += 1

    return item_el


def _build_organizations(payload: Optional[list[dict]]) -> Optional[ET._Element]:
    if not payload:
        return None
    orgs = ET.Element(qn("organizations"))
    for item in payload:
        orgs.append(_build_org_item(item))
    return orgs



def _build_view_connection(data: dict) -> ET._Element:
    conn = ET.Element(qn("connection"))
    if data.get("id"):
        conn.set("identifier", data["id"])
    if data.get("relationshipRef"):
        conn.set("relationshipRef", data["relationshipRef"])
    if data.get("source"):
        conn.set("source", data["source"])
    if data.get("target"):
        conn.set("target", data["target"])

    # xsi:type: default 'Relationship' when relationshipRef presente; senão 'Line' (livre)
    conn_type = (data.get("type") or "").split(":")[-1] if data.get("type") else None
    if not conn_type:
        conn_type = "Relationship" if data.get("relationshipRef") else "Line"
    conn.set(ET.QName(XSI_NS, "type"), conn_type)

    order = data.get("child_order") or []
    for token in order:
        child_el = None
        if token == "style":
            child_el = _build_style(data.get("style"))
        elif token == "label":
            child_el = _build_text_element("label", data.get("label"))
        elif token == "points":
            pts = data.get("points") or []
            if pts:
                child_el = ET.Element(qn("points"))
                for pt in pts:
                    p_el = ET.SubElement(child_el, qn("point"))
                    if "x" in pt: p_el.set("x", str(pt["x"]))
                    if "y" in pt: p_el.set("y", str(pt["y"]))
        if child_el is not None:
            conn.append(child_el)
    return conn



def _build_view_node(data: dict) -> ET._Element:
    node_el = ET.Element(qn("node"))
    if data.get("id"):
        node_el.set("identifier", data["id"])

    # bounds
    bounds = data.get("bounds") or {}
    for attr in ("x", "y", "w", "h"):
        if attr in bounds and bounds[attr] is not None:
            node_el.set(attr, str(bounds[attr]))

    # refs: aceitar tanto no topo quanto em 'refs'
    refs = dict(data.get("refs") or {})
    if "elementRef" not in refs and data.get("elementRef"):
        refs["elementRef"] = data["elementRef"]
    if "relationshipRef" not in refs and data.get("relationshipRef"):
        refs["relationshipRef"] = data["relationshipRef"]
    if "viewRef" not in refs and data.get("viewRef"):
        refs["viewRef"] = data["viewRef"]

    # xsi:type: se ausente em 'type', inferir
    node_type = (data.get("type") or "").split(":")[-1] if data.get("type") else None
    if not node_type:
        if "elementRef" in refs:
            node_type = "Element"
        else:
            # se tem subnodes vira Container; se tem label sem elementRef, vira Label
            sub_nodes = data.get("nodes")
            if sub_nodes is None:
                sub_nodes = data.get("children") or []
            if sub_nodes:
                node_type = "Container"
            elif data.get("label"):
                node_type = "Label"
            else:
                node_type = "Container"
    node_el.set(ET.QName(XSI_NS, "type"), node_type)

    # set refs as attributes
    if "elementRef" in refs:
        node_el.set("elementRef", refs["elementRef"])
    if "relationshipRef" in refs:
        node_el.set("relationshipRef", refs["relationshipRef"])

    # children ordering
    sub_nodes = data.get("nodes")
    if sub_nodes is None:
        sub_nodes = data.get("children") or []
    connections = data.get("connections") or []

    node_idx = 0
    conn_idx = 0
    order = data.get("child_order") or ["style", "label", "node", "connection", "viewRef"]

    for token in order:
        child_el = None
        if token == "style":
            child_el = _build_style(data.get("style"))
        elif token == "label":
            child_el = _build_text_element("label", data.get("label"))
        elif token == "node":
            if node_idx < len(sub_nodes):
                child_el = _build_view_node(sub_nodes[node_idx])
                node_idx += 1
        elif token == "connection":
            if conn_idx < len(connections):
                child_el = _build_view_connection(connections[conn_idx])
                conn_idx += 1
        elif token == "viewRef":
            view_ref = refs.get("viewRef")
            if view_ref:
                child_el = ET.Element(qn("viewRef"))
                child_el.set("ref", view_ref)
        if child_el is not None:
            node_el.append(child_el)

    # Append remaining
    while node_idx < len(sub_nodes):
        node_el.append(_build_view_node(sub_nodes[node_idx]))
        node_idx += 1
    while conn_idx < len(connections):
        node_el.append(_build_view_connection(connections[conn_idx]))
        conn_idx += 1

    return node_el


def _build_diagrams(payload: dict) -> Optional[ET._Element]:
    diagrams_data = payload.get("diagrams") if payload else None
    if not diagrams_data:
        return None
    diagrams_el = ET.Element(qn("diagrams"))
    for view_data in diagrams_data:
        view_el = ET.Element(qn("view"))
        if view_data.get("id"):
            view_el.set("identifier", view_data["id"])
        view_type = view_data.get("type")
        if view_type:
            view_el.set(ET.QName(XSI_NS, "type"), view_type.split(":")[-1])

        nodes = view_data.get("nodes") or []
        connections = view_data.get("connections") or []
        node_idx = 0
        conn_idx = 0
        order = view_data.get("child_order") or []
        for token in order:
            child_el = None
            if token == "name":
                child_el = _build_text_element("name", view_data.get("name"))
            elif token == "label":
                child_el = _build_text_element("label", view_data.get("label"))
            elif token == "documentation":
                child_el = _build_text_element("documentation", view_data.get("documentation"), encode_doc=True)
            elif token == "style":
                child_el = _build_style(view_data.get("style"))
            elif token == "node":
                if node_idx < len(nodes):
                    child_el = _build_view_node(nodes[node_idx])
                    node_idx += 1
            elif token == "connection":
                if conn_idx < len(connections):
                    child_el = _build_view_connection(connections[conn_idx])
                    conn_idx += 1
            if child_el is not None:
                view_el.append(child_el)

        while node_idx < len(nodes):
            view_el.append(_build_view_node(nodes[node_idx]))
            node_idx += 1
        while conn_idx < len(connections):
            view_el.append(_build_view_connection(connections[conn_idx]))
            conn_idx += 1

        diagrams_el.append(view_el)
    return diagrams_el

def patch_template_with_model(template_xml: str | Path, model_json: str | Path, out_xml: str | Path) -> Path:
    """Copia o template.xml, aplica patch com os dados do datamodel e grava o resultado."""
    template_xml = Path(template_xml)
    model_json = Path(model_json)
    out_xml = Path(out_xml)

    tree = ET.parse(str(template_xml))
    root = tree.getroot()  # mantém namespaces como no arquivo

    model = json.loads(model_json.read_text(encoding="utf-8"))

    # metadados do model
    if model.get("model_identifier"):
        root.set("identifier", model["model_identifier"])
    if model.get("model_name"):
        nm_text, nm_lang = _normalize_text_payload(model.get("model_name"))
        if nm_text:
            _upsert_in_order(root, "name", nm_text, nm_lang)

    # elements
    if "elements" in model:
        el_tree = _build_elements_tree(model.get("elements", []))
        _replace_child(root, "elements", el_tree)

    # relationships
    if "relations" in model:
        rel_tree = _build_relationships_tree(model.get("relations", []))
        _replace_child(root, "relationships", rel_tree)

    # organizations
    if "organizations" in model:
        orgs_el = _build_organizations(model.get("organizations"))
        _replace_child(root, "organizations", orgs_el)

    # views (diagrams)
    if "views" in model:
        views_payload = model.get("views") or {}
        views_root = root.find(qn("views"))
        if views_root is None:
            views_root = ET.SubElement(root, qn("views"))
        diagrams_el = _build_diagrams(views_payload)
        _replace_child(views_root, "diagrams", diagrams_el)

    # garante ordem correta dentro de <views>
    _ensure_views_sequence(tree)
    _ensure_view_children_order(tree)

    _prune_invalid_identifierRefs(tree)


    # serializa e corrige entidades numéricas de CR
    xml_txt = _serialize_tree(tree)
    xml_txt = xml_txt.replace("&amp;#xD;", "&#xD;")

    out_xml.parent.mkdir(parents=True, exist_ok=True)
    out_xml.write_text(xml_txt, encoding="utf-8")
    return out_xml

def _ensure_views_sequence(root: ET._Element) -> None:
    """views: garante <viewpoints> antes de <diagrams> e cria um viewpoint mínimo se faltar."""
    views = root.find(qn("views"))
    if views is None: return
    viewpoints = views.find(qn("viewpoints"))
    diagrams   = views.find(qn("diagrams"))

    if viewpoints is None:
        viewpoints = ET.Element(qn("viewpoints"))
        if diagrams is not None:
            idx = list(views).index(diagrams)
            views.insert(idx, viewpoints)
        else:
            views.insert(0, viewpoints)

    if diagrams is not None:
        kids = list(views)
        if kids.index(viewpoints) > kids.index(diagrams):
            views.remove(viewpoints)
            views.insert(kids.index(diagrams), viewpoints)

    # viewpoint mínimo (obrigatório pelo XSD)
    if viewpoints.find(qn("viewpoint")) is None:
        vp = ET.SubElement(viewpoints, qn("viewpoint"))
        vp.set("identifier", "id-viewpoint-default")
        nm = ET.SubElement(vp, qn("name"))
        nm.text = "Default Viewpoint"

def _ensure_view_children_order(root: ET._Element) -> None:
    """
    Para cada <view> em <views>/<diagrams>, garante que <name> exista e seja o PRIMEIRO filho.
    Não mexe em nodes/connections além disso.
    """
    views = root.find(qn("views"))
    if views is None: return
    diagrams = views.find(qn("diagrams"))
    if diagrams is None: return

    # Alguns templates usam tag 'view' (Archi) — cobrir 'view' e 'diagram' por segurança
    for tag in ("view", "diagram"):
        for v in diagrams.findall(qn(tag)):
            # procura <name>
            name_el = None
            for ch in v:
                if _local_name(ch.tag) == "name":
                    name_el = ch
                    break
            if name_el is None:
                name_el = ET.Element(qn("name"))
                name_el.text = "View"
                v.insert(0, name_el)
            else:
                # move para primeira posição se necessário
                first = v[0] if len(v) else None
                if first is not name_el:
                    v.remove(name_el)
                    v.insert(0, name_el)
    """
    Garante a ordem e o conteúdo mínimo de <views>:
      - <viewpoints> (obrigatório) ANTES de <diagrams>
      - <viewpoints> deve conter pelo menos um <viewpoint> com <name>
    Não altera conteúdo de <diagrams>.
    """
    views = root.find(qn("views"))
    if views is None:
        return

    viewpoints = views.find(qn("viewpoints"))
    diagrams   = views.find(qn("diagrams"))

    # cria <viewpoints> se não existir
    if viewpoints is None:
        viewpoints = ET.Element(qn("viewpoints"))
        if diagrams is not None:
            idx = list(views).index(diagrams)
            views.insert(idx, viewpoints)
        else:
            views.insert(0, viewpoints)

    # reposiciona <viewpoints> para vir antes de <diagrams> (se necessário)
    if diagrams is not None:
        children = list(views)
        if children.index(viewpoints) > children.index(diagrams):
            views.remove(viewpoints)
            idx = children.index(diagrams)
            views.insert(idx, viewpoints)

    # conteúdo mínimo: pelo menos 1 <viewpoint> com <name>
    vp = viewpoints.find(qn("viewpoint"))
    if vp is None:
        vp = ET.SubElement(viewpoints, qn("viewpoint"))
        vp.set("identifier", "id-viewpoint-default")
        nm = ET.SubElement(vp, qn("name"))
        nm.text = "Default Viewpoint"
        # xml:lang é opcional; inclua se quiser:
        # nm.set(ET.QName(XML_NS, "lang"), "pt-BR")
    """
    Garante a ordem exigida pelo XSD dentro de <views>:
      <viewpoints> (obrigatório) antes de <diagrams>.
    - Se não existir <viewpoints>, cria um vazio e insere antes de <diagrams>.
    - Se existir, mas vier depois de <diagrams>, move para antes.
    Não altera nada dentro de <diagrams> ou <viewpoints>.
    """
    views = root.find(qn("views"))
    if views is None:
        return

    viewpoints = views.find(qn("viewpoints"))
    diagrams   = views.find(qn("diagrams"))

    # se não há <viewpoints>, cria
    if viewpoints is None:
        viewpoints = ET.Element(qn("viewpoints"))
        if diagrams is not None:
            # insere imediatamente antes de <diagrams>
            idx = list(views).index(diagrams)
            views.insert(idx, viewpoints)
        else:
            # insere como primeiro filho de <views>
            views.insert(0, viewpoints)
        return

    # se já existe, mas está depois de <diagrams>, reposiciona
    if diagrams is not None:
        children = list(views)
        if children.index(viewpoints) > children.index(diagrams):
            views.remove(viewpoints)
            idx = children.index(diagrams)
            views.insert(idx, viewpoints)

# -------------------- Validação opcional por XSD (offline) --------------------

def _ensure_local_xml_xsd(xsd_dir: Path) -> Path:
    """Cria um xml.xsd mínimo local (define xml:lang) para uso offline."""
    xml_xsd = xsd_dir / "xml.xsd"
    if not xml_xsd.exists():
        xml_xsd.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"\n'
            '           targetNamespace="http://www.w3.org/XML/1998/namespace"\n'
            '           xmlns:xml="http://www.w3.org/XML/1998/namespace"\n'
            '           elementFormDefault="qualified"\n'
            '           attributeFormDefault="unqualified">\n'
            '  <xs:attribute name="lang" type="xs:language"/>\n'
            '</xs:schema>\n',
            encoding="utf-8"
        )
    return xml_xsd

def validate_with_full_xsd(xml_path: str | Path, xsd_dir: str | Path) -> tuple[bool, list[str]]:
    """
    Valida o XML gerado contra o conjunto completo de XSDs.
    Preferência: archimate3_Diagram.xsd (que redefine ViewsType para permitir <diagrams>).
    - Patching local: substitui o schemaLocation do xml.xsd dentro do Model.xsd
      e faz com que os demais XSDs apontem para as versões locais.
    """
    if not LXML_AVAILABLE:
        return False, [
            "Validação indisponível: instale a dependência opcional 'lxml' (ex.: pip install lxml)."
        ]

    xml_path = Path(xml_path)
    xsd_dir = Path(xsd_dir)

    diagram_xsd = xsd_dir / "archimate3_Diagram.xsd"
    view_xsd = xsd_dir / "archimate3_View.xsd"
    model_xsd = xsd_dir / "archimate3_Model.xsd"
    if not model_xsd.exists():
        return False, [f"XSD não encontrado: {model_xsd}"]

    # garante xml.xsd local
    _ensure_local_xml_xsd(xsd_dir)

    # patch do Model.xsd -> _archimate3_Model_local.xsd
    model_txt = model_xsd.read_text(encoding="utf-8")
    model_txt = model_txt.replace(
        'schemaLocation="http://www.w3.org/2001/xml.xsd"',
        'schemaLocation="xml.xsd"'
    )
    model_local = xsd_dir / "_archimate3_Model_local.xsd"
    model_local.write_text(model_txt, encoding="utf-8")

    view_local: Optional[Path] = None
    if view_xsd.exists():
        # patch do View.xsd -> incluir o Model_local
        view_txt = view_xsd.read_text(encoding="utf-8")
        view_txt = view_txt.replace(
            'schemaLocation="archimate3_Model.xsd"',
            'schemaLocation="_archimate3_Model_local.xsd"'
        )
        view_local = xsd_dir / "_archimate3_View_local.xsd"
        view_local.write_text(view_txt, encoding="utf-8")

    diagram_local: Optional[Path] = None
    if view_local is not None and diagram_xsd.exists():
        # patch do Diagram.xsd -> incluir o View_local
        diagram_txt = diagram_xsd.read_text(encoding="utf-8")
        diagram_txt = diagram_txt.replace(
            'schemaLocation="archimate3_View.xsd"',
            'schemaLocation="_archimate3_View_local.xsd"'
        )
        diagram_local = xsd_dir / "_archimate3_Diagram_local.xsd"
        diagram_local.write_text(diagram_txt, encoding="utf-8")

    if diagram_local is not None:
        schema_doc = ET.parse(str(diagram_local))
    elif view_local is not None:
        schema_doc = ET.parse(str(view_local))
    else:
        # fallback: validar só com o Model (sem views)
        schema_doc = ET.parse(str(model_local))
    schema = ET.XMLSchema(schema_doc)

    doc = ET.parse(str(xml_path))
    ok = schema.validate(doc)
    errors = [str(e) for e in schema.error_log]
    return ok, errors

# -------------------- CLI --------------------

def _cli() -> None:
    ap = argparse.ArgumentParser(description="ArchiMate Exchange – Copy+Patch generator")
    ap.add_argument("--template", required=True, help="Caminho para template.xml (base)")
    ap.add_argument("--model-json", required=True, help="Caminho para datamodel.json")
    ap.add_argument("--out", required=True, help="Caminho para o xml de saída")
    ap.add_argument("--validate-xsd-dir", help="Diretório contendo archimate3_Model.xsd (+ xml.xsd será criado)")
    args = ap.parse_args()

    out = patch_template_with_model(args.template, args.model_json, args.out)
    print(f"[OK] XML gerado: {out}")

    if args.validate_xsd_dir:
        ok, errs = validate_with_full_xsd(out, args.validate_xsd_dir)
        print(f"[VALIDAÇÃO] ArchiMate XSD: {'OK' if ok else 'FALHOU'}")
        if not ok:
            for e in errs[:10]:
                print(" -", e)


if __name__ == "__main__":
    _cli()
