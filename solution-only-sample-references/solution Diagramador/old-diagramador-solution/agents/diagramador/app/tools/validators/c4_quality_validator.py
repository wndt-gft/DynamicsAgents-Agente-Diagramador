"""C4 Quality Validator

Provides quality validation for ArchiMate XML diagrams with C4 Container focus.
Exposes two APIs:
 - validate_c4_quality(xml) -> C4QualityReport (rich dataclass)
 - validate_c4_compliance(xml) -> dict (lightweight summary used by legacy tests)
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class C4ContainerQuality(Enum):
    EXCELLENT = 10
    VERY_GOOD = 8
    GOOD = 7
    FAIR = 6
    POOR = 4
    INVALID = 0


@dataclass
class QualityMetric:
    name: str
    score: float
    max_score: float
    description: str
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'score': self.score,
            'max_score': self.max_score,
            'description': self.description,
            'recommendations': self.recommendations
        }


@dataclass
class C4QualityReport:
    overall_score: float
    quality_level: C4ContainerQuality
    metrics: List[QualityMetric]
    summary: str
    elements_count: int
    relationships_count: int
    issues: List[str]
    recommendations: List[str]
    is_metamodel_compliant: bool = True
    metamodel_compliance: float = 0.0
    c4_structure_score: float = 0.0
    naming_conventions_score: float = 0.0
    relationships_score: float = 0.0
    documentation_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'overall_score': self.overall_score,
            'quality_level': self.quality_level.name,
            'metrics': [m.to_dict() for m in self.metrics],
            'summary': self.summary,
            'elements_count': self.elements_count,
            'relationships_count': self.relationships_count,
            'issues': self.issues,
            'recommendations': self.recommendations,
            'is_metamodel_compliant': self.is_metamodel_compliant,
            'metamodel_compliance': self.metamodel_compliance,
            'c4_structure_score': self.c4_structure_score,
            'naming_conventions_score': self.naming_conventions_score,
            'relationships_score': self.relationships_score,
            'documentation_score': self.documentation_score
        }


class C4QualityValidator:
    def __init__(self, metamodel_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.metamodel_path = metamodel_path
        self.naming_patterns = {
            'ApplicationComponent': r'^[A-Z][a-zA-Z0-9]+(?:Service|Application|System|API)?$',
            'DataObject': r'^[A-Z][a-zA-Z0-9]+(?:Database|Store|Repository|Cache)?$',
            'TechnologyService': r'^[A-Z][a-zA-Z0-9]+(?:Service|Platform|Infrastructure)?$'
        }

    # ---------- Public Rich Report API ----------
    def validate_c4_quality(self, xml_content: str) -> C4QualityReport:
        try:
            root = ET.fromstring(xml_content)
            namespaces = self._detect_namespaces(root)
            metrics: List[QualityMetric] = []
            structure_metric = self._validate_structure(root, namespaces)
            naming_metric = self._validate_naming(root, namespaces)
            relationships_metric = self._validate_relationships(root, namespaces)
            documentation_metric = self._validate_documentation(root, namespaces)
            c4_compliance_metric = self._validate_c4_compliance(root, namespaces)
            metrics.extend([
                structure_metric,
                naming_metric,
                relationships_metric,
                documentation_metric,
                c4_compliance_metric
            ])
            total_score = sum(m.score for m in metrics)
            max_total = sum(m.max_score for m in metrics)
            overall_score = (total_score / max_total) * 100 if max_total else 0
            quality_level = self._determine_quality_level(overall_score)
            elements = self._get_elements(root, namespaces)
            relationships = self._get_relationships(root, namespaces)
            recommendations: List[str] = []
            for m in metrics:
                recommendations.extend(m.recommendations)
            c4_structure_score = (structure_metric.score / structure_metric.max_score) * 100 if structure_metric.max_score else 0
            naming_conventions_score = (naming_metric.score / naming_metric.max_score) * 100 if naming_metric.max_score else 0
            relationships_score = (relationships_metric.score / relationships_metric.max_score) * 100 if relationships_metric.max_score else 0
            documentation_score = (documentation_metric.score / documentation_metric.max_score) * 100 if documentation_metric.max_score else 0
            is_metamodel_compliant = overall_score >= 70.0
            metamodel_compliance = overall_score
            return C4QualityReport(
                overall_score=overall_score,
                quality_level=quality_level,
                metrics=metrics,
                summary=f"Diagrama com qualidade {quality_level.name} ({overall_score:.1f}%)",
                elements_count=len(elements),
                relationships_count=len(relationships),
                issues=[],
                recommendations=recommendations,
                is_metamodel_compliant=is_metamodel_compliant,
                metamodel_compliance=metamodel_compliance,
                c4_structure_score=c4_structure_score,
                naming_conventions_score=naming_conventions_score,
                relationships_score=relationships_score,
                documentation_score=documentation_score
            )
        except ET.ParseError as e:
            return self._create_error_report(f"XML inválido: {e}")
        except Exception as e:  # pragma: no cover (defensive)
            logger.exception("Erro inesperado na validação C4")
            return self._create_error_report(str(e))

    # --- Compatibility wrapper expected by DiagramService ---
    def validate_diagram_quality(self, xml_content: str) -> C4QualityReport:  # noqa: D401
        """Wrapper delegando para validate_c4_quality (API esperada externamente)."""
        return self.validate_c4_quality(xml_content)

    def generate_quality_badge(self, quality_level: C4ContainerQuality) -> str:  # noqa: D401
        """Gera badge textual simples para nível de qualidade (compatibilidade)."""
        try:
            name = quality_level.name if isinstance(quality_level, C4ContainerQuality) else str(quality_level)
        except Exception:  # pragma: no cover
            name = str(quality_level)
        palette = {
            'EXCELLENT': '✅',
            'VERY_GOOD': '🌟',
            'GOOD': '👍',
            'FAIR': '➖',
            'POOR': '⚠️',
            'INVALID': '❌'
        }
        icon = palette.get(name, '•')
        return f"{icon} {name}"

    # ---------- Legacy Lightweight API ----------
    def validate_c4_compliance(self, xml_content: str) -> Dict[str, Any]:
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return {"compliant": False, "score": 0, "errors": ["Invalid XML"], "recommendations": []}
        report = self.validate_c4_quality(xml_content)
        containers = self._count_containers(root)
        relationships = self._count_relationships(root)
        layers = self._detect_layers(root)
        score = min(100.0, report.overall_score)
        return {
            'compliant': score >= 70.0,
            'score': score,
            'containers_count': containers,
            'relationships_count': relationships,
            'layers_detected': layers,
            'recommendations': list(dict.fromkeys(report.recommendations)),  # dedup
            'documentation_score': report.documentation_score
        }

    # ---------- Internal helpers (subset from extended validator) ----------
    def _validate_structure(self, root: ET.Element, namespaces: Optional[Dict[str, str]] = None) -> QualityMetric:
        score = 0.0
        max_score = 10.0
        recs: List[str] = []
        elements = self._get_elements(root, namespaces)
        relationships = self._get_relationships(root, namespaces)
        if elements:
            score += 3
        else:
            recs.append("Adicionar elementos ao diagrama")
        if elements and relationships:
            ratio = len(relationships)/len(elements)
            if 0.5 <= ratio <= 3.0:
                score += 4
            else:
                recs.append("Balancear proporção entre elementos e relacionamentos")
        if self._has_hierarchical_structure(root, namespaces):
            score += 3
        else:
            recs.append("Considerar organização hierárquica dos elementos")
        return QualityMetric("Estrutura", score, max_score, "Validação da estrutura do diagrama", recs)

    def _validate_naming(self, root: ET.Element, namespaces: Optional[Dict[str, str]] = None) -> QualityMetric:
        max_score = 10.0
        elements = self._get_elements(root, namespaces)
        if not elements:
            return QualityMetric("Nomenclatura", 0, max_score, "Sem elementos para validar nomenclatura", ["Adicionar elementos ao diagrama"])
        valid = 0
        for e in elements:
            name = self._get_element_name(e)
            if name and len(name) > 3 and not name.startswith('id-'):
                valid += 1
        ratio = valid/len(elements) if elements else 0
        recs = [] if ratio >= 0.8 else ["Melhorar nomenclatura dos elementos"]
        return QualityMetric("Nomenclatura", ratio*max_score, max_score, "Validação das convenções de nomenclatura", recs)

    def _validate_relationships(self, root: ET.Element, namespaces: Optional[Dict[str, str]] = None) -> QualityMetric:
        max_score = 10.0
        elements = self._get_elements(root, namespaces)
        relationships = self._get_relationships(root, namespaces)
        if not relationships:
            return QualityMetric("Relacionamentos", 0, max_score, "Sem relacionamentos para validar", ["Adicionar relacionamentos entre elementos"])
        ids = {e.get('id') for e in elements if e.get('id')}
        valid = 0
        for r in relationships:
            if r.get('source') in ids and r.get('target') in ids:
                valid += 1
        ratio = valid/len(relationships) if relationships else 0
        recs = [] if ratio == 1.0 else ["Corrigir relacionamentos com referências inválidas"]
        return QualityMetric("Relacionamentos", ratio*max_score, max_score, "Validação dos relacionamentos", recs)

    def _validate_documentation(self, root: ET.Element, namespaces: Optional[Dict[str, str]] = None) -> QualityMetric:
        max_score = 10.0
        elements = self._get_elements(root, namespaces)
        if not elements:
            return QualityMetric("Documentação", 0, max_score, "Sem elementos para validar documentação", ["Adicionar elementos ao diagrama"])
        documented = 0
        for e in elements:
            doc = e.find('.//documentation')
            if doc is not None and doc.text and doc.text.strip():
                documented += 1
        ratio = documented/len(elements) if elements else 0
        recs = [] if ratio >= 0.7 else ["Adicionar documentação aos elementos"]
        return QualityMetric("Documentação", ratio*max_score, max_score, "Validação da documentação", recs)

    def _validate_c4_compliance(self, root: ET.Element, namespaces: Optional[Dict[str, str]] = None) -> QualityMetric:
        max_score = 10.0
        elements = self._get_elements(root, namespaces)
        if not elements:
            return QualityMetric("Conformidade C4", 0, max_score, "Sem elementos para validar conformidade C4", ["Adicionar elementos seguindo padrões C4"])
        c4_types = {'ApplicationComponent', 'DataObject', 'TechnologyService', 'SystemSoftware'}
        valid = 0
        for e in elements:
            t = e.get('type') or e.get('{http://www.w3.org/2001/XMLSchema-instance}type')
            if t and any(ct in t for ct in c4_types):
                valid += 1
        ratio = valid/len(elements)
        recs = [] if ratio >= 0.8 else ["Usar tipos de elementos apropriados para C4"]
        return QualityMetric("Conformidade C4", ratio*max_score, max_score, "Validação de conformidade com padrões C4", recs)

    # ---------- Primitive utilities ----------
    def _get_elements(self, root: ET.Element, namespaces: Optional[Dict[str, str]] = None) -> List[ET.Element]:
        els = root.findall('.//{http://www.opengroup.org/xsd/archimate/3.0/}element')
        if not els:
            els = root.findall('.//element')
        if not els:
            section = root.find('.//{http://www.opengroup.org/xsd/archimate/3.0/}elements') or root.find('.//elements')
            if section is not None:
                els = list(section)
        return els

    def _get_relationships(self, root: ET.Element, namespaces: Optional[Dict[str, str]] = None) -> List[ET.Element]:
        rels = root.findall('.//{http://www.opengroup.org/xsd/archimate/3.0/}relationship')
        if not rels:
            rels = root.findall('.//relationship')
        if not rels:
            section = root.find('.//{http://www.opengroup.org/xsd/archimate/3.0/}relationships') or root.find('.//relationships')
            if section is not None:
                rels = list(section)
        return rels

    def _get_element_name(self, element: ET.Element) -> Optional[str]:
        name_elem = element.find('.//n')
        if name_elem is not None and name_elem.text:
            return name_elem.text.strip()
        name = element.get('name')
        if name:
            return name.strip()
        return None

    def _has_hierarchical_structure(self, root: ET.Element, namespaces: Optional[Dict[str, str]] = None) -> bool:
        folders = root.findall('.//{http://www.opengroup.org/xsd/archimate/3.0/}folder') or root.findall('.//folder')
        groups = root.findall('.//{http://www.opengroup.org/xsd/archimate/3.0/}group') or root.findall('.//group')
        return bool(folders or groups)

    def _detect_namespaces(self, root: ET.Element) -> Dict[str, str]:
        ns = {}
        for k, v in root.attrib.items():
            if k.startswith('{http://www.w3.org/2000/xmlns/}'):
                ns[k.split('}')[1]] = v
            elif k == 'xmlns':
                ns[''] = v
        return ns

    def _determine_quality_level(self, score: float) -> C4ContainerQuality:
        if score >= 90.0:
            return C4ContainerQuality.EXCELLENT
        if score >= 80.0:
            return C4ContainerQuality.VERY_GOOD
        if score >= 70.0:
            return C4ContainerQuality.GOOD
        if score >= 60.0:
            return C4ContainerQuality.FAIR
        if score >= 40.0:
            return C4ContainerQuality.POOR
        return C4ContainerQuality.INVALID

    def _create_error_report(self, msg: str) -> C4QualityReport:
        return C4QualityReport(
            overall_score=0.0,
            quality_level=C4ContainerQuality.INVALID,
            metrics=[],
            summary=f"Erro na validação: {msg}",
            elements_count=0,
            relationships_count=0,
            issues=[msg],
            recommendations=["Verificar estrutura do arquivo XML"]
        )

    # Lightweight helpers for compliance summary
    def _count_containers(self, root: ET.Element) -> int:
        count = 0
        for elem in root.iter():
            t = elem.get('type', '') or elem.get('{http://www.w3.org/2001/XMLSchema-instance}type', '')
            n = elem.get('name', '')
            if 'Component' in t or 'Component' in n:
                count += 1
        return count

    def _count_relationships(self, root: ET.Element) -> int:
        count = 0
        for elem in root.iter():
            t = elem.get('type', '') or elem.get('{http://www.w3.org/2001/XMLSchema-instance}type', '')
            if 'Relationship' in t:
                count += 1
        return count

    def _detect_layers(self, root: ET.Element) -> List[str]:
        layers = []
        types = []
        for elem in root.iter():
            t = elem.get('type', '') or elem.get('{http://www.w3.org/2001/XMLSchema-instance}type', '')
            types.append(t)
        if any('Application' in t for t in types):
            layers.append('presentation')
        if any('Business' in t for t in types):
            layers.append('business')
        if any('Data' in t for t in types):
            layers.append('data')
        if any('Technology' in t or 'SystemSoftware' in t for t in types):
            layers.append('infrastructure')
        return layers


# --- Compatibility alias (legacy name expected by older imports) ---
try:  # pragma: no cover (defensive)
    C4MetamodelQualityValidator  # type: ignore[name-defined]
except NameError:  # Only define if not already injected
    class C4MetamodelQualityValidator(C4QualityValidator):  # noqa: D401
        """Alias de compatibilidade: mantém suporte a imports antigos.

        Futuro: substituir referências externas para C4QualityValidator e remover alias.
        """
        def validate_diagram_quality(self, xml_content: str) -> C4QualityReport:  # noqa: D401
            return super().validate_diagram_quality(xml_content)
        def generate_quality_badge(self, quality_level: C4ContainerQuality) -> str:  # noqa: D401
            return super().generate_quality_badge(quality_level)

__all__ = [
    'C4ContainerQuality', 'QualityMetric', 'C4QualityReport',
    'C4QualityValidator', 'C4MetamodelQualityValidator'
]
