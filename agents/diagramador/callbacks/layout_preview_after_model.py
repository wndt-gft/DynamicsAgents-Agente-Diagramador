"""Callback responsável por pós-processar respostas com pré-visualizações."""

from __future__ import annotations

import base64
import copy
import html
import json
import logging
import mimetypes
import re
import urllib.parse
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any, Iterable, Tuple

try:  # pragma: no cover - dependência opcional
    import cairosvg  # type: ignore
except Exception:  # pragma: no cover - ambiente sem suporte
    cairosvg = None  # type: ignore[assignment]

from ..tools.diagramador import (
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
    SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
    generate_layout_preview as _generate_layout_preview,
)

logger = logging.getLogger(__name__)


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
        logger.debug(
            "Falha ao gerar pré-visualização automática antes da resposta",
            exc_info=True,
        )
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
    safe_label = html.escape(label or "Abrir diagrama", quote=False)
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
        label_text = "Abrir diagrama"
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


def _register_placeholder(mapping: dict[str, str], placeholder: Any, value: str | None) -> None:
    placeholder_text = _stringify_placeholder_value(placeholder)
    if not placeholder_text or value is None:
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


def _register_state_prefix_variants(mapping: dict[str, str], placeholder: Any, value: str) -> None:
    token = _stringify_placeholder_value(placeholder)
    value_text = _stringify_placeholder_value(value)

    if not token or not value_text:
        return

    base_keys = [
        f"state.{token}",
        f"app.state.{token}",
        token,
    ]

    for base in base_keys:
        _register_direct_placeholder(mapping, f"{{{{{base}}}}}", value_text)
        _register_direct_placeholder(mapping, f"{{{{ {base} }}}}", value_text)
        _register_direct_placeholder(mapping, f"[[{base}]]", value_text)
        _register_direct_placeholder(mapping, f"[[ {base} ]]", value_text)

    if token.startswith("{{") and token.endswith("}}"):  # legacy ADK placeholder
        stripped = token.strip("{}").strip()
        if stripped:
            mapping.setdefault(stripped, value_text)
            mapping.setdefault(stripped.replace(".", "_"), value_text)


def _register_square_placeholder_variants(mapping: dict[str, str], key_text: str, value_text: str) -> None:
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


