"""Tests for the Diagramador agent orchestration helpers."""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "agents" / "diagramador"))

import sitecustomize  # noqa: F401

from agents.diagramador.agent import (  # type: ignore[import-not-found]
    _after_model_response_callback,
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
)
from agents.diagramador.tools.diagramador import (  # type: ignore[import-not-found]
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    SESSION_ARTIFACT_TEMPLATE_GUIDANCE,
)


class _MutableState(dict):
    """Minimal session state stub replicating ADK behaviour."""

    def to_dict(self):  # pragma: no cover - simple passthrough
        return copy.deepcopy(self)


def _build_response_with_placeholder() -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                "Prévia: {{state.layout_preview.primary_preview.inline_markdown}}\n"
                                "Link: {{state.layout_preview.primary_preview.download_markdown}}"
                            )
                        }
                    ]
                }
            }
        ]
    }


def test_after_model_callback_generates_preview_before_replacement():
    state = _MutableState(
        {
            "diagramador": {
                "artifacts": {
                    SESSION_ARTIFACT_TEMPLATE_GUIDANCE: {
                        "model": {"path": "templates/BV-C4-Model-SDLC/layout_template.xml"}
                    },
                    SESSION_ARTIFACT_FINAL_DATAMODEL: {"json": "{}", "template": "ignored"},
                },
                "view_focus": ["id-171323"],
            }
        }
    )

    llm_response = _build_response_with_placeholder()

    expected_png = "data:image/png;base64,AAA"
    expected_svg = "data:image/svg+xml;base64,BBB"

    def _fake_generate_layout_preview(datamodel, template_path=None, session_state=None, view_filter=None):
        artifacts = session_state.setdefault("diagramador", {}).setdefault("artifacts", {})
        artifacts[SESSION_ARTIFACT_LAYOUT_PREVIEW] = {
            "primary_preview": {
                "inline_placeholder": "{{state.layout_preview.primary_preview.inline_markdown}}",
                "inline_markdown": f'<img src="{expected_png}" alt="Preview">',
                "inline_data_uri": expected_png,
                "download_placeholder": "{{state.layout_preview.primary_preview.download_markdown}}",
                "download_markdown": f"[SVG]({expected_svg})",
                "download_data_uri": expected_svg,
                "view_name": "Visão",
            }
        }
        return {"status": "ok", "artifact": SESSION_ARTIFACT_LAYOUT_PREVIEW}

    with mock.patch("agents.diagramador.agent._generate_layout_preview", side_effect=_fake_generate_layout_preview) as mocked:
        _after_model_response_callback(
            callback_context=SimpleNamespace(state=state),
            llm_response=llm_response,
        )

    mocked.assert_called_once()

    rendered_text = llm_response["candidates"][0]["content"]["parts"][0]["text"]
    assert expected_png in rendered_text
    assert expected_svg in rendered_text
