"""Ferramenta de geração de diagramas reutilizando a implementação legada."""

from __future__ import annotations

import base64
import logging
import unicodedata
import os
import re
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import zipfile

from dynamic_agents import RuntimeToolError

logger = logging.getLogger(__name__)

try:
    from agents.diagramador.app.settings import get_output_root
    from agents.diagramador.app.tools.shared.diagram_generator.diagram_service import (
        DiagramService,
    )
    from agents.diagramador.app.tools.shared.diagram_generator.utilities import (
        confirmation_handler,
    )
    from agents.diagramador.app.tools.shared.diagram_generator.utilities.cloud_storage import (
        upload_xml_to_gcs,
    )
except ImportError:  # pragma: no cover - fallback when package context is missing
    import sys

    repo_root = Path(__file__).resolve().parents[6]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from agents.diagramador.app.settings import get_output_root
    from agents.diagramador.app.tools.shared.diagram_generator.diagram_service import (
        DiagramService,
    )

    try:  # pragma: no cover - cloud upload é opcional
        from agents.diagramador.app.tools.shared.diagram_generator.utilities.cloud_storage import (
            upload_xml_to_gcs,
        )
    except Exception:  # noqa: BLE001
        upload_xml_to_gcs = None

    from agents.diagramador.app.tools.shared.diagram_generator.utilities import (
        confirmation_handler,
    )


if "upload_xml_to_gcs" not in globals():  # pragma: no cover - cobertura defensiva
    upload_xml_to_gcs = None


def _slugify(value: str) -> str:
    normalized = "".join(ch for ch in value if ch.isalnum()).lower()
    if not normalized:
        normalized = "diagram"
    return normalized[:60]


def _normalize_lookup_key(value: str) -> str:
    """Simplifica ``value`` para uso em tabelas de busca insensíveis a acentos."""

    if not value:
        return ""

    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.strip().lower()


def _looks_like_xml(value: str) -> bool:
    """Return ``True`` when ``value`` appears to be an XML document."""

    return isinstance(value, str) and value.lstrip().startswith("<")


def _decode_data_url(data_url: str) -> str:
    """Decodifica *data URL* para texto XML quando possível."""

    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        return ""

    header, _, encoded = data_url.partition(",")
    if not _:
        return ""

    try:
        if ";base64" in header:
            binary = base64.b64decode(encoded)
        else:
            from urllib.parse import unquote_to_bytes

            binary = unquote_to_bytes(encoded)
    except Exception:  # pragma: no cover - falha na decodificação
        return ""

    if "application/zip" in header:
        buffer = BytesIO(binary)
        try:
            with zipfile.ZipFile(buffer) as zip_file:
                for name in zip_file.namelist():
                    if name.lower().endswith(".xml"):
                        return zip_file.read(name).decode("utf-8", "ignore")
        except Exception:  # pragma: no cover - queda segura
            return ""

    charset = "utf-8"
    for part in header.split(";"):
        if part.startswith("charset="):
            charset = part.split("=", 1)[1] or charset

    try:
        return binary.decode(charset, "ignore")
    except Exception:  # pragma: no cover - queda segura
        return binary.decode("utf-8", "ignore")


def _normalize_xml_payload(payload: Any) -> str:
    """Converte estruturas heterogêneas de XML em texto puro."""

    if payload is None:
        return ""

    if isinstance(payload, (bytes, bytearray)):
        try:
            return payload.decode("utf-8")
        except Exception:  # pragma: no cover - fallback defensivo
            return bytes(payload).decode("utf-8", "ignore")

    if isinstance(payload, str):
        if payload.startswith("data:"):
            return _decode_data_url(payload)
        return payload

    if isinstance(payload, dict):
        for key in (
            "xml_content",
            "content",
            "xml",
            "value",
            "body",
            "text",
        ):
            if key in payload:
                normalized = _normalize_xml_payload(payload[key])
                if normalized.strip().startswith("<"):
                    return normalized

        diagram_section = payload.get("diagram") if isinstance(payload.get("diagram"), dict) else None
        if diagram_section:
            return _normalize_xml_payload(diagram_section.get("last_result"))

        for value in payload.values():
            normalized = _normalize_xml_payload(value)
            if normalized.strip().startswith("<"):
                return normalized

        path_value = payload.get("local_path") or payload.get("local_file_path")
        if isinstance(path_value, str):
            try:
                candidate = Path(path_value).read_text(encoding="utf-8")
            except Exception:
                candidate = ""
            if _looks_like_xml(candidate):
                return candidate

        return ""

    if isinstance(payload, (list, tuple, set)):
        for item in payload:
            normalized = _normalize_xml_payload(item)
            if normalized:
                return normalized
        return ""

    return str(payload)


