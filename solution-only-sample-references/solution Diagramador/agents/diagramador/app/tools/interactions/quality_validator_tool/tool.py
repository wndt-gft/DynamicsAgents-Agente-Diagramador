from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import unquote_to_bytes
import zipfile
import xml.etree.ElementTree as ET

from dynamic_agents import RuntimeToolError

try:
    from agents.diagramador.app.settings import get_metamodel_path
    from agents.diagramador.app.tools.shared.diagram_generator.validators.c4_quality_validator import (
        C4QualityValidator,
    )
except ImportError:  # pragma: no cover - fallback when package context is missing
    import sys

    repo_root = Path(__file__).resolve().parents[6]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from agents.diagramador.app.settings import get_metamodel_path
    from agents.diagramador.app.tools.shared.diagram_generator.validators.c4_quality_validator import (
        C4QualityValidator,
    )


def _looks_like_xml(value: str) -> bool:
    return isinstance(value, str) and value.lstrip().startswith("<")


def _decode_data_url(data_url: str) -> str:
    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        return ""

    header, _, encoded = data_url.partition(",")
    if not _:
        return ""

    try:
        if ";base64" in header:
            binary = base64.b64decode(encoded)
        else:
            binary = unquote_to_bytes(encoded)
    except Exception:  # pragma: no cover - fallback defensivo
        return ""

    if "application/zip" in header:
        try:
            with zipfile.ZipFile(BytesIO(binary)) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".xml"):
                        return zf.read(name).decode("utf-8", "ignore")
        except Exception:  # pragma: no cover - fallback defensivo
            return ""

    charset = "utf-8"
    for part in header.split(";"):
        if part.startswith("charset="):
            charset = part.split("=", 1)[1] or charset

    try:
        return binary.decode(charset, "ignore")
    except Exception:  # pragma: no cover
        return binary.decode("utf-8", "ignore")


