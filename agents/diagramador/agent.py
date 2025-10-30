"""Ponto de entrada do agente Diagramador."""

from __future__ import annotations

import copy
import json
import logging
import base64
import html
import mimetypes
import re
import urllib.parse
import warnings
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any, Iterable, Tuple

try:  # pragma: no cover - dependência opcional
    import cairosvg  # type: ignore
except Exception:  # pragma: no cover - ambiente sem suporte
    cairosvg = None  # type: ignore[assignment]

from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool

from .prompt import ORCHESTRATOR_PROMPT
from .tools.diagramador import (
    DEFAULT_DATAMODEL_FILENAME,
    DEFAULT_DIAGRAM_FILENAME,
    DEFAULT_MODEL,
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
    describe_template as _describe_template,
    finalize_datamodel as _finalize_datamodel,
    generate_archimate_diagram as _generate_archimate_diagram,
    generate_layout_preview as _generate_layout_preview,
    list_templates as _list_templates,
    save_datamodel as _save_datamodel,
)

warnings.filterwarnings("ignore", category=UserWarning, module=".*pydantic.*")


diagramador_description = (
    "Agente orquestrador responsável por interpretar histórias de usuário, "
    "gerar datamodels no padrão ArchiMate e exportar diagramas XML validados."
)


logger = logging.getLogger(__name__)


def _coerce_session_state(session_state: Any) -> MutableMapping[str, Any] | None:
    """Normaliza o estado de sessão recebido pela ADK."""

    if session_state is None:
        return None

    if isinstance(session_state, MutableMapping):
        return session_state

    if isinstance(session_state, str):
        payload = session_state.strip()
        if not payload:
            return None
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Falha ao decodificar session_state fornecido como string.")
            return None
        if isinstance(decoded, MutableMapping):
            return decoded
        logger.warning(
            "session_state string decodificada não representa um mapeamento: %s",
            type(decoded).__name__,
        )
        return None

    logger.warning(
        "Tipo de session_state não suportado recebido (%s); será ignorado.",
        type(session_state).__name__,
    )
    return None


def _make_tool(function, *, name: str | None = None):
    tool = FunctionTool(function)
    tool_name = name or getattr(function, "__tool_name__", None)
    if getattr(tool, "name", None) in (None, ""):
        tool.name = tool_name or function.__name__
    elif tool_name:
        tool.name = tool_name
    return tool


def _empty_string_to_none(value: Any) -> Any | None:
    """Converte strings vazias em ``None`` mantendo outros valores inalterados."""

    if value is None:
        return None

    if isinstance(value, str):
        if not value.strip():
            return None
        return value

    return value


def _normalize_bool_flag(value: Any) -> bool | None:
    """Interpreta strings vindas da orquestração como sinalizadores booleanos."""

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().casefold()
        if not normalized or normalized in {"none", "null", "default"}:
            return None
        if normalized in {"true", "1", "yes", "sim"}:
            return True
        if normalized in {"false", "0", "no", "nao", "não"}:
            return False

    return None


_PLACEHOLDER_SEGMENT_RE = re.compile(r"[^A-Za-z0-9]+")


def _extract_session_mapping(callback_context: Any) -> MutableMapping[str, Any] | None:
    """Try to obtain a mutable mapping backing the session state."""

    visited: set[int] = set()
    queue: list[Any] = [callback_context]

    candidate_attrs = (
        "session_state",
        "state",
        "data",
        "_session_state",
        "_state",
        "_data",
        "invocation_context",
        "context",
    )

    while queue:
        current = queue.pop(0)
        if current is None:
            continue
        marker = id(current)
        if marker in visited:
            continue
        visited.add(marker)

        if isinstance(current, MutableMapping):
            return current

        to_dict = getattr(current, "to_dict", None)
        if callable(to_dict):
            try:
                mapping = to_dict()
            except Exception:  # pragma: no cover - contexto pode lançar
                mapping = None
            if isinstance(mapping, MutableMapping):
                return mapping

        for attr in candidate_attrs:
            try:
                candidate = getattr(current, attr)
            except AttributeError:
                continue
            if candidate is not None and id(candidate) not in visited:
                queue.append(candidate)

    return None


