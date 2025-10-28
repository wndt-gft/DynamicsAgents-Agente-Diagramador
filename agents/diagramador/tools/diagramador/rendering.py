"""Utilitários para renderizar visões ArchiMate em SVG/PNG preservando layout."""

from __future__ import annotations

import base64
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import svgwrite

try:  # pragma: no cover - fallback caso CairoSVG não esteja disponível
    import cairosvg  # type: ignore
except Exception:  # pragma: no cover
    cairosvg = None  # type: ignore[assignment]

DEFAULT_MARGIN = 32
DEFAULT_FONT_FAMILY = "Segoe UI"
DEFAULT_FONT_SIZE = 12
DEFAULT_FONT_WEIGHT = "normal"
DEFAULT_STROKE_WIDTH = 1.5
BACKGROUND_COLOR = "#ffffff"
ARROW_MARKER_SIZE = (10, 10)


def _slugify_identifier(value: Optional[str]) -> str:
    if not value:
        return "view"
    normalized = re.sub(r"\s+", "_", value)
    cleaned = re.sub(r"[^0-9A-Za-z_.-]", "_", normalized)
    cleaned = cleaned.strip("._")
    return cleaned or "view"


def _color_to_rgba(color: Optional[Dict[str, Any]], default: str) -> str:
    if not isinstance(color, dict):
        return default
    r = int(color.get("r", 0))
    g = int(color.get("g", 0))
    b = int(color.get("b", 0))
    alpha = color.get("a")
    if alpha is None:
        return f"rgb({r},{g},{b})"
    try:
        alpha_float = float(alpha)
    except (TypeError, ValueError):
        alpha_float = 255
    if alpha_float >= 255:
        return f"rgb({r},{g},{b})"
    if alpha_float <= 0:
        return "rgba({},{},{},0)".format(r, g, b)
    alpha_norm = round(alpha_float / 255, 3)
    return f"rgba({r},{g},{b},{alpha_norm})"


def _resolve_color(
    style: Optional[Dict[str, Any]],
    key: str,
    default: str,
    *,
    allow_none: bool = False,
) -> Tuple[Optional[str], Optional[float]]:
    if isinstance(style, dict):
        payload = style.get(key)
        if isinstance(payload, dict):
            try:
                r = int(payload.get("r", 0))
                g = int(payload.get("g", 0))
                b = int(payload.get("b", 0))
            except (TypeError, ValueError):
                r = g = b = 0
            color_value = f"rgb({r},{g},{b})"
            alpha = payload.get("a")
            opacity: Optional[float] = None
            if alpha is not None:
                try:
                    alpha_float = float(alpha)
                except (TypeError, ValueError):
                    alpha_float = None
                if alpha_float is not None:
                    opacity = max(0.0, min(1.0, alpha_float / 255))
                    if opacity <= 0 and allow_none:
                        return None, opacity
            return color_value, opacity
    return (default, None)


def _extract_font_settings(
    style: Optional[Dict[str, Any]]
) -> Tuple[str, float, str, str, Optional[float]]:
    font = style.get("font") if isinstance(style, dict) else None
    family = font.get("name") if isinstance(font, dict) else None
    size = font.get("size") if isinstance(font, dict) else None
    weight = font.get("style") if isinstance(font, dict) else None
    color = font if isinstance(font, dict) else None

    font_family = str(family) if family else DEFAULT_FONT_FAMILY
    try:
        font_size = float(size)
    except (TypeError, ValueError):
        font_size = DEFAULT_FONT_SIZE
    font_weight = str(weight) if weight else DEFAULT_FONT_WEIGHT
    color_value, color_opacity = _resolve_color(color, "color", "#000000")
    font_color = color_value or "#000000"
    return font_family, font_size, font_weight, font_color, color_opacity


def _resolve_fill_style(style: Optional[Dict[str, Any]]) -> Tuple[str, Optional[float]]:
    color, opacity = _resolve_color(style, "fillColor", "#ffffff", allow_none=True)
    if color is None:
        return "none", opacity
    return color, opacity


def _resolve_stroke_style(style: Optional[Dict[str, Any]]) -> Tuple[str, Optional[float]]:
    color, opacity = _resolve_color(style, "lineColor", "#333333", allow_none=True)
    if color is None:
        return "none", opacity
    return color, opacity