def _build_artifact_metadata(
    filename: str,
    xml_content: Any,
    template_name: str,
    local_file_path: Optional[str],
    expiration_hours: int = 24,
) -> tuple[Dict[str, Any], str]:
    """Normaliza o XML, garante que o arquivo local seja persistido e gera metadados.

    Returns
    -------
    tuple
        Um par ``(artifact, xml_text)`` onde ``artifact`` contém os metadados utilizados
        pelo front-end e ``xml_text`` é a representação final do documento ArchiMate.
    """

    xml_text = _normalize_xml_payload(xml_content)
    if not isinstance(xml_text, str):
        xml_text = str(xml_text)

    # Determinar caminho local preferencial (o serviço legado costuma fornecer um).
    if local_file_path:
        local_path = Path(local_file_path).resolve()
    else:
        fallback_dir = get_output_root() / template_name
        fallback_dir.mkdir(parents=True, exist_ok=True)
        local_path = (fallback_dir / filename).resolve()

    local_path.parent.mkdir(parents=True, exist_ok=True)

    # Caso o serviço tenha retornado um placeholder (ex.: "id"), reaproveitar o arquivo
    # que ele mesmo persistiu. Isso garante compatibilidade com o comportamento anterior.
    if not _looks_like_xml(xml_text):
        try:
            candidate = local_path.read_text(encoding="utf-8")
        except Exception:
            candidate = ""
        if _looks_like_xml(candidate):
            xml_text = candidate

    # Garantir que o XML final esteja salvo para download ou inspeção posterior.
    try:
        if _looks_like_xml(xml_text):
            local_path.write_text(xml_text, encoding="utf-8")
        else:
            local_path.write_text("", encoding="utf-8")
    except Exception:  # pragma: no cover - persistência local é best-effort
        pass

    bucket_name = os.getenv("DIAGRAMADOR_GCS_BUCKET", "diagram_signed_temp")
    project_id = os.getenv("DIAGRAMADOR_GCS_PROJECT", "gft-bu-gcp")
    timestamp = datetime.utcnow()

    artifact = {
        "bucket": bucket_name,
        "filename": filename,
        "gcs_blob_name": "",
        "signed_url": "",
        "expires_at": (timestamp + timedelta(hours=expiration_hours)).isoformat() + "Z",
        "local_path": str(local_path) if local_path else "",
        "output_dir": str(local_path.parent) if local_path else "",
        "template_name": template_name,
        "project": project_id,
    }

    if upload_xml_to_gcs is not None and _looks_like_xml(xml_text):
        try:
            uploaded_blob, uploaded_url = upload_xml_to_gcs(
                xml_text,
                filename,
                bucket_name=bucket_name,
                project=project_id,
                expiration_hours=expiration_hours,
            )
        except Exception as exc:  # pragma: no cover - upload opcional
            logger.warning("Falha ao enviar XML para GCS: %s", exc)
        else:
            if uploaded_blob:
                artifact["gcs_blob_name"] = (
                    uploaded_blob
                    if str(uploaded_blob).startswith("gs://")
                    else f"gs://{bucket_name}/{uploaded_blob}"
                )
            if uploaded_url:
                artifact["signed_url"] = uploaded_url

    if not artifact["signed_url"] and local_path:
        try:
            artifact["signed_url"] = Path(local_path).resolve().as_uri()
        except Exception:  # pragma: no cover - fallback defensivo
            artifact["signed_url"] = str(local_path)

    if not artifact["gcs_blob_name"]:
        if artifact["signed_url"].startswith("gs://"):
            artifact["gcs_blob_name"] = artifact["signed_url"]
        elif local_path:
            artifact["gcs_blob_name"] = (
                "local://" + Path(local_path).resolve().as_posix()
            )

    return artifact, xml_text