def _resolve_template_path_from_bucket(bucket: Mapping[str, Any]) -> str | None:
    artifacts = bucket.get("artifacts") if isinstance(bucket, Mapping) else None
    template_path: str | None = None

    if isinstance(artifacts, Mapping):
        guidance = artifacts.get(SESSION_ARTIFACT_TEMPLATE_GUIDANCE)
        if isinstance(guidance, Mapping):
            model_payload = guidance.get("model")
            if isinstance(model_payload, Mapping):
                candidate = model_payload.get("path") or model_payload.get("template")
                if isinstance(candidate, str) and candidate.strip():
                    template_path = candidate.strip()
        if not template_path:
            final_datamodel = artifacts.get(SESSION_ARTIFACT_FINAL_DATAMODEL)
            if isinstance(final_datamodel, Mapping):
                candidate = final_datamodel.get("template")
                if isinstance(candidate, str) and candidate.strip():
                    template_path = candidate.strip()

    return template_path


def _extract_datamodel_payload(bucket: Mapping[str, Any]) -> str | None:
    artifacts = bucket.get("artifacts") if isinstance(bucket, Mapping) else None
    if not isinstance(artifacts, Mapping):
        return None

    payload = artifacts.get(SESSION_ARTIFACT_FINAL_DATAMODEL)
    if not isinstance(payload, Mapping):
        return None

    for key in ("json", "source_json"):
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    for key in ("datamodel", "source"):
        candidate = payload.get(key)
        if isinstance(candidate, Mapping):
            try:
                return json.dumps(candidate)
            except TypeError:
                continue

    return None


def _ensure_layout_preview_assets(session_state: MutableMapping[str, Any]) -> bool:
    """Guarantee that layout preview assets exist before response delivery."""

    if not isinstance(session_state, MutableMapping):
        return False

    bucket = session_state.get("diagramador")
    if not isinstance(bucket, MutableMapping):
        return False

    artifacts = bucket.get("artifacts")
    if isinstance(artifacts, MutableMapping):
        layout_artifact = artifacts.get(SESSION_ARTIFACT_LAYOUT_PREVIEW)
        if isinstance(layout_artifact, Mapping):
            if _collect_layout_preview_replacements(layout_artifact):
                return False

    template_path = _resolve_template_path_from_bucket(bucket)
    if not template_path:
        return False

    datamodel_payload = _extract_datamodel_payload(bucket)
    if datamodel_payload is None:
        datamodel_payload = None

    view_focus = bucket.get("view_focus") if isinstance(bucket, Mapping) else None

    try:
        _generate_layout_preview(
            datamodel_payload,
            template_path=template_path,
            session_state=session_state,
            view_filter=view_focus,
        )
        return True
    except Exception:  # pragma: no cover - geração de prévia pode falhar silenciosamente
        logger.debug("Falha ao gerar pré-visualização automática antes da resposta", exc_info=True)
        return False


def _resolve_local_file(path_text: str | None, uri_text: str | None) -> Path | None:
    """Identify um caminho local válido a partir de um path absoluto ou URI."""

    candidates: Iterable[str] = []
    normalized: list[str] = []

    if isinstance(path_text, str) and path_text.strip():
        normalized.append(path_text.strip())

    if isinstance(uri_text, str) and uri_text.strip():
        parsed = urllib.parse.urlparse(uri_text.strip())
        if parsed.scheme == "file":
            raw_path = urllib.parse.unquote(parsed.path or "")
            if parsed.netloc:
                raw_path = f"//{parsed.netloc}{raw_path}"
            if raw_path:
                normalized.append(raw_path)

    candidates = normalized

    for candidate in candidates:
        try:
            candidate_path = Path(candidate)
        except Exception:  # pragma: no cover - caminhos inválidos
            continue
        resolved = candidate_path.expanduser().resolve(strict=False)
        if resolved.exists():
            return resolved
    return None


def _guess_mime_type(path: Path | None, fallback: str | None = None) -> str:
    if path is not None:
        mime_type, _ = mimetypes.guess_type(str(path), strict=False)
        if mime_type:
            return mime_type
        suffix = path.suffix.lower()
        if suffix == ".svg":
            return "image/svg+xml"
        if suffix == ".png":
            return "image/png"
    if fallback:
        return fallback
    return "application/octet-stream"