def _make_data_uri(mime_type: str, payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _compute_bounds(nodes: Iterable[Dict[str, Any]]) -> Optional[Tuple[float, float, float, float]]:
    min_x = math.inf
    min_y = math.inf
    max_x = -math.inf
    max_y = -math.inf
    found = False

    for node in nodes:
        bounds = node.get("bounds")
        if not isinstance(bounds, dict):
            continue
        try:
            x = float(bounds["x"])
            y = float(bounds["y"])
            w = float(bounds["w"])
            h = float(bounds["h"])
        except (KeyError, TypeError, ValueError):
            continue
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x + w)
        max_y = max(max_y, y + h)
        found = True

    if not found:
        return None
    return min_x, min_y, max_x, max_y


def _node_center(render_info: Dict[str, float]) -> Tuple[float, float]:
    return (
        render_info["x"] + render_info["w"] / 2,
        render_info["y"] + render_info["h"] / 2,
    )


def _edge_point(bounds: Dict[str, float], target_center: Tuple[float, float]) -> Tuple[float, float]:
    cx = bounds["x"] + bounds["w"] / 2
    cy = bounds["y"] + bounds["h"] / 2
    tx, ty = target_center
    dx = tx - cx
    dy = ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    if dx == 0:
        scale = (bounds["h"] / 2) / abs(dy)
        return cx, cy + dy * scale
    if dy == 0:
        scale = (bounds["w"] / 2) / abs(dx)
        return cx + dx * scale, cy
    scale_x = (bounds["w"] / 2) / abs(dx)
    scale_y = (bounds["h"] / 2) / abs(dy)
    scale = min(scale_x, scale_y)
    return cx + dx * scale, cy + dy * scale


