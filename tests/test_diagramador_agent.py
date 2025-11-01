"""Tests for the Diagramador agent orchestration helpers."""

from __future__ import annotations

from types import SimpleNamespace

from agents.diagramador.callbacks import after_model_response_callback
from agents.diagramador.tools import SESSION_ARTIFACT_LAYOUT_PREVIEW, SESSION_STATE_ROOT


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
    svg_data_uri = "data:image/svg+xml;base64,AAA"
    inline_html = (
        '<img src="data:image/svg+xml;base64,AAA" alt="Template - Layout - View" '
        'title="Template - Layout - View" width="100%" />'
    )
    download_markdown = "[abrir](data:image/svg+xml;base64,AAA)"
    return {
        SESSION_STATE_ROOT: {
            "artifacts": {
                SESSION_ARTIFACT_LAYOUT_PREVIEW: {
                    "replacements": {
                        "layout_preview.inline": inline_html,
                        "layout_preview.download": download_markdown,
                        "layout_preview.download.markdown": download_markdown,
                        "layout_preview.download.label": "Abrir",
                        "layout_preview.download.url": svg_data_uri,
                        "layout_preview.svg": svg_data_uri,
                        "layout_preview.image.alt": "Template - Layout - View",
                        "layout_preview.image.title": "Template - Layout - View",
                    }
                }
            },
            "layout_preview": {
                "template_name": "Template",
                "layout_name": "Layout",
                "view_name": "View",
                "inline": inline_html,
                "download": {
                    "markdown": download_markdown,
                    "url": svg_data_uri,
                    "label": "Abrir",
                },
                "svg": svg_data_uri,
                "image": {
                    "alt": "Template - Layout - View",
                    "title": "Template - Layout - View",
                },
                "files": {},
            },
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


def test_after_model_callback_handles_attribute_based_response():
    state = _session_with_replacements()

    class Part:
        def __init__(self, text: str) -> None:
            self.text = text

    class Content:
        def __init__(self, parts) -> None:
            self.parts = parts

    class Candidate:
        def __init__(self, content) -> None:
            self.content = content

    class Response:
        def __init__(self, candidates) -> None:
            self.candidates = candidates

    response = Response(
        [
            Candidate(
                Content(
                    [
                        Part(
                            "Inline: {{state.layout_preview.inline}}\n"
                            "Link: [[state.layout_preview.download]]\n"
                            "SVG: {{state.layout_preview.svg}}"
                        )
                    ]
                )
            )
        ]
    )

    after_model_response_callback(
        callback_context=SimpleNamespace(session_state=state),
        llm_response=response,
    )

    rendered_text = response.candidates[0].content.parts[0].text
    assert "{{state.layout_preview.inline}}" not in rendered_text
    assert "[[state.layout_preview.download]]" not in rendered_text
    assert rendered_text.count("data:image/svg+xml") >= 2


def test_after_model_callback_replaces_top_level_text():
    state = _session_with_replacements()
    response = {
        "text": (
            "Inline={{session.state.layout_preview.inline}} "
            "SVG={{session.state.layout_preview.svg}} "
            "ALT={{session.state.layout_preview.image.alt}}"
        ),
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Placeholder {{session.state.layout_preview.inline}}"}
                    ]
                }
            }
        ],
    }

    after_model_response_callback(
        callback_context=SimpleNamespace(session_state=state),
        llm_response=response,
    )

    assert "{{" not in response["text"]
    assert "data:image/svg+xml" in response["text"]
    assert "<img " in response["text"]