def _encode_data_uri(path: Path | None, *, mime_hint: str | None = None) -> Tuple[str | None, str | None]:
    if path is None:
        return None, None
    try:
        payload = path.read_bytes()
    except OSError:
        return None, None
    mime_type = _guess_mime_type(path, fallback=mime_hint)
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}", mime_type


def _convert_svg_to_png_data_uri(path: Path | None) -> Tuple[str | None, str | None]:
    """Gera um data URI PNG a partir de um arquivo SVG, se possível."""

    if path is None or cairosvg is None:
        return None, None

    try:
        svg_bytes = path.read_bytes()
    except OSError:
        return None, None

    try:  # pragma: no cover - depende de cairosvg
        png_bytes = cairosvg.svg2png(bytestring=svg_bytes)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - falha na conversão
        return None, None

    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}", "image/png"


def _build_image_html(data_uri: str | None, alt_text: str | None) -> str | None:
    if not data_uri:
        return None
    safe_alt = html.escape(alt_text or "Pré-visualização", quote=True)
    return f'<img src="{data_uri}" alt="{safe_alt}">' 


def _extract_markdown_label(markdown: str | None) -> str | None:
    if not markdown:
        return None
    match = re.match(r"\s*\[(?P<label>[^\]]+)\]\s*\(", markdown)
    if match:
        label = match.group("label").strip()
        if label:
            return label
    return None


def _build_link_html(data_uri: str | None, label: str | None) -> str | None:
    if not data_uri:
        return None
    safe_label = html.escape(label or "Abrir SVG da Previsão do Diagrama", quote=False)
    return f'<a href="{data_uri}" target="_blank" rel="noopener">{safe_label}</a>'


def _stringify_placeholder_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    return None


def _sanitize_state_segment(segment: str) -> str:
    cleaned = _PLACEHOLDER_SEGMENT_RE.sub("_", segment.strip())
    cleaned = cleaned.strip("_")
    return cleaned or segment.strip() or "valor"


def _flatten_state_for_placeholders(
    node: Any,
    prefix: str,
    mapping: dict[str, str],
    *,
    raw_segments: tuple[str, ...] = (),
) -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            raw_key = str(key)
            sanitized_key = _sanitize_state_segment(raw_key)
            if not sanitized_key:
                continue
            next_prefix = f"{prefix}.{sanitized_key}" if prefix else sanitized_key
            next_raw_segments = raw_segments + (raw_key,)
            _flatten_state_for_placeholders(
                value,
                next_prefix,
                mapping,
                raw_segments=next_raw_segments,
            )
        return
    if isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
        for index, value in enumerate(node):
            index_text = str(index)
            sanitized_index = _sanitize_state_segment(index_text)
            next_prefix = f"{prefix}.{sanitized_index}" if prefix else sanitized_index
            next_raw_segments = raw_segments + (index_text,)
            _flatten_state_for_placeholders(
                value,
                next_prefix,
                mapping,
                raw_segments=next_raw_segments,
            )
        return
    text = _stringify_placeholder_value(node)
    if text is not None and prefix:
        mapping.setdefault(prefix, text)
        underscore_key = prefix.replace(".", "_")
        underscore_key = underscore_key.replace("-", "_")
        underscore_key = re.sub(r"__+", "_", underscore_key)
        if underscore_key and underscore_key != prefix:
            mapping.setdefault(underscore_key, text)
        raw_path = ".".join(
            segment.strip()
            for segment in raw_segments
            if isinstance(segment, str) and segment.strip()
        )
        if raw_path and raw_path != prefix:
            mapping.setdefault(raw_path, text)
            raw_underscore = raw_path.replace(".", "_").replace("-", "_")
            raw_underscore = re.sub(r"__+", "_", raw_underscore)
            if raw_underscore and raw_underscore not in {prefix, raw_path}:
                mapping.setdefault(raw_underscore, text)


def _format_download_link(uri: str, label: str | None = None) -> str:
    safe_uri = uri.strip()
    if not safe_uri:
        return ""
    label_text = label.strip() if isinstance(label, str) else None
    if not label_text:
        label_text = "Abrir SVG da Previsão do Diagrama"
    return f"[{label_text}]({safe_uri})"


