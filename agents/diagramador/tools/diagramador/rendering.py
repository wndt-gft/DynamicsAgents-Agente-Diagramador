"""Rotinas utilitárias para renderizar pré-visualizações simples em SVG."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Mapping

__all__ = ["render_view_layout"]


def _slugify(name: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in name)
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or "view"


def _build_svg_document(view_name: str, alias: str) -> str:
    safe_name = view_name.strip() or alias.strip() or "View"
    safe_alias = alias.strip() or safe_name
    return (
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"800\" height=\"450\" "
        "viewBox=\"0 0 800 450\">"
        "<rect x=\"0\" y=\"0\" width=\"800\" height=\"450\" fill=\"#f4f6fb\" "
        "stroke=\"#4d6ed3\" stroke-width=\"2\" rx=\"16\"/>"
        "<text x=\"50%\" y=\"50%\" dominant-baseline=\"middle\" text-anchor=\"middle\" "
        "font-family=\"Segoe UI, Arial, sans-serif\" font-size=\"28\" fill=\"#1a2b6d\">"
        f"{safe_alias}" "</text>"
        "<text x=\"50%\" y=\"65%\" dominant-baseline=\"middle\" text-anchor=\"middle\" "
        "font-family=\"Segoe UI, Arial, sans-serif\" font-size=\"16\" fill=\"#4d6ed3\">"
        f"{safe_name}" "</text>"
        "</svg>"
    )


def render_view_layout(
    view_name: str,
    view_alias: str,
    layout: Mapping[str, object] | None,
    *,
    output_dir: Path,
) -> dict[str, object]:
    svg_text = _build_svg_document(view_name, view_alias)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_slugify(view_alias or view_name)}.svg"
    svg_path = output_dir / filename
    svg_path.write_text(svg_text, encoding="utf-8")

    svg_base64 = base64.b64encode(svg_text.encode("utf-8")).decode("ascii")
    data_uri = f"data:image/svg+xml;base64,{svg_base64}"
    inline_markdown = f"![Pré-visualização de {view_name}]({data_uri})"
    download_markdown = f"[Abrir {view_name} em SVG]({data_uri})"

    return {
        "format": "svg",
        "local_path": str(svg_path),
        "svg_data_uri": data_uri,
        "inline_markdown": inline_markdown,
        "download_markdown": download_markdown,
    }
