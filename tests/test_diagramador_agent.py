"""Tests for the Diagramador agent orchestration helpers."""

from __future__ import annotations

from types import SimpleNamespace

from agents.diagramador.callbacks import after_model_response_callback
from agents.diagramador.tools import (
    SESSION_ARTIFACT_LAYOUT_PREVIEW,
    SESSION_STATE_ROOT,
)


def _response_with_placeholders() -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                "Inline: {{state.layout_preview.inline}}\n"
                                "Link: [[state.layout_preview.download]]\n"
                                "SVG: {{state.layout_preview.svg}}"
                            )
                        }
                    ]
                }
            }
        ]
    }


def _session_with_replacements() -> dict:
    return {
        SESSION_STATE_ROOT: {
            "artifacts": {
                SESSION_ARTIFACT_LAYOUT_PREVIEW: {
                    "replacements": {
                        "layout_preview.inline": "![img](data:image/svg+xml;base64,AAA)",
                        "layout_preview.download": "[abrir](data:image/svg+xml;base64,AAA)",
                        "layout_preview.svg": "data:image/svg+xml;base64,AAA",
                    }
                }
            }
        }
    }


def test_after_model_callback_replaces_placeholders():
    state = _session_with_replacements()
    response = _response_with_placeholders()

    after_model_response_callback(
        callback_context=SimpleNamespace(session_state=state),
        llm_response=response,
    )

    rendered = response["candidates"][0]["content"]["parts"][0]["text"]
    assert "{{state.layout_preview.inline}}" not in rendered
    assert "data:image/svg+xml;base64,AAA" in rendered


def test_after_model_callback_handles_nested_context():
    state = _session_with_replacements()
    response = _response_with_placeholders()

    nested_context = SimpleNamespace(
        invocation_context=SimpleNamespace(
            context=SimpleNamespace(state=state)
        )
    )

    after_model_response_callback(
        callback_context=nested_context,
        llm_response=response,
    )

    rendered = response["candidates"][0]["content"]["parts"][0]["text"]
    assert "[[state.layout_preview.download]]" not in rendered
    assert rendered.count("data:image/svg+xml") >= 2