def _format_inline_image(uri: str, alt: str | None = None) -> str:
    safe_uri = uri.strip()
    if not safe_uri:
        return ""
    alt_text = alt.strip() if isinstance(alt, str) else None
    if not alt_text:
        alt_text = "Pré-visualização"
    return f"![{alt_text}]({safe_uri})"


def _coalesce_inline_markdown(summary: Mapping[str, Any]) -> str | None:
    inline = _stringify_placeholder_value(summary.get("inline_markdown"))
    if inline:
        return inline
    uri = _stringify_placeholder_value(summary.get("inline_uri"))
    if uri:
        alt = _stringify_placeholder_value(summary.get("view_name"))
        markup = _format_inline_image(uri, alt)
        return markup or None
    return None


def _coalesce_download_markdown(summary: Mapping[str, Any]) -> str | None:
    download = _stringify_placeholder_value(summary.get("download_markdown"))
    if download:
        return download
    uri = _stringify_placeholder_value(summary.get("download_uri"))
    if uri:
        label = _stringify_placeholder_value(summary.get("download_label"))
        markup = _format_download_link(uri, label)
        return markup or None
    return None


def _coalesce_path(summary: Mapping[str, Any]) -> str | None:
    path_value = _stringify_placeholder_value(summary.get("download_path"))
    if path_value:
        return path_value
    return _stringify_placeholder_value(summary.get("inline_path"))


def _coalesce_filename(summary: Mapping[str, Any]) -> str | None:
    filename = _stringify_placeholder_value(summary.get("download_filename"))
    if filename:
        return filename
    filename = _stringify_placeholder_value(summary.get("inline_filename"))
    if filename:
        return filename
    path_value = _coalesce_path(summary)
    if path_value:
        return Path(path_value).name
    return _stringify_placeholder_value(summary.get("view_name"))


def _register_direct_placeholder(mapping: dict[str, str], token: str, value: str) -> None:
    """Adiciona ``token`` ao mapa, incluindo variação por URL encoding."""

    if not token:
        return

    if token not in mapping:
        mapping[token] = value

    encoded = urllib.parse.quote(token, safe="")
    if encoded and encoded != token:
        mapping.setdefault(encoded, value)


def _register_state_prefix_variants(
    mapping: dict[str, str], prefix: Any, value: Any
) -> None:
    """Registra placeholders baseados apenas no prefixo da visão."""

    prefix_text = _stringify_placeholder_value(prefix)
    value_text = _stringify_placeholder_value(value)

    if not prefix_text or not value_text:
        return

    base_keys = [
        f"state.{prefix_text}",
        f"app.state.{prefix_text}",
        prefix_text,
    ]

    for base in base_keys:
        _register_direct_placeholder(mapping, f"{{{{{base}}}}}", value_text)
        _register_direct_placeholder(mapping, f"{{{{ {base} }}}}", value_text)
        _register_direct_placeholder(mapping, f"[[{base}]]", value_text)
        _register_direct_placeholder(mapping, f"[[ {base} ]]", value_text)


def _register_square_placeholder_variants(
    mapping: dict[str, str], key_text: str, value_text: str
) -> None:
    """Register double-bracket variants for a given placeholder key."""

    if not key_text:
        return

    seeds: list[str] = [key_text]
    canonical: set[str] = set()

    while seeds:
        candidate = seeds.pop()
        if not candidate or candidate in canonical:
            continue
        canonical.add(candidate)

        if candidate.startswith("app.state."):
            suffix = candidate[len("app.state.") :]
            if suffix and suffix not in canonical:
                seeds.append(suffix)
        if candidate.startswith("state."):
            suffix = candidate[len("state.") :]
            if suffix and suffix not in canonical:
                seeds.append(suffix)
        if candidate.startswith("app_state_"):
            suffix = candidate[len("app_state_") :]
            if suffix and suffix not in canonical:
                seeds.append(suffix)
        if candidate.startswith("state_"):
            suffix = candidate[len("state_") :]
            if suffix and suffix not in canonical:
                seeds.append(suffix)

        normalized = candidate.replace(".", "_")
        normalized = normalized.replace("-", "_")
        normalized = re.sub(r"__+", "_", normalized)
        if normalized and normalized not in canonical:
            seeds.append(normalized)

    variants: set[str] = set()

    for item in canonical:
        if not item:
            continue
        variants.add(item)

        core = item
        if item.startswith("state."):
            core = item[len("state.") :]
        elif item.startswith("app.state."):
            core = item[len("app.state.") :]
        elif item.startswith("state_"):
            core = item[len("state_") :]
        elif item.startswith("app_state_"):
            core = item[len("app_state_") :]

        if core and core != item:
            variants.add(core)

        if core:
            variants.add(f"state.{core}")
            variants.add(f"app.state.{core}")
            if "_" in core:
                variants.add(f"state_{core}")
                variants.add(f"app_state_{core}")

    for variant in variants:
        token = f"[[{variant}]]"
        _register_direct_placeholder(mapping, token, value_text)