def _collect_layout_preview_placeholders(layout: Mapping[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}

    default_png: str | None = None
    default_svg: str | None = None

    def _process(summary: Mapping[str, Any]) -> None:
        nonlocal default_png, default_svg

        if not isinstance(summary, Mapping):
            return

        inline_html_pref = _stringify_placeholder_value(summary.get("inline_html"))
        inline_md = _coalesce_inline_markdown(summary)
        inline_uri = _stringify_placeholder_value(summary.get("inline_uri"))
        inline_path = _stringify_placeholder_value(summary.get("inline_path"))
        inline_filename = _stringify_placeholder_value(summary.get("inline_filename"))
        inline_data_uri = _stringify_placeholder_value(summary.get("inline_data_uri"))

        download_html_pref = _stringify_placeholder_value(summary.get("download_html"))
        download_md = _coalesce_download_markdown(summary)
        download_uri = _stringify_placeholder_value(summary.get("download_uri"))
        download_path = _stringify_placeholder_value(summary.get("download_path"))
        download_filename = _stringify_placeholder_value(summary.get("download_filename"))
        download_data_uri = _stringify_placeholder_value(summary.get("download_data_uri"))

        alt_text = _stringify_placeholder_value(summary.get("view_name"))
        filename = download_filename or inline_filename or alt_text

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

        inline_html = inline_html_pref or _build_image_html(inline_data_uri or download_data_uri, alt_text)
        link_label = _extract_markdown_label(download_md) or alt_text or "Abrir diagrama"
        download_html = download_html_pref or _build_link_html(
            download_data_uri or inline_data_uri, link_label
        )

        inline_value = inline_html or inline_md or inline_uri or inline_path
        download_value = download_html or download_md or download_uri or inline_html

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
        _register_placeholder(mapping, summary.get("inline_placeholder_legacy"), inline_value)
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
                or (inline_path and inline_path.lower().endswith(".png"))
            ):
                default_png = inline_value

        link_target = download_path or download_uri
        if (
            (download_value and "data:image" in download_value)
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
        mapping.setdefault("preview.svg", default_svg)
    if default_png:
        mapping.setdefault("preview.png", default_png)

    bucket = layout.get("state_placeholders")
    if isinstance(bucket, Mapping):
        for key, value in bucket.items():
            token = _stringify_placeholder_value(key)
            resolved = _stringify_placeholder_value(value)
            if token and resolved:
                mapping.setdefault(token, resolved)

    return mapping


def _collect_layout_preview_replacements(layout: Mapping[str, Any]) -> dict[str, str]:
    mapping = _collect_layout_preview_placeholders(layout)

    state_snapshot = layout.get("state_snapshot")
    if isinstance(state_snapshot, Mapping):
        _flatten_state_for_placeholders(state_snapshot, "state", mapping)
        _flatten_state_for_placeholders(state_snapshot, "session", mapping)

    return mapping


def _build_placeholder_replacements(state: Mapping[str, Any] | None) -> dict[str, str]:
    if not isinstance(state, Mapping):
        return {}

    replacements: dict[str, str] = {}
    virtual_state: dict[str, Any] = dict(state)
    alias_candidates: list[Mapping[str, Any]] = []

    diagramador_bucket = state.get("diagramador")
    if isinstance(diagramador_bucket, Mapping):
        artifacts = diagramador_bucket.get("artifacts")
        if isinstance(artifacts, Mapping):
            layout_artifact = artifacts.get(SESSION_ARTIFACT_LAYOUT_PREVIEW)
            if isinstance(layout_artifact, Mapping):
                alias_candidates.append(layout_artifact)
        direct_layout = diagramador_bucket.get("layout_preview")
        if isinstance(direct_layout, Mapping):
            alias_candidates.append(direct_layout)

    top_level_layout = state.get("layout_preview")
    if isinstance(top_level_layout, Mapping):
        alias_candidates.append(top_level_layout)

    primary_layout = next((candidate for candidate in alias_candidates if isinstance(candidate, Mapping)), None)
    if isinstance(primary_layout, Mapping):
        virtual_state.setdefault("layout_preview", primary_layout)

    for candidate in alias_candidates:
        if isinstance(candidate, Mapping):
            replacements.update(_collect_layout_preview_replacements(candidate))

    flat_paths: dict[str, str] = {}
    _flatten_state_for_placeholders(virtual_state, "", flat_paths)
    for path, value in flat_paths.items():
        _register_direct_placeholder(replacements, f"{{{{state.{path}}}}}", value)
        _register_direct_placeholder(replacements, f"{{{{app.state.{path}}}}}", value)
        _register_direct_placeholder(replacements, f"{{{{{path}}}}}", value)
        _register_square_placeholder_variants(replacements, f"state.{path}", value)

    return replacements


def _apply_replacements_to_mapping(
    mapping: MutableMapping[str, Any], replacements: Mapping[str, str]
) -> None:
    for key, value in list(mapping.items()):
        if isinstance(value, MutableMapping):
            _apply_replacements_to_mapping(value, replacements)
            continue
        if isinstance(value, list):
            _apply_replacements_to_list(value, replacements)
            continue
        if isinstance(value, str):
            mapping[key] = _apply_replacements_to_text(value, replacements)


def _apply_replacements_to_list(collection: list[Any], replacements: Mapping[str, str]) -> None:
    for index, value in enumerate(list(collection)):
        if isinstance(value, MutableMapping):
            _apply_replacements_to_mapping(value, replacements)
        elif isinstance(value, list):
            _apply_replacements_to_list(value, replacements)
        elif isinstance(value, str):
            collection[index] = _apply_replacements_to_text(value, replacements)


def _apply_replacements_to_text(text: str, replacements: Mapping[str, str]) -> str:
    rendered = text
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    return rendered


def _apply_replacements_to_object(obj: Any, replacements: Mapping[str, str]) -> None:
    if isinstance(obj, MutableMapping):
        _apply_replacements_to_mapping(obj, replacements)
    elif isinstance(obj, list):
        _apply_replacements_to_list(obj, replacements)


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


def after_model_response_callback(*, callback_context: Any, llm_response: Any):
    """Callback executado após a geração do modelo."""

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


__all__ = ["after_model_response_callback"]
