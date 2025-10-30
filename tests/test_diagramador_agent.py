"""Tests for the Diagramador agent orchestration helpers."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest import mock

from agents.diagramador.callbacks import after_model_response_callback
from agents.diagramador.tools import (
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
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
                                "Imagem embutida: {{state.preview_token}}\n"
                                "Link SVG: [[state.preview_token_url]]\n"
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
                "state_placeholder_prefix": "preview_token",
                "placeholder_token": "preview_token",
                "placeholders": {
                    "image": "{{state.preview_token}}",
                    "link": "{{state.preview_token_link}}",
                    "uri": "{{state.preview_token_url}}",
                    "url": "{{state.preview_token_url}}",
                    "bare_image": "{{preview_token}}",
                    "bare_link": "{{preview_token_link}}",
                    "bare_uri": "{{preview_token_url}}",
                },
            }
        }
        return {"status": "ok", "artifact": SESSION_ARTIFACT_LAYOUT_PREVIEW}

    with mock.patch(
        "agents.diagramador.callbacks.layout_preview_after_model._generate_layout_preview",
        side_effect=_fake_generate_layout_preview,
    ) as mocked:
        after_model_response_callback(
            callback_context=SimpleNamespace(state=state),
            llm_response=llm_response,
        )

    mocked.assert_called_once()

    rendered_text = llm_response["candidates"][0]["content"]["parts"][0]["text"]
    assert expected_png in rendered_text
    assert expected_svg in rendered_text
    assert "{{state.preview_token}}" not in rendered_text
    assert "[[state.preview_token_url]]" not in rendered_text
    assert '<img src="data:image/png;base64,AAA"' in rendered_text
    assert 'href="data:image/svg+xml;base64,BBB"' in rendered_text


def test_after_model_callback_handles_nested_session_state():
    base_mapping = {
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

    llm_response = _build_response_with_placeholder()

    expected_png = "data:image/png;base64,AAA"
    expected_svg = "data:image/svg+xml;base64,BBB"

    def _fake_generate_layout_preview(datamodel, template_path=None, session_state=None, view_filter=None):
        artifacts = session_state.setdefault("diagramador", {}).setdefault("artifacts", {})
        artifacts[SESSION_ARTIFACT_LAYOUT_PREVIEW] = {
            "primary_preview": {
                "inline_placeholder": "{{state.preview_token}}",
                "inline_markdown": f'<img src="{expected_png}" alt="Preview">',
                "inline_data_uri": expected_png,
                "download_placeholder": "{{state.preview_token_link}}",
                "download_markdown": f"[SVG]({expected_svg})",
                "download_data_uri": expected_svg,
                "view_name": "Visão",
                "state_placeholder_prefix": "preview_token",
                "placeholder_token": "preview_token",
                "placeholders": {
                    "image": "{{state.preview_token}}",
                    "link": "{{state.preview_token_link}}",
                    "uri": "{{state.preview_token_url}}",
                },
            }
        }
        return {"status": "ok", "artifact": SESSION_ARTIFACT_LAYOUT_PREVIEW}

    nested_context = SimpleNamespace(
        invocation_context=SimpleNamespace(
            session_state=SimpleNamespace(data=base_mapping)
        )
    )

    with mock.patch(
        "agents.diagramador.callbacks.layout_preview_after_model._generate_layout_preview",
        side_effect=_fake_generate_layout_preview,
    ) as mocked:
        after_model_response_callback(
            callback_context=nested_context,
            llm_response=llm_response,
        )

    mocked.assert_called_once()
    rendered_text = llm_response["candidates"][0]["content"]["parts"][0]["text"]
    assert expected_png in rendered_text
    assert expected_svg in rendered_text
    assert "{{state.preview_token}}" not in rendered_text