def _register_placeholder(mapping: dict[str, str], placeholder: Any, value: str | None) -> None:
    placeholder_text = _stringify_placeholder_value(placeholder)
    if not placeholder_text:
        return
    if value is None:
        return
    value_text = value.strip()
    if not value_text:
        return
    _register_direct_placeholder(mapping, placeholder_text, value_text)
    if (
        placeholder_text.startswith("{")
        and placeholder_text.endswith("}")
        and not placeholder_text.startswith("{{")
    ):
        inner = placeholder_text[1:-1].strip()
        if inner:
            nested = f"{{{{{inner}}}}}"
            _register_direct_placeholder(mapping, nested, value_text)
            _register_square_placeholder_variants(mapping, inner, value_text)

    if placeholder_text.startswith("{{") and placeholder_text.endswith("}}"):  # pragma: no branch
        inner = placeholder_text[2:-2].strip()
        if inner:
            _register_square_placeholder_variants(mapping, inner, value_text)


def _collect_layout_preview_replacements(
    layout: Mapping[str, Any] | None,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not isinstance(layout, Mapping):
        return mapping

    default_svg: str | None = None
    default_png: str | None = None

    def _process(summary: Mapping[str, Any] | None) -> None:
        nonlocal default_svg, default_png
        if not isinstance(summary, Mapping):
            return

        inline_html_pref = _stringify_placeholder_value(summary.get("inline_html"))
        download_html_pref = _stringify_placeholder_value(summary.get("download_html"))
        inline_md = _coalesce_inline_markdown(summary)
        download_md = _coalesce_download_markdown(summary)
        inline_uri = _stringify_placeholder_value(summary.get("inline_uri"))
        download_uri = _stringify_placeholder_value(summary.get("download_uri"))
        inline_data_uri = _stringify_placeholder_value(summary.get("inline_data_uri"))
        download_data_uri = _stringify_placeholder_value(summary.get("download_data_uri"))
        inline_path = _stringify_placeholder_value(summary.get("inline_path"))
        download_path = _stringify_placeholder_value(summary.get("download_path"))
        filename = _coalesce_filename(summary)
        alt_text = _stringify_placeholder_value(summary.get("view_name")) or "Pré-visualização"

        inline_file = _resolve_local_file(inline_path, inline_uri)
        computed_inline_data_uri, inline_mime = _encode_data_uri(inline_file)
        if not inline_data_uri:
            inline_data_uri = computed_inline_data_uri
        if inline_data_uri and inline_mime and inline_mime.endswith("svg+xml"):
            png_data_uri, png_mime = _convert_svg_to_png_data_uri(inline_file)
            if png_data_uri:
                inline_data_uri, inline_mime = png_data_uri, png_mime

        download_file = _resolve_local_file(download_path, download_uri)
        computed_download_data_uri, download_mime = _encode_data_uri(download_file)
        if not download_data_uri:
            download_data_uri = computed_download_data_uri

        if inline_data_uri is None and inline_uri and inline_uri == download_uri:
            inline_data_uri = download_data_uri

        preferred_image_source = inline_data_uri or download_data_uri
        inline_html = None
        if preferred_image_source:
            inline_html = _build_image_html(preferred_image_source, alt_text)
        if not inline_html and inline_html_pref:
            inline_html = inline_html_pref

        link_label = _extract_markdown_label(download_md)
        if not link_label:
            if alt_text:
                link_label = f"Abrir SVG da Previsão do Diagrama - {alt_text}"
            else:
                link_label = "Abrir SVG da Previsão do Diagrama"

        preferred_link_source = download_data_uri or inline_data_uri or download_uri
        download_html = None
        if preferred_link_source:
            download_html = _build_link_html(preferred_link_source, link_label)
        if not download_html and download_html_pref:
            download_html = download_html_pref

        inline_value = inline_html or inline_md or inline_uri or inline_path
        download_value = download_html or download_md or preferred_link_source or inline_html

        placeholders = summary.get("placeholders")
        if isinstance(placeholders, Mapping):
            for key, placeholder in placeholders.items():
                normalized_key = _stringify_placeholder_value(key)
                placeholder_token = _stringify_placeholder_value(placeholder)
                if not normalized_key or not placeholder_token:
                    continue
                base_key = normalized_key.lower()
                if base_key.startswith("legacy_"):
                    base_key = base_key[len("legacy_") :]
                elif base_key.startswith("bare_"):
                    base_key = base_key[len("bare_") :]
                resolved: str | None = None
                if base_key in {"image", "img", "embed"}:
                    resolved = inline_value
                elif base_key in {"link", "markdown_link"}:
                    resolved = download_value
                elif base_key in {"path", "relative_path"}:
                    resolved = (
                        download_data_uri
                        or inline_data_uri
                        or download_path
                        or inline_path
                        or download_uri
                        or inline_uri
                    )
                elif base_key in {"uri", "url"}:
                    resolved = (
                        download_data_uri
                        or inline_data_uri
                        or download_uri
                        or inline_uri
                    )
                elif base_key == "filename":
                    resolved = filename
                if resolved:
                    _register_placeholder(mapping, placeholder_token, resolved)

        _register_placeholder(mapping, summary.get("inline_placeholder"), inline_value)
        _register_placeholder(
            mapping, summary.get("inline_placeholder_legacy"), inline_value
        )
        _register_placeholder(
            mapping,
            summary.get("download_placeholder"),
            download_value,
        )
        _register_placeholder(
            mapping,
            summary.get("download_placeholder_legacy"),
            download_value,
        )

        base_value = inline_value or download_value
        if base_value:
            _register_state_prefix_variants(
                mapping, summary.get("state_placeholder_prefix"), base_value
            )
            _register_state_prefix_variants(
                mapping, summary.get("placeholder_token"), base_value
            )

        if inline_value:
            lower_inline = inline_value.lower()
            if default_png is None and (
                "data:image/png" in lower_inline
                or (inline_mime and inline_mime.endswith("png"))
                or (inline_path and inline_path.lower().endswith(".png"))
            ):
                default_png = inline_value

        link_target = download_path or download_uri
        if (
            (download_value and "data:image" in download_value)
            or (download_mime and download_mime.endswith("svg+xml"))
            or (link_target and link_target.lower().endswith(".svg"))
        ):
            if download_md:
                default_svg = default_svg or download_value
            elif download_uri:
                default_svg = default_svg or download_value

    _process(layout)
    _process(layout.get("primary_preview"))

    summaries = layout.get("preview_summaries")
    if isinstance(summaries, Sequence):
        for summary in summaries:
            if isinstance(summary, Mapping):
                _process(summary)

    previews = layout.get("previews")
    if isinstance(previews, Sequence):
        for summary in previews:
            if isinstance(summary, Mapping):
                _process(summary)

    if default_svg:
        _register_placeholder(mapping, "{diagramador_svg_link}", default_svg)
        _register_placeholder(mapping, "{link_diagrama_svg_base64}", default_svg)
    if default_png:
        _register_placeholder(mapping, "{diagram_img_png}", default_png)

    return mapping


def _build_placeholder_replacements(
    state_data: Mapping[str, Any] | None,
) -> dict[str, str]:
    replacements: dict[str, str] = {}
    if not isinstance(state_data, Mapping):
        return replacements

    virtual_state: dict[str, Any] = dict(state_data)
    alias_candidates: list[Mapping[str, Any]] = []

    diagramador_bucket = state_data.get("diagramador")
    if isinstance(diagramador_bucket, Mapping):
        artifacts = diagramador_bucket.get("artifacts")
        if isinstance(artifacts, Mapping):
            layout_artifact = artifacts.get(SESSION_ARTIFACT_LAYOUT_PREVIEW)
            if isinstance(layout_artifact, Mapping):
                alias_candidates.append(layout_artifact)
        direct_layout = diagramador_bucket.get("layout_preview")
        if isinstance(direct_layout, Mapping):
            alias_candidates.append(direct_layout)

    primary_layout = next(iter(alias_candidates), None)
    if isinstance(primary_layout, Mapping):
        virtual_state.setdefault("layout_preview", primary_layout)

    for candidate in alias_candidates:
        replacements.update(_collect_layout_preview_replacements(candidate))

    flat_paths: dict[str, str] = {}
    _flatten_state_for_placeholders(virtual_state, "", flat_paths)
    for path, value in flat_paths.items():
        _register_direct_placeholder(replacements, f"{{{{state.{path}}}}}", value)
        _register_direct_placeholder(replacements, f"{{{{app.state.{path}}}}}", value)
        _register_direct_placeholder(replacements, f"{{{{{path}}}}}", value)
        _register_square_placeholder_variants(replacements, f"state.{path}", value)

    return replacements


def _apply_replacements_to_text(text: str, replacements: Mapping[str, str]) -> str:
    result = text
    for needle, replacement in replacements.items():
        if not needle:
            continue
        if needle not in result:
            continue
        result = result.replace(needle, replacement)
    return result


def _apply_replacements_to_mapping(
    payload: MutableMapping[str, Any], replacements: Mapping[str, str]
) -> None:
    for key, value in list(payload.items()):
        if isinstance(value, str):
            updated = _apply_replacements_to_text(value, replacements)
            if updated != value:
                payload[key] = updated
        elif isinstance(value, MutableMapping):
            _apply_replacements_to_mapping(value, replacements)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            _apply_replacements_to_sequence(value, replacements)


def _apply_replacements_to_sequence(
    payload: Sequence[Any], replacements: Mapping[str, str]
) -> None:
    for index, item in enumerate(list(payload)):
        if isinstance(item, str):
            updated = _apply_replacements_to_text(item, replacements)
            if updated != item and hasattr(payload, "__setitem__"):
                try:
                    payload[index] = updated  # type: ignore[index]
                except Exception:  # pragma: no cover - estruturas não mutáveis
                    pass
        elif isinstance(item, MutableMapping):
            _apply_replacements_to_mapping(item, replacements)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            _apply_replacements_to_sequence(item, replacements)
        else:
            _apply_replacements_to_object(item, replacements)


def _apply_replacements_to_object(obj: Any, replacements: Mapping[str, str]) -> None:
    if obj is None:
        return
    text = getattr(obj, "text", None)
    if isinstance(text, str):
        updated = _apply_replacements_to_text(text, replacements)
        if updated != text:
            obj.text = updated  # type: ignore[attr-defined]

    content = getattr(obj, "content", None)
    if isinstance(content, str):
        updated = _apply_replacements_to_text(content, replacements)
        if updated != content:
            obj.content = updated  # type: ignore[attr-defined]
    elif isinstance(content, MutableMapping):
        _apply_replacements_to_mapping(content, replacements)
    elif isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        _apply_replacements_to_sequence(content, replacements)
    elif content is not None:
        _apply_replacements_to_object(content, replacements)

    parts = getattr(obj, "parts", None)
    if isinstance(parts, Sequence):
        _apply_replacements_to_sequence(parts, replacements)


def _apply_replacements_to_llm_response(
    llm_response: Any, replacements: Mapping[str, str]
) -> None:
    if not replacements or llm_response is None:
        return

    candidates = getattr(llm_response, "candidates", None)
    if isinstance(candidates, Sequence):
        for candidate in candidates:
            _apply_replacements_to_object(candidate, replacements)

    if isinstance(llm_response, MutableMapping):
        _apply_replacements_to_mapping(llm_response, replacements)
        return

    _apply_replacements_to_object(llm_response, replacements)


def _after_model_response_callback(*, callback_context: Any, llm_response: Any):
    session_mapping = _extract_session_mapping(callback_context)

    if session_mapping is not None:
        _ensure_layout_preview_assets(session_mapping)

    try:
        state_obj = getattr(callback_context, "state")
        state_data = state_obj.to_dict()  # type: ignore[attr-defined]
    except Exception:
        if session_mapping is not None:
            try:
                state_data = copy.deepcopy(session_mapping)
            except Exception:
                state_data = dict(session_mapping)
        else:
            state_data = {}

    if session_mapping is None and isinstance(state_data, MutableMapping):
        _ensure_layout_preview_assets(state_data)

    replacements = _build_placeholder_replacements(state_data)
    if not replacements:
        return None

    logger.debug(
        "Substituindo %d placeholders após a resposta do modelo.", len(replacements)
    )
    _apply_replacements_to_llm_response(llm_response, replacements)
    return None


def list_templates(directory: str, session_state: str):
    """Wrapper to keep the public signature simple for automatic calling."""

    coerced_state = _coerce_session_state(session_state)
    normalized_directory: Any | None = _empty_string_to_none(directory)
    return _list_templates(normalized_directory, session_state=coerced_state)


def describe_template(
    template_path: str,
    view_filter: str,
    session_state: str,
):
    coerced_state = _coerce_session_state(session_state)
    filter_payload: Any | None = _empty_string_to_none(view_filter)
    return _describe_template(
        template_path,
        view_filter=filter_payload,
        session_state=coerced_state,
    )


def generate_layout_preview(
    datamodel: str,
    template_path: str,
    view_filter: str,
    session_state: str,
):
    coerced_state = _coerce_session_state(session_state)
    datamodel_payload: Any | None = datamodel
    if isinstance(datamodel, str) and not datamodel.strip():
        datamodel_payload = None

    template_payload: Any | None = _empty_string_to_none(template_path)
    filter_payload: Any | None = _empty_string_to_none(view_filter)

    try:
        return _generate_layout_preview(
            datamodel_payload,
            template_path=template_payload,
            session_state=coerced_state,
            view_filter=filter_payload,
        )
    except ValueError as exc:
        if datamodel_payload is None or coerced_state is None:
            raise
        try:
            return _generate_layout_preview(
                None,
                template_path=template_payload,
                session_state=coerced_state,
                view_filter=filter_payload,
            )
        except Exception:
            raise exc


def finalize_datamodel(
    datamodel: str,
    template_path: str,
    session_state: str,
):
    coerced_state = _coerce_session_state(session_state)
    return _finalize_datamodel(
        datamodel,
        template_path,
        session_state=coerced_state,
    )


def save_datamodel(
    datamodel: str,
    filename: str,
    session_state: str,
):
    target = _empty_string_to_none(filename) or DEFAULT_DATAMODEL_FILENAME
    payload: Any | None = datamodel
    if isinstance(datamodel, str) and not datamodel.strip():
        payload = None
    coerced_state = _coerce_session_state(session_state)
    return _save_datamodel(payload, target, session_state=coerced_state)


def generate_archimate_diagram(
    model_json_path: str,
    output_filename: str,
    template_path: str,
    validate: str,
    xsd_dir: str,
    session_state: str,
):
    target_output = _empty_string_to_none(output_filename) or DEFAULT_DIAGRAM_FILENAME
    coerced_state = _coerce_session_state(session_state)
    validate_flag = _normalize_bool_flag(validate)
    if validate_flag is None:
        validate_flag = True
    return _generate_archimate_diagram(
        _empty_string_to_none(model_json_path),
        output_filename=target_output,
        template_path=_empty_string_to_none(template_path),
        validate=validate_flag,
        xsd_dir=_empty_string_to_none(xsd_dir),
        session_state=coerced_state,
    )


diagramador_agent = Agent(
    model=DEFAULT_MODEL,
    name="diagramador",
    description=diagramador_description,
    instruction=ORCHESTRATOR_PROMPT,
    after_model_callback=_after_model_response_callback,
    tools=[
        _make_tool(list_templates, name="list_templates"),
        _make_tool(describe_template, name="describe_template"),
        _make_tool(generate_layout_preview, name="generate_layout_preview"),
        _make_tool(finalize_datamodel, name="finalize_datamodel"),
        _make_tool(save_datamodel, name="save_datamodel"),
        _make_tool(
            generate_archimate_diagram,
            name="generate_archimate_diagram",
        ),
    ],
)


def get_root_agent() -> Agent:
    """Return the Diagramador agent instance.

    Provided for compatibility with integrations that expect a callable
    accessor while also exposing ``root_agent`` as a module-level variable for
    the Google ADK loader.
    """

    return diagramador_agent


root_agent: Agent = diagramador_agent


__all__ = ["diagramador_agent", "get_root_agent", "root_agent"]