class Tool:
    """Adapter que reutiliza o validador legado de qualidade C4."""

    def __init__(self, metadata: Optional[Dict[str, Any]] = None):
        self.metadata = metadata or {}
        metamodel_path = self.metadata.get("metamodelo")
        if metamodel_path:
            path = Path(metamodel_path)
            if not path.is_absolute():
                path = Path(__file__).resolve().parent / path
            metamodel = str(path)
        else:
            metamodel = str(get_metamodel_path())

        self.validator = C4QualityValidator(metamodel)

    def evaluate_quality(
        self,
        xml_content: Any,
        elements: Optional[List[Dict[str, Any]]] = None,
        relationships: Optional[List[Dict[str, Any]]] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = state or {}

        xml_candidate = self._resolve_state_reference(xml_content, state)
        xml_text = self._extract_xml_content(xml_candidate)

        if not xml_text:
            for reference in (
                "diagram.last_result.xml_content",
                "diagram.laast_result.xml_content",
                "diagram.last_result.storage.local_path",
                "diagram.laast_result.storage.local_path",
                "diagram.last_result.local_path",
                "diagram.laast_result.local_path",
                "diagram.xml_path",
            ):
                candidate = self._lookup_state_value(state, reference)
                if candidate:
                    xml_text = self._extract_xml_content(candidate)
                    if xml_text:
                        break

        if not xml_text:
            xml_text = self._search_state_for_xml(state)

        if not xml_text:
            raise RuntimeToolError("O conteúdo XML é obrigatório para avaliação de qualidade.")

        elements = self._resolve_state_reference(elements, state)
        if elements is None:
            elements = self._lookup_state_value(state, "analysis.elements")

        relationships = self._resolve_state_reference(relationships, state)
        if relationships is None:
            relationships = self._lookup_state_value(state, "analysis.relationships")

        try:
            report = self.validator.validate_diagram_quality(xml_text)
        except Exception as exc:  # pragma: no cover - erro inesperado do validador legado
            raise RuntimeToolError(f"Falha ao avaliar qualidade: {exc}") from exc

        badge = self.validator.generate_quality_badge(report.quality_level)
        layers_detected = self._extract_layers(xml_text)

        quality = {
            "score": round(report.overall_score, 2),
            "level": badge,
            "level_id": getattr(report.quality_level, "name", str(report.quality_level)),
            "metamodel": round(report.metamodel_compliance, 2),
            "structure": round(report.c4_structure_score, 2),
            "nomenclature": round(report.naming_conventions_score, 2),
            "documentation": round(report.documentation_score, 2),
            "relationships": report.relationships_count,
            "elements": report.elements_count,
            "is_metamodel_compliant": report.is_metamodel_compliant,
            "recommendations": report.recommendations,
            "issues": report.issues,
            "layers_detected": layers_detected,
        }

        if elements is not None:
            quality["input_elements"] = len(elements)
        if relationships is not None:
            quality["input_relationships"] = len(relationships)

        return {"quality": quality}

    @staticmethod
    def _lookup_state_value(state: Dict[str, Any], reference: Any) -> Any:
        if not state or reference in (None, ""):
            return None

        tokens = list(Tool._iter_reference_tokens(reference))
        if not tokens:
            return None

        current: Any = state
        for token in tokens:
            if isinstance(current, dict):
                current = current.get(token)
            elif isinstance(current, (list, tuple)):
                try:
                    index = int(token)
                except (TypeError, ValueError):
                    return None
                if index < 0 or index >= len(current):
                    return None
                current = current[index]
            else:
                return None
        return current

    def _resolve_state_reference(self, payload: Any, state: Dict[str, Any]) -> Any:
        if not isinstance(payload, dict):
            return payload

        if "$state" in payload:
            resolved = self._lookup_state_value(state, payload.get("$state"))
            if resolved is not None:
                return resolved
            reference = payload.get("$state")
            if isinstance(reference, dict):
                for key in ("path", "value", "segments"):
                    if key in reference:
                        return self._lookup_state_value(state, reference[key])
            return None

        if "$input" in payload:
            return self._lookup_input_value(state, payload.get("$input"))

        return payload

    @staticmethod
    def _iter_reference_tokens(reference: Any) -> Iterable[str]:
        if isinstance(reference, str):
            normalized = reference.replace("[", ".").replace("]", ".")
            for raw in normalized.split("."):
                token = raw.strip()
                if token:
                    yield token
        elif isinstance(reference, dict):
            for key in ("path", "value", "segments"):
                if key in reference:
                    yield from Tool._iter_reference_tokens(reference[key])
                    return
        elif isinstance(reference, (list, tuple, set)):
            for item in reference:
                yield from Tool._iter_reference_tokens(item)
        elif reference is not None:
            token = str(reference).strip()
            if token:
                yield token

    def _lookup_input_value(self, state: Dict[str, Any], reference: Any) -> Any:
        if not isinstance(state, dict) or reference in (None, ""):
            return None

        tokens = list(self._iter_reference_tokens(reference))
        if not tokens:
            return None

        containers: List[Any] = [state]
        containers.extend(self._candidate_input_containers(state))

        for container in containers:
            if isinstance(container, dict):
                resolved = self._lookup_state_value(container, tokens)
                if resolved not in (None, "", []):
                    return resolved
            elif isinstance(container, (list, tuple, set)):
                for item in container:
                    if isinstance(item, dict):
                        resolved = self._lookup_state_value(item, tokens)
                        if resolved not in (None, "", []):
                            return resolved

        if len(tokens) == 1:
            fallback = self._search_key_anywhere(state, tokens[0])
            if fallback not in (None, "", []):
                return fallback

        return None

    def _candidate_input_containers(self, state: Dict[str, Any]) -> List[Any]:
        containers: List[Any] = []
        if not isinstance(state, dict):
            return containers

        stack: List[Any] = [state]
        seen: set[int] = set()

        while stack:
            current = stack.pop()
            object_id = id(current)
            if object_id in seen:
                continue
            seen.add(object_id)

            if isinstance(current, dict):
                for key, value in current.items():
                    if key in {"inputs", "input", "$inputs", "$input", "parameters", "kwargs"}:
                        containers.append(value)
                    if isinstance(value, (dict, list, tuple, set)):
                        stack.append(value)
            elif isinstance(current, (list, tuple, set)):
                stack.extend(current)

        return containers

    def _search_key_anywhere(self, structure: Any, key: str) -> Any:
        if not key:
            return None

        stack: List[Any] = [structure]
        seen: set[int] = set()

        while stack:
            current = stack.pop()
            object_id = id(current)
            if object_id in seen:
                continue
            seen.add(object_id)

            if isinstance(current, dict):
                if key in current and current[key] not in (None, "", []):
                    return current[key]
                stack.extend(current.values())
            elif isinstance(current, (list, tuple, set)):
                stack.extend(current)

        return None

    def _search_state_for_xml(self, state: Dict[str, Any]) -> str:
        if not isinstance(state, dict):
            return ""

        for key in ("xml_content", "xml", "content", "body", "local_path"):
            candidate = self._search_key_anywhere(state, key)
            xml_text = self._extract_xml_content(candidate)
            if xml_text:
                return xml_text

        return ""

    def _extract_xml_content(self, payload: Any) -> str:
        if payload is None:
            return ""

        if isinstance(payload, (bytes, bytearray)):
            try:
                decoded = payload.decode("utf-8")
            except Exception:  # pragma: no cover - fallback defensivo
                decoded = bytes(payload).decode("utf-8", "ignore")
            return decoded if _looks_like_xml(decoded) else ""

        if isinstance(payload, str):
            if _looks_like_xml(payload):
                return payload
            if payload.startswith("data:"):
                decoded = _decode_data_url(payload)
                if _looks_like_xml(decoded):
                    return decoded
            potential_path = Path(payload)
            if potential_path.exists():
                try:
                    text = potential_path.read_text(encoding="utf-8")
                except Exception:
                    text = ""
                if _looks_like_xml(text):
                    return text
            return ""

        if isinstance(payload, dict):
            for key in ("xml_content", "content", "xml", "value", "body", "text"):
                if key in payload:
                    extracted = self._extract_xml_content(payload[key])
                    if _looks_like_xml(extracted):
                        return extracted

            diagram_section = payload.get("diagram") if isinstance(payload.get("diagram"), dict) else None
            if diagram_section and "last_result" in diagram_section:
                return self._extract_xml_content(diagram_section["last_result"])

            for key in ("artifact", "storage", "last_result"):
                nested = payload.get(key)
                if isinstance(nested, dict):
                    extracted = self._extract_xml_content(nested)
                    if _looks_like_xml(extracted):
                        return extracted

        for value in payload.values():
            extracted = self._extract_xml_content(value)
            if _looks_like_xml(extracted):
                return extracted

        signed_url = payload.get("signed_url")
        if isinstance(signed_url, str) and signed_url.startswith("data:"):
            decoded = _decode_data_url(signed_url)
            if _looks_like_xml(decoded):
                return decoded

        path_value = payload.get("local_path") or payload.get("local_file_path")
        if isinstance(path_value, str):
            try:
                text = Path(path_value).read_text(encoding="utf-8")
            except Exception:
                text = ""
            if _looks_like_xml(text):
                return text

            return ""

        if isinstance(payload, (list, tuple, set)):
            for item in payload:
                extracted = self._extract_xml_content(item)
                if _looks_like_xml(extracted):
                    return extracted
            return ""

        return ""

    def _extract_layers(self, xml_content: str) -> Dict[str, int]:
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return {}

        namespaces = {
            "a": "http://www.opengroup.org/xsd/archimate/3.0/",
        }
        buckets: Dict[str, int] = {}
        for elem in root.findall(".//a:element", namespaces):
            element_id = elem.get("identifier")
            if not element_id:
                continue
            # Layer é codificado no template por meio do nome do view elemento.
            # Inspecionar documentações associadas para inferir layer.
            documentation = "".join(doc.text or "" for doc in elem.findall("a:documentation", namespaces))
            marker = self._detect_layer_marker(documentation)
            if marker:
                buckets[marker] = buckets.get(marker, 0) + 1
        return buckets

    @staticmethod
    def _detect_layer_marker(documentation: str) -> Optional[str]:
        doc = (documentation or "").lower()
        if "channels" in doc:
            return "channels"
        if "gateway inbound" in doc or "inbound" in doc:
            return "gateway_inbound"
        if "execution logic" in doc:
            return "execution_logic"
        if "data management" in doc:
            return "data_management"
        if "gateway outbound" in doc or "outbound" in doc:
            return "gateway_outbound"
        if "external integration" in doc:
            return "external_integration"
        return None


__all__ = ["Tool"]