def render_view_layout(
    view_name: str,
    view_alias: str,
    layout: Optional[Dict[str, Any]],
    *,
    output_dir: Path,
) -> Optional[Dict[str, Any]]:
    """Renderiza uma visão utilizando as coordenadas originais do template."""

    if not layout:
        return None

    nodes = [node for node in layout.get("nodes", []) if isinstance(node, dict)]
    bounds = _compute_bounds(nodes)
    if not bounds:
        return None

    min_x, min_y, max_x, max_y = bounds
    width = max_x - min_x + 2 * DEFAULT_MARGIN
    height = max_y - min_y + 2 * DEFAULT_MARGIN

    drawing = svgwrite.Drawing(
        size=(f"{width}px", f"{height}px"),
        profile="full",
    )
    drawing.add(
        drawing.rect(
            insert=(0, 0),
            size=(width, height),
            fill=BACKGROUND_COLOR,
        )
    )

    marker = drawing.marker(
        insert=(ARROW_MARKER_SIZE[0], ARROW_MARKER_SIZE[1] / 2),
        size=ARROW_MARKER_SIZE,
        orient="auto",
        id="arrow-end",
    )
    marker.add(
        drawing.path(
            d="M0,0 L10,5 L0,10 z",
            fill="#333333",
        )
    )
    drawing.defs.add(marker)

    node_render_info: Dict[str, Dict[str, float]] = {}
    alias_lookup: Dict[str, Dict[str, float]] = {}

    for node in nodes:
        raw_bounds = node.get("bounds") or {}
        try:
            raw_x = float(raw_bounds["x"])
            raw_y = float(raw_bounds["y"])
            raw_w = float(raw_bounds["w"])
            raw_h = float(raw_bounds["h"])
        except (KeyError, TypeError, ValueError):
            continue
        x = raw_x - min_x + DEFAULT_MARGIN
        y = raw_y - min_y + DEFAULT_MARGIN
        w = raw_w
        h = raw_h

        render_bounds = {"x": x, "y": y, "w": w, "h": h}
        identifiers = {
            str(node.get(key))
            for key in ("id", "identifier", "key", "element_ref")
            if node.get(key)
        }
        for identifier in identifiers:
            node_render_info[identifier] = render_bounds
        alias = node.get("alias")
        if alias:
            alias_lookup[str(alias)] = render_bounds
            node_render_info[str(alias)] = render_bounds

        style = node.get("style") if isinstance(node.get("style"), dict) else {}
        fill_color, fill_opacity = _resolve_fill_style(style)
        stroke_color, stroke_opacity = _resolve_stroke_style(style)
        rect_kwargs = {
            "insert": (x, y),
            "size": (w, h),
            "rx": 8,
            "ry": 8,
            "fill": fill_color,
            "stroke": stroke_color,
            "stroke_width": DEFAULT_STROKE_WIDTH,
        }
        if fill_opacity is not None:
            rect_kwargs["fill_opacity"] = fill_opacity
        if stroke_opacity is not None:
            rect_kwargs["stroke_opacity"] = stroke_opacity
        drawing.add(drawing.rect(**rect_kwargs))

        font_family, font_size, font_weight, font_color, font_opacity = _extract_font_settings(style)
        title = node.get("title") or node.get("element_name") or node.get("label")
        element_type = node.get("type") or node.get("element_type")
        lines = [str(title).strip() if title else "Elemento"]
        if element_type:
            lines.append(str(element_type))

        text_start = y + font_size + 6
        for idx, line in enumerate(lines):
            text_y = text_start + idx * (font_size + 4)
            text_kwargs = {
                "insert": (x + w / 2, text_y),
                "text_anchor": "middle",
                "font_size": font_size,
                "font_family": font_family,
                "font_weight": font_weight,
                "fill": font_color,
            }
            if font_opacity is not None:
                text_kwargs["fill_opacity"] = font_opacity
            drawing.add(drawing.text(line, **text_kwargs))

    connections = [
        conn for conn in layout.get("connections", []) if isinstance(conn, dict)
    ]
    for connection in connections:
        source_ref = connection.get("source") or connection.get("source_alias")
        target_ref = connection.get("target") or connection.get("target_alias")
        if not source_ref or not target_ref:
            continue
        source_bounds = node_render_info.get(str(source_ref)) or alias_lookup.get(
            str(source_ref)
        )
        target_bounds = node_render_info.get(str(target_ref)) or alias_lookup.get(
            str(target_ref)
        )
        if not source_bounds or not target_bounds:
            continue
        src_center = _node_center(source_bounds)
        tgt_center = _node_center(target_bounds)
        start = _edge_point(source_bounds, tgt_center)
        end = _edge_point(target_bounds, src_center)
        style = connection.get("style") if isinstance(connection.get("style"), dict) else {}
        stroke_color, stroke_opacity = _resolve_stroke_style(style)
        line_kwargs = {
            "start": start,
            "end": end,
            "stroke": stroke_color,
            "stroke_width": DEFAULT_STROKE_WIDTH,
            "marker_end": marker.get_funciri(),
        }
        if stroke_opacity is not None:
            line_kwargs["stroke_opacity"] = stroke_opacity
        drawing.add(drawing.line(**line_kwargs))
        label = connection.get("label")
        if label:
            mid_x = (start[0] + end[0]) / 2
            mid_y = (start[1] + end[1]) / 2
            drawing.add(
                drawing.text(
                    str(label),
                    insert=(mid_x, mid_y - 4),
                    text_anchor="middle",
                    font_size=DEFAULT_FONT_SIZE,
                    font_family=DEFAULT_FONT_FAMILY,
                    fill="#333333",
                )
            )

    svg_bytes = drawing.tostring().encode("utf-8")
    slug = _slugify_identifier(view_alias or view_name)
    svg_path = output_dir / f"{slug}_layout.svg"
    svg_path.write_bytes(svg_bytes)

    payload: Dict[str, Any] = {
        "format": "svg",
        "path": str(svg_path.resolve()),
        "width": width,
        "height": height,
        "data_uri": _make_data_uri("image/svg+xml", svg_bytes),
    }

    if cairosvg is not None:  # pragma: no cover - depende de lib externa
        try:
            png_bytes = cairosvg.svg2png(bytestring=svg_bytes)
        except Exception:
            png_bytes = None
        if png_bytes:
            png_path = output_dir / f"{slug}_layout.png"
            png_path.write_bytes(png_bytes)
            payload["png"] = {
                "format": "png",
                "path": str(png_path.resolve()),
                "data_uri": _make_data_uri("image/png", png_bytes),
            }

    return payload


__all__ = ["render_view_layout"]