class Tool:
    """Adaptador que utiliza o serviço legado para gerar o XML ArchiMate."""

    _LAYER_ALIAS_BY_PREFIX = {
        "layer1": "channels",
        "layer2": "gateway_inbound",
        "layer3": "execution_logic",
        "layer4": "data_management",
        "layer5": "gateway_outbound",
        "layer6": "external_integration",
    }
    _DEFAULT_DIAGRAM_ORDER: Tuple[str, ...] = ("container", "context", "component")
    _DIAGRAM_LABELS: Dict[str, str] = {
        "container": "Container C4",
        "context": "Contexto C4",
        "component": "Component C4",
    }
    _DIAGRAM_KEYWORDS: Dict[str, Tuple[str, ...]] = {
        "container": ("container", "contêiner", "conteiner"),
        "context": ("context", "contexto"),
        "component": ("component", "componente"),
    }

    def __init__(self, metadata: Optional[Dict[str, Any]] = None):
        self.metadata = metadata or {}
        self.service = DiagramService()
        get_allowed_elements = getattr(self.service, "_get_allowed_element_types", None)
        self._allowed_element_types = (
            set(get_allowed_elements()) if callable(get_allowed_elements) else set()
        )

    @staticmethod
    def _coerce_to_text(value: Any) -> str:
        """Pequeno proxy para o utilitário de normalização do serviço legado."""
        try:
            return DiagramService._coerce_to_text(value)
        except Exception:  # pragma: no cover - fallback defensivo
            return "" if value is None else str(value)

    def _register_lookup_key(self, lookup: Dict[str, str], key: Optional[str], identifier: str) -> None:
        text = self._coerce_to_text(key)
        if not text:
            return
        normalized = _normalize_lookup_key(text)
        if normalized:
            lookup.setdefault(normalized, identifier)
            lookup.setdefault(normalized.replace(" ", ""), identifier)

    def _build_element_lookup(self, elements: List[Dict[str, Any]]) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
        """Retorna mapa ``valor -> id`` e garante que cada elemento possua um identificador."""

        lookup: Dict[str, str] = {}
        used_ids: Dict[str, int] = {}

        for element in elements:
            name = self._coerce_to_text(element.get("name"))
            identifier = self._coerce_to_text(element.get("id") or element.get("identifier"))

            if not identifier:
                base = _slugify(name or "element")
                suffix = used_ids.get(base, 0)
                identifier = base if suffix == 0 else f"{base}{suffix + 1}"
                used_ids[base] = suffix + 1
                element["id"] = identifier
            else:
                used_ids.setdefault(identifier, 0)

            self._register_lookup_key(lookup, identifier, identifier)
            if name:
                self._register_lookup_key(lookup, name, identifier)
                self._register_lookup_key(lookup, _slugify(name), identifier)

        return lookup, elements

    def _resolve_element_reference(self, reference: Any, lookup: Optional[Dict[str, str]]) -> Optional[str]:
        text = self._coerce_to_text(reference)
        if not text:
            return None
        if not lookup:
            return text

        normalized = _normalize_lookup_key(text)
        if normalized in lookup:
            return lookup[normalized]
        compact = normalized.replace(" ", "")
        if compact in lookup:
            return lookup[compact]
        slug = _slugify(text)
        slug_key = _normalize_lookup_key(slug)
        if slug_key in lookup:
            return lookup[slug_key]
        return lookup.get(slug) or None

    def _split_participants(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            result: List[str] = []
            for item in value:
                result.extend(self._split_participants(item))
            return result

        text = self._coerce_to_text(value)
        if not text:
            return []

        for separator in ("/", "\\", ",", ";"):
            text = text.replace(separator, "|")

        parts = [part.strip() for part in text.split("|") if part.strip()]
        return parts or [text.strip()]

    @staticmethod
    def _lookup_state_value(state: Dict[str, Any], reference: Any) -> Any:
        """Resolve ponteiros ``$state`` aceitando diferentes formatos de referência."""

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

    def _resolve_state_reference(
        self, payload: Any, state: Optional[Dict[str, Any]]
    ) -> tuple[bool, Any]:
        """Retorna ``(True, valor)`` quando ``payload`` referencia o estado global."""

        if not isinstance(payload, dict):
            return False, payload

        working_state = state or {}

        if "$state" in payload:
            reference = payload.get("$state")
            resolved = self._lookup_state_value(working_state, reference)
            if resolved is not None:
                return True, resolved
            if isinstance(reference, dict):
                for key in ("path", "value", "segments"):
                    if key in reference:
                        resolved = self._lookup_state_value(working_state, reference[key])
                        return True, resolved
            return True, None

        if "$input" in payload:
            reference = payload.get("$input")
            resolved = self._lookup_input_value(working_state, reference)
            return True, resolved

        return False, payload

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

    def _search_state_for_key(
        self,
        state: Optional[Dict[str, Any]],
        key: str,
        validator,
    ) -> Any:
        if not isinstance(state, dict):
            return None

        stack: List[Any] = [state]
        seen: set[int] = set()

        while stack:
            current = stack.pop()
            object_id = id(current)
            if object_id in seen:
                continue
            seen.add(object_id)

            if isinstance(current, dict):
                if key in current:
                    candidate = current[key]
                    if validator(candidate):
                        return candidate
                stack.extend(current.values())
            elif isinstance(current, (list, tuple, set)):
                stack.extend(current)

        return None

    def _looks_like_elements_structure(self, value: Any) -> bool:
        try:
            for _element, _layer in self._iter_element_payloads(value):
                return True
        except Exception:  # pragma: no cover - fallback defensivo
            return False
        return False

    def _looks_like_relationships_structure(self, value: Any) -> bool:
        stack: List[Any] = [value]
        seen: set[int] = set()

        while stack:
            current = stack.pop()
            object_id = id(current)
            if object_id in seen:
                continue
            seen.add(object_id)

            if isinstance(current, dict):
                if {"source", "target", "source_id", "target_id"}.intersection(current.keys()):
                    return True
                stack.extend(current.values())
            elif isinstance(current, (list, tuple, set)):
                stack.extend(current)

        return False

    def _looks_like_steps_structure(self, value: Any) -> bool:
        stack: List[Any] = [value]
        seen: set[int] = set()

        while stack:
            current = stack.pop()
            object_id = id(current)
            if object_id in seen:
                continue
            seen.add(object_id)

            if isinstance(current, dict):
                if any(
                    key in current for key in ("description", "text", "step", "steps", "etapas")
                ):
                    textual = current.get("description") or current.get("text") or current.get("step")
                    if isinstance(textual, str) and textual.strip():
                        return True
                    nested = current.get("steps") or current.get("etapas")
                    if nested is not None:
                        stack.append(nested)
                stack.extend(current.values())
            elif isinstance(current, (list, tuple, set)):
                for item in current:
                    if isinstance(item, str) and item.strip():
                        return True
                stack.extend(current)
            elif isinstance(current, str) and current.strip():
                return True

        return False

    def _looks_like_system_name(self, value: Any) -> bool:
        text = self._normalize_system_name(value)
        return bool(text and text.strip())

    @staticmethod
    def _extract_xml_string(payload: Any) -> str:
        """Extrai conteúdo XML de estruturas heterogêneas retornadas pelo serviço legado."""

        return _normalize_xml_payload(payload)

    @staticmethod
    def _default_type_for_layer(layer: str) -> str:
        bucket = (layer or "").lower()
        if "channel" in bucket:
            return "ApplicationCollaboration"
        if "data" in bucket or "storage" in bucket:
            return "DataObject"
        if "infra" in bucket or "kubernetes" in bucket:
            return "TechnologyService"
        if "external" in bucket:
            return "ApplicationComponent"
        return "ApplicationComponent"

    def _canonicalize_element_type(self, raw_type: str, layer_hint: str) -> str:
        value = (raw_type or "").strip()
        if not value:
            return self._default_type_for_layer(layer_hint)

        normalized = value.lower().replace("-", " ")
        aliases = {
            "application interface": "ApplicationCollaboration",
            "interface": "ApplicationCollaboration",
            "channel": "ApplicationCollaboration",
            "frontend": "ApplicationCollaboration",
            "ui": "ApplicationCollaboration",
            "microservice": "ApplicationComponent",
            "service": "ApplicationService",
            "application service": "ApplicationService",
            "application component": "ApplicationComponent",
            "component": "ApplicationComponent",
            "database": "DataObject",
            "datastore": "DataObject",
            "db": "DataObject",
            "cache": "DataObject",
            "artifact": "Artifact",
            "file": "Artifact",
            "log": "Artifact",
            "node": "Node",
            "cluster": "Node",
            "communication network": "CommunicationNetwork",
            "network": "CommunicationNetwork",
            "queue": "TechnologyService",
            "messaging": "TechnologyService",
            "postgresql": "DataObject",
            "transactional database (postgresql)": "DataObject",
            "redis": "DataObject",
            "cache (redis)": "DataObject",
            "kafka": "TechnologyService",
            "apache kafka": "TechnologyService",
            "elk": "TechnologyService",
            "elk stack": "TechnologyService",
            "prometheus": "TechnologyService",
            "hardware security module": "TechnologyService",
            "hsm": "TechnologyService",
            "gateway": "ApplicationComponent",
            "api gateway": "ApplicationComponent",
        }

        canonical = aliases.get(normalized)
        if canonical:
            return canonical

        stripped = value.replace(" ", "").lower()
        if stripped in aliases:
            return aliases[stripped]

        canonical = aliases.get(stripped)
        if canonical:
            return canonical

        return value

    def _normalize_layer_label(self, raw_layer: Optional[str]) -> Optional[str]:
        text = self._coerce_to_text(raw_layer)
        if not text:
            return None

        lowered = text.lower()
        compact = lowered.replace(" ", "").replace(":", "").replace("_", "")
        for prefix, alias in self._LAYER_ALIAS_BY_PREFIX.items():
            if compact.startswith(prefix):
                return alias

        if "channel" in lowered:
            return "channels"
        if "inbound" in lowered and "gateway" in lowered:
            return "gateway_inbound"
        if "outbound" in lowered and "gateway" in lowered:
            return "gateway_outbound"
        if "external" in lowered or "integra" in lowered:
            return "external_integration"
        if "data" in lowered or "storage" in lowered:
            return "data_management"
        return text

    def _iter_element_payloads(self, payload: Any, layer_hint: Optional[str] = None):
        """Gera pares (dict, layer_hint) a partir de estruturas aninhadas."""

        stack: List[tuple[Any, Optional[str]]] = [(payload, layer_hint)]
        element_keys = {
            "name",
            "title",
            "type",
            "category",
            "description",
            "documentation",
            "doc",
            "id",
            "identifier",
        }

        while stack:
            current, current_layer = stack.pop()
            if current is None:
                continue

            if isinstance(current, dict):
                if "layers" in current and isinstance(current["layers"], dict):
                    for layer_label, items in current["layers"].items():
                        stack.append((items, self._coerce_to_text(layer_label)))
                    remaining = {k: v for k, v in current.items() if k != "layers"}
                    if remaining:
                        stack.append((remaining, current_layer))
                    continue

                if element_keys.intersection(current.keys()):
                    yield current, current.get("layer") or current_layer
                    continue

                for key, value in current.items():
                    if key.lower() in {"layer", "layer_name"} and isinstance(value, str):
                        current_layer = self._coerce_to_text(value)
                        continue
                    stack.append((value, current_layer or self._coerce_to_text(key)))
                continue

            if isinstance(current, (list, tuple, set)):
                for item in current:
                    stack.append((item, current_layer))
                continue

            # Ignora valores escalar sem estrutura

    def _normalize_elements(self, raw_elements: Any) -> List[Dict[str, Any]]:
        """Converte payload heterogêneo de elementos em uma lista plana e anotada com layer."""

        if raw_elements is None:
            return []

        normalized: List[Dict[str, Any]] = []

        for item, layer_hint in self._iter_element_payloads(raw_elements):
            if not isinstance(item, dict):
                logger.debug("Ignorando elemento não estruturado: %r", item)
                continue
            element = self._prepare_element_dict(item, layer_hint)
            if element:
                normalized.append(element)

        if not normalized:
            logger.debug("Estrutura de elementos não suportada: %r", raw_elements)

        return normalized

    def _prepare_element_dict(self, item: Dict[str, Any], layer_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
        element = dict(item)
        layer_text = self._normalize_layer_label(element.get("layer") or layer_hint)
        name = self._coerce_to_text(element.get("name") or element.get("title"))
        documentation = self._coerce_to_text(
            element.get("documentation")
            or element.get("doc")
            or element.get("description")
        )
        raw_type = self._coerce_to_text(
            element.get("type")
            or element.get("category")
            or element.get("ttype")
            or element.get("element_type")
            or element.get("archimate_type")
        )

        etype = self._canonicalize_element_type(
            raw_type,
            layer_text or "",
        )

        if not name:
            logger.debug("Elemento ignorado por falta de nome: %r", item)
            return None

        if not etype:
            etype = self._default_type_for_layer(layer_text or "")

        element.clear()
        element_id = self._coerce_to_text(item.get("id") or item.get("identifier"))
        if element_id:
            element["id"] = element_id
        if self._allowed_element_types and etype not in self._allowed_element_types:
            etype = self._default_type_for_layer(layer_text or "")

        element["name"] = name
        element["type"] = etype
        if layer_text:
            element["layer"] = layer_text
        if documentation:
            element["documentation"] = documentation
        return element

    def _normalize_relationships(
        self, raw_relationships: Any, element_lookup: Optional[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Garante que relacionamentos sejam entregues como lista de dicionários."""

        if not raw_relationships:
            return []

        normalized: List[Dict[str, Any]] = []

        stack: List[Any] = [raw_relationships]
        while stack:
            current = stack.pop()
            if current is None:
                continue

            if isinstance(current, dict):
                if {"source", "target", "source_id", "target_id"}.intersection(current.keys()):
                    base_rel = dict(current)
                    name = self._coerce_to_text(
                        base_rel.get("name")
                        or base_rel.get("label")
                        or base_rel.get("description")
                    )
                    base_rel["name"] = name
                    if not base_rel.get("type"):
                        base_rel["type"] = self._guess_relationship_type(base_rel)

                    sources = self._split_participants(
                        base_rel.get("source_id") or base_rel.get("source")
                    )
                    targets = self._split_participants(
                        base_rel.get("target_id") or base_rel.get("target")
                    )
                    if not sources:
                        sources = [self._coerce_to_text(base_rel.get("source_id"))]
                    if not targets:
                        targets = [self._coerce_to_text(base_rel.get("target_id"))]

                    filtered_sources = [src for src in sources if src]
                    filtered_targets = [tgt for tgt in targets if tgt]
                    if not filtered_sources or not filtered_targets:
                        continue

                    for src in filtered_sources:
                        for tgt in filtered_targets:
                            rel_copy = dict(base_rel)
                            rel_copy["source"] = src
                            rel_copy["target"] = tgt
                            resolved_src = self._resolve_element_reference(src, element_lookup)
                            resolved_tgt = self._resolve_element_reference(tgt, element_lookup)
                            if resolved_src:
                                rel_copy["source_id"] = resolved_src
                            if resolved_tgt:
                                rel_copy["target_id"] = resolved_tgt
                            normalized.append(rel_copy)
                    continue

                if "relations" in current and isinstance(current["relations"], (list, tuple, set)):
                    stack.append(current["relations"])
                    continue

                stack.extend(current.values())
                continue

            if isinstance(current, (list, tuple, set)):
                stack.extend(current)
                continue

            logger.debug("Ignorando relacionamento não estruturado: %r", current)

        return normalized

    def _guess_relationship_type(self, rel: Dict[str, Any]) -> str:
        text_parts: List[str] = []
        for key in ("type", "label", "name", "description"):
            value = rel.get(key)
            if value:
                text_parts.append(self._coerce_to_text(value))
        text = " ".join(text_parts).lower()

        flow_keywords = {
            "evento",
            "event",
            "publica",
            "publicar",
            "envia",
            "enviar",
            "notifica",
            "notificação",
            "mensagem",
            "stream",
            "assíncron",
            "fila",
            "kafka",
            "pub",
            "push",
        }
        access_keywords = {
            "consulta",
            "consultar",
            "verifica",
            "verificar",
            "acessa",
            "acessar",
            "lê",
            "leitura",
            "persist",
            "salva",
            "grava",
            "armazen",
        }
        trigger_keywords = {
            "aciona",
            "acionar",
            "chama",
            "invoca",
            "solicita",
            "delega",
            "trigger",
            "executa",
        }

        if any(keyword in text for keyword in flow_keywords):
            return "Flow"
        if any(keyword in text for keyword in access_keywords):
            return "Access"
        if any(keyword in text for keyword in trigger_keywords):
            return "Triggering"
        return "Serving"

    def _normalize_steps(self, raw_steps: Any) -> List[str]:
        if not raw_steps:
            return []

        def iterate_steps(payload: Any) -> Iterable[Any]:
            stack: List[Any] = [payload]
            while stack:
                current = stack.pop()
                if current is None:
                    continue
                if isinstance(current, dict):
                    for key, value in current.items():
                        if key.lower() in {"steps", "etapas"}:
                            stack.append(value)
                        else:
                            stack.append(value)
                    continue
                if isinstance(current, (list, tuple, set)):
                    stack.extend(reversed(list(current)))
                    continue
                yield current

        normalized: List[str] = []
        for entry in iterate_steps(raw_steps):
            if isinstance(entry, dict):
                description = self._coerce_to_text(
                    entry.get("description")
                    or entry.get("text")
                    or entry.get("step")
                    or entry.get("name")
                )
                if not description:
                    continue
                if description.strip().isdigit():
                    continue
                normalized.append(description)
                continue
            text = self._coerce_to_text(entry)
            if text and not text.strip().isdigit():
                normalized.append(text)
        return normalized

    def _normalize_system_name(self, raw_system: Any) -> str:
        if isinstance(raw_system, dict):
            for key in ("name", "title", "value", "label", "system_name"):
                if raw_system.get(key):
                    return self._coerce_to_text(raw_system[key])
            return self._coerce_to_text(next(iter(raw_system.values()), ""))
        return self._coerce_to_text(raw_system)

    def _suggest_system_name(
        self,
        elements: Optional[List[Dict[str, Any]]],
        state: Optional[Dict[str, Any]],
    ) -> str:
        """Sugere um nome de sistema quando nenhum foi informado pelo usuário."""

        state = state or {}

        # 1) Tenta recuperar sugestões previamente calculadas durante a fase de análise.
        for reference in (
            "analysis.system_name_suggestion",
            "analysis.system_name_hint",
            "analysis.solution.name",
            "analysis.summary.system",
        ):
            value = self._lookup_state_value(state, reference)
            text = self._coerce_to_text(value)
            if text:
                return text

        # 2) Usa o primeiro elemento com papel de contêiner como inspiração.
        if elements:
            fallback_name: Optional[str] = None
            prioritized_types = {
                "applicationcomponent",
                "applicationsystem",
                "softwaresystem",
            }

            for element in elements:
                name = self._coerce_to_text(element.get("name"))
                if not name:
                    continue
                element_type = self._coerce_to_text(element.get("type")).lower()
                if element_type in prioritized_types or any(
                    keyword in element_type for keyword in ("system", "container")
                ):
                    return name
                if fallback_name is None and name:
                    fallback_name = name

            if fallback_name:
                return fallback_name

        # 3) Último recurso: título genérico.
        return "Solução Arquitetural"

    # ------------------------------------------------------------------ #
    # Diagram type resolution helpers
    # ------------------------------------------------------------------ #
    def _diagram_label(self, diagram_type: str) -> str:
        key = self._coerce_to_text(diagram_type).lower()
        return self._DIAGRAM_LABELS.get(key, diagram_type.title() or "Container C4")

    def _normalize_diagram_types_input(self, value: Any) -> List[str]:
        if value in (None, "", []):
            return []
        if isinstance(value, (list, tuple, set)):
            collected: List[str] = []
            for item in value:
                collected.extend(self._normalize_diagram_types_input(item))
            return self._deduplicate_preserve_order(collected)
        if isinstance(value, str):
            tokens = re.split(r"[,\s;/]+", value.strip().lower())
        else:
            tokens = [self._coerce_to_text(value).lower()]

        mapped: List[str] = []
        alias_map = {
            "contexto": "context",
            "context": "context",
            "container": "container",
            "conteiner": "container",
            "contêiner": "container",
            "component": "component",
            "componente": "component",
            "componentes": "component",
            "c1": "context",
            "c2": "container",
            "c3": "component",
        }
        all_tokens = {"todos", "todo", "todas", "tudo", "all"}
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            if token in all_tokens:
                mapped.extend(self._DEFAULT_DIAGRAM_ORDER)
                continue
            mapped_value = alias_map.get(token)
            if mapped_value:
                mapped.append(mapped_value)
        return self._deduplicate_preserve_order(mapped)

    @staticmethod
    def _deduplicate_preserve_order(values: Iterable[str]) -> List[str]:
        seen: set[str] = set()
        ordered: List[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                ordered.append(value)
        return ordered

    def _infer_diagram_types_from_text(self, text: Any) -> List[str]:
        normalized = self._coerce_to_text(text).lower()
        if not normalized:
            return []

        requested: List[str] = []
        for diagram_type, keywords in self._DIAGRAM_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                requested.append(diagram_type)
        return self._deduplicate_preserve_order(requested)

    def _extract_user_story_text(self, state: Dict[str, Any]) -> str:
        for reference in (
            "analysis.user_story",
            "analysis.last_presented.user_story",
            "analysis.original_user_story",
            "inputs.user_story",
            "input.user_story",
        ):
            value = self._lookup_state_value(state, reference)
            text = self._coerce_to_text(value)
            if text:
                return text
        return ""

    def _resolve_diagram_types(
        self,
        state: Dict[str, Any],
        explicit_request: Optional[Any] = None,
    ) -> List[str]:
        diagram_types: List[str] = self._normalize_diagram_types_input(explicit_request)

        if not diagram_types and isinstance(state, dict):
            references = [
                "analysis.diagram_types",
                "analysis.diagram_type",
                "analysis.diagram_preferences.detected_types",
                "analysis.diagram_preferences.diagram_types",
                "analysis.confirmed.diagram_types",
                "analysis.confirmed.diagram_type",
                "analysis.last_presented.diagram_types",
                "analysis.last_presented.diagram_type",
                "analysis.last_analysis.diagram_types",
                "analysis.last_analysis.diagram_type",
                "inputs.diagram_types",
                "inputs.diagram_type",
                "input.diagram_types",
                "input.diagram_type",
            ]
            for reference in references:
                candidate = self._lookup_state_value(state, reference)
                diagram_types = self._normalize_diagram_types_input(candidate)
                if diagram_types:
                    break

        if not diagram_types:
            story_text = self._extract_user_story_text(state)
            diagram_types = self._infer_diagram_types_from_text(story_text)

        if not diagram_types:
            return ["container"]

        ordered: List[str] = []
        for candidate in self._DEFAULT_DIAGRAM_ORDER:
            if candidate in diagram_types:
                ordered.append(candidate)
        for candidate in diagram_types:
            if candidate not in ordered:
                ordered.append(candidate)
        return ordered or ["container"]

    def _resolve_filename(
        self,
        filename: Optional[str],
        system_name: str,
        diagram_type: str,
        used_filenames: set[str],
    ) -> str:
        candidate = filename or f"{_slugify(system_name)}_{diagram_type}.xml"
        root, ext = os.path.splitext(candidate)
        if not ext:
            ext = ".xml"
        candidate = f"{root}{ext}"
        suffix = 1
        resolved = candidate
        while resolved in used_filenames:
            resolved = f"{root}_{suffix}{ext}"
            suffix += 1
        used_filenames.add(resolved)
        return resolved

    def _generate_diagram_variant(
        self,
        *,
        diagram_type: str,
        normalized_elements: List[Dict[str, Any]],
        normalized_relationships: List[Dict[str, Any]],
        normalized_steps: List[str],
        normalized_system_name: str,
        used_filenames: set[str],
    ) -> Dict[str, Any]:
        raw_result = self.service.process_mapped_elements(
            normalized_elements,
            normalized_relationships,
            diagram_type=diagram_type,
            system_name=normalized_system_name,
            steps_labels=normalized_steps,
        )

        if not isinstance(raw_result, dict):
            raise RuntimeToolError(str(raw_result) or "Falha desconhecida ao gerar o diagrama.")

        if not raw_result.get("success"):
            raise RuntimeToolError(raw_result.get("error", "Falha desconhecida ao gerar o diagrama."))

        xml_content = _normalize_xml_payload(raw_result.get("xml_content"))
        local_path = raw_result.get("local_file_path")
        if local_path and not _looks_like_xml(xml_content):
            try:
                xml_content = Path(local_path).read_text(encoding="utf-8")
            except Exception:
                logger.warning("Não foi possível ler o XML salvo em %s", local_path)

        if not _looks_like_xml(xml_content):
            xml_content = _normalize_xml_payload(raw_result)

        if local_path and not _looks_like_xml(xml_content):
            try:
                xml_content = Path(local_path).read_text(encoding="utf-8")
            except Exception:
                pass

        if not _looks_like_xml(xml_content):
            raise RuntimeToolError("A ferramenta legada não retornou o XML do diagrama.")

        filename = self._resolve_filename(
            raw_result.get("filename"),
            normalized_system_name,
            diagram_type,
            used_filenames,
        )
        template_name = raw_result.get("template_name") or getattr(self.service, "template_name", "default")
        artifact, persisted_xml = _build_artifact_metadata(
            filename,
            xml_content,
            template_name,
            local_path,
        )
        xml_content = persisted_xml

        metadata = raw_result.get("metadata") or {}
        quality_report = raw_result.get("quality_report") or {}
        if quality_report and "score" not in quality_report:
            quality_report["score"] = quality_report.get("overall_score")
        if quality_report and "quality_level_id" not in quality_report:
            level = quality_report.get("quality_level")
            quality_report["quality_level_id"] = str(level) if level is not None else "unknown"
        compliance = raw_result.get("compliance_summary") or {}
        diagram_key = diagram_type.lower() or "container"

        counts = {
            "elements": metadata.get("total_elements", len(normalized_elements)),
            "relationships": metadata.get("total_relationships", len(normalized_relationships)),
            "layers": len((metadata.get("layers") or {}).keys()),
        }

        quality_score = quality_report.get("score") or quality_report.get("overall_score")
        quality_level = quality_report.get("quality_level") or quality_report.get("quality_badge")

        summary = {
            "system": normalized_system_name,
            "diagram_type": self._diagram_label(diagram_key),
            "diagram_key": diagram_key,
            "counts": counts,
            "layers": metadata.get("layers"),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "quality_score": quality_score,
            "quality_level": quality_level,
            "metamodel_compliance": compliance.get("compliance_score"),
            "template_name": template_name,
        }

        quality_snapshot = {
            "score": quality_score,
            "level": quality_level,
            "metamodel": compliance.get("compliance_score"),
            "elements": counts["elements"],
            "relationships": counts["relationships"],
            "input_elements": len(normalized_elements),
            "input_relationships": len(normalized_relationships),
        }

        result_payload: Dict[str, Any] = {
            "system": normalized_system_name,
            "diagram_type": self._diagram_label(diagram_key),
            "diagram_key": diagram_key,
            "artifact": artifact,
            "metadata": {"template_name": template_name, **metadata},
            "quality_report": quality_report,
            "quality_summary": quality_snapshot,
            "compliance_summary": compliance,
            "storage": {
                "local_path": artifact["local_path"],
                "signed_url": artifact["signed_url"],
                "gcs_blob_name": artifact["gcs_blob_name"],
            },
            "summary": summary,
            "steps_count": len(normalized_steps),
            "counts": counts,
            "layers": metadata.get("layers"),
            "signed_url": artifact["signed_url"],
            "gcs_blob_name": artifact["gcs_blob_name"],
            "filename": artifact["filename"],
            "local_path": artifact["local_path"],
            "output_dir": artifact["output_dir"],
            "xml_content": artifact["local_path"],
        }

        if normalized_steps:
            preview_steps = normalized_steps[:3]
            if len(normalized_steps) > 3:
                preview_steps.append("...")
            result_payload["steps_preview"] = preview_steps

        result_payload["raw_result"] = raw_result

        return result_payload

    def generate_diagram(
        self,
        system_name: str,
        elements: List[Dict[str, Any]],
        relationships: Optional[List[Dict[str, Any]]] = None,
        steps: Optional[List[str]] = None,
        state: Optional[Dict[str, Any]] = None,
        *,
        diagram_type: Optional[Any] = None,
        diagram_types: Optional[Any] = None,
    ) -> Dict[str, Any]:
        state = state or {}

        confirmation = (
            state.get("confirmation") if isinstance(state.get("confirmation"), dict) else {}
        )
        approved_analysis = confirmation.get("approved_analysis") if confirmation else None

        global_snapshot = confirmation_handler.get_approved_snapshot()
        if not approved_analysis:
            approved_analysis = global_snapshot.get("analysis")

        explicit_requests: List[Any] = []
        for candidate in (diagram_types, diagram_type):
            if candidate in (None, "", []):
                continue
            resolved, value = self._resolve_state_reference(candidate, state)
            explicit_requests.append(value if resolved else candidate)

        resolved, value = self._resolve_state_reference(system_name, state)
        if resolved:
            system_name = value

        if not system_name and confirmation:
            system_name = (
                confirmation.get("approved_system_name")
                or (approved_analysis or {}).get("system_name")
                or (approved_analysis or {}).get("system")
            )
        if not system_name and global_snapshot.get("system_name"):
            system_name = global_snapshot.get("system_name")

        if not system_name:
            for reference in (
                "analysis.system_name",
                "analysis.summary.system_name",
                "analysis.summary.system",
                "analysis.last_presented.system_name",
                "analysis.solution.name",
                "analysis.system_name_suggestion",
                "analysis.system_name_hint",
                "confirmation.approved_system_name",
                "confirmation.approved_analysis.system_name",
                "confirmation.approved_analysis.system",
            ):
                fallback = self._lookup_state_value(state, reference)
                if fallback:
                    system_name = fallback
                    break

        if not system_name:
            system_name = self._search_state_for_key(state, "system_name", self._looks_like_system_name)
        if not system_name:
            system_name = self._search_state_for_key(state, "system", self._looks_like_system_name)
        if not system_name:
            system_name = global_snapshot.get("system_name")

        resolved, value = self._resolve_state_reference(elements, state)
        if resolved:
            elements = value
        if not elements and confirmation:
            elements = confirmation.get("approved_elements") or (
                (approved_analysis or {}).get("elements") if approved_analysis else None
            )
        if not elements and global_snapshot.get("elements"):
            elements = global_snapshot.get("elements")
        if not elements:
            for reference in (
                "analysis.elements",
                "analysis.last_presented.elements",
                "analysis.last_analysis.elements",
                "analysis.confirmed.elements",
                "analysis.latest.elements",
                "analysis.history.last.elements",
                "confirmation.approved_elements",
                "confirmation.approved_analysis.elements",
            ):
                candidate = self._lookup_state_value(state, reference)
                if candidate:
                    elements = candidate
                    break

        if not elements:
            elements = self._search_state_for_key(state, "elements", self._looks_like_elements_structure)
        if not elements and global_snapshot.get("elements"):
            elements = global_snapshot.get("elements")

        resolved, value = self._resolve_state_reference(relationships, state)
        if resolved:
            relationships = value
        if relationships in (None, []) and confirmation:
            relationships = confirmation.get("approved_relationships")
            if relationships in (None, []):
                relationships = (approved_analysis or {}).get("relationships") if approved_analysis else None
        if relationships in (None, []) and global_snapshot.get("relationships"):
            relationships = global_snapshot.get("relationships")
        if relationships in (None, []):
            for reference in (
                "analysis.relationships",
                "analysis.last_presented.relationships",
                "analysis.last_analysis.relationships",
                "analysis.confirmed.relationships",
                "confirmation.approved_relationships",
                "confirmation.approved_analysis.relationships",
            ):
                candidate = self._lookup_state_value(state, reference)
                if candidate:
                    relationships = candidate
                    break

        if relationships in (None, []):
            relationships = self._search_state_for_key(
                state, "relationships", self._looks_like_relationships_structure
            )

        resolved, value = self._resolve_state_reference(steps, state)
        if resolved:
            steps = value
        if steps in (None, [], {}) and confirmation:
            steps = confirmation.get("approved_steps")
            if steps in (None, [], {}):
                steps = (approved_analysis or {}).get("steps") if approved_analysis else None
        if steps in (None, [], {}) and global_snapshot.get("steps"):
            steps = global_snapshot.get("steps")
        if steps in (None, [], {}):
            for reference in (
                "analysis.steps",
                "analysis.last_presented.steps",
                "analysis.last_analysis.steps",
                "analysis.confirmed.steps",
                "confirmation.approved_steps",
                "confirmation.approved_analysis.steps",
            ):
                candidate = self._lookup_state_value(state, reference)
                if candidate:
                    steps = candidate
                    break

        if steps in (None, [], {}):
            steps = self._search_state_for_key(state, "steps", self._looks_like_steps_structure)
        if steps in (None, [], {}) and global_snapshot.get("steps"):
            steps = global_snapshot.get("steps")

        if not elements:
            raise RuntimeToolError("É necessário fornecer os elementos aprovados na Fase 1.")

        normalized_elements = self._normalize_elements(elements)
        if not normalized_elements:
            raise RuntimeToolError(
                "Nenhum elemento estruturado foi encontrado para gerar o diagrama."
            )

        normalized_system_name = self._normalize_system_name(system_name)
        if not normalized_system_name:
            suggestion = self._suggest_system_name(normalized_elements, state)
            normalized_system_name = self._normalize_system_name(suggestion)

        if not normalized_system_name:
            normalized_system_name = "Solução Arquitetural"

        element_lookup, normalized_elements = self._build_element_lookup(normalized_elements)
        normalized_relationships = self._normalize_relationships(relationships, element_lookup)
        normalized_steps = self._normalize_steps(steps)

        resolved_diagram_types = self._resolve_diagram_types(
            state, explicit_requests if explicit_requests else None
        )
        used_filenames: set[str] = set()

        history: List[Dict[str, Any]] = []
        if state:
            history = list(state.get("diagram", {}).get("history", []))

        generated_results: List[Dict[str, Any]] = []
        for diagram_kind in resolved_diagram_types:
            variant_result = self._generate_diagram_variant(
                diagram_type=diagram_kind,
                normalized_elements=normalized_elements,
                normalized_relationships=normalized_relationships,
                normalized_steps=normalized_steps,
                normalized_system_name=normalized_system_name,
                used_filenames=used_filenames,
            )
            generated_results.append(variant_result)
            history.append(variant_result["summary"])

        if not generated_results:
            raise RuntimeToolError("Falha desconhecida ao gerar os diagramas solicitados.")

        primary = next(
            (result for result in generated_results if result.get("diagram_key") == "container"),
            None,
        )
        if primary is None:
            primary = generated_results[0]

        additional_results = [result for result in generated_results if result is not primary]
        diagram_types_ordered = [
            result.get("diagram_key") or "container" for result in generated_results
        ]

        confirmation: Dict[str, Any] = {
            "diagram_generated": True,
            "status": "generated",
            "should_generate": False,
            "diagram_types": diagram_types_ordered,
            "last_generation": {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "filename": primary["filename"],
                "signed_url": primary["signed_url"],
                "gcs_blob_name": primary["gcs_blob_name"],
                "diagram_types": diagram_types_ordered,
            },
        }

        if additional_results:
            confirmation["additional_diagrams"] = [
                {
                    "diagram_type": result["diagram_type"],
                    "diagram_key": result["diagram_key"],
                    "signed_url": result["signed_url"],
                    "gcs_blob_name": result["gcs_blob_name"],
                    "filename": result["filename"],
                }
                for result in additional_results
            ]

        diagram_payload: Dict[str, Any] = {
            "last_result": primary,
            "history": history,
            "results": generated_results,
            "additional_results": additional_results,
            "diagram_types": diagram_types_ordered,
            "primary_type": primary.get("diagram_key"),
            "results_by_type": {
                result.get("diagram_key"): result for result in generated_results
            },
        }

        # Referências compactas para consumo posterior.
        diagram_payload["xml_path"] = primary["local_path"]
        diagram_payload["storage"] = primary["storage"]

        # Compatibilidade: fluxos anteriores referenciam ``diagram.laast_result``.
        diagram_payload["laast_result"] = primary

        return {
            "diagram": diagram_payload,
            "confirmation": confirmation,
        }


__all__ = ["Tool"]
