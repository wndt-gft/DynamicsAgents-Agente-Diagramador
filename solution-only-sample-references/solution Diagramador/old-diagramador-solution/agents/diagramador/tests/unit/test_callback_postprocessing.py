"""Tests for the output post-processing callbacks."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import importlib

from google.genai import types as genai_types
from google.adk.models.llm_response import LlmResponse

callback_module = importlib.import_module("app.callback")


def test_sanitize_model_response_callback_applies_canonical_url():
    callback_state = {}
    mock_context = MagicMock()
    mock_context.state = callback_state

    with patch.object(callback_module, "_get_last_generation_result", return_value={
        "signed_url": "https://storage.googleapis.com/diagram_signed_temp/correct.xml",
        "gcs_blob_name": "gs://diagram_signed_temp/correct.xml",
    }):
        response = LlmResponse(
            content=genai_types.Content(
                parts=[genai_types.Part(
                    text="Link: https://storage.googleapis.com/wrong-bucket/old.xml"
                )]
            )
        )
        sanitized = callback_module.sanitize_model_response_callback(
            mock_context, response
        )

    assert sanitized is not None
    assert sanitized.content.parts[0].text.endswith("correct.xml")
    assert mock_context.state["processed_urls"] is True
    assert mock_context.state["gcs_urls_corrected"] is True


def test_after_agent_callback_sanitizes_string_output():
    ctx = MagicMock()
    ctx.final_content = "Download: https://storage.googleapis.com/old-bucket/file.xml"
    ctx.state = {}

    result = callback_module.after_agent_callback(ctx)
    assert result is not None
    part_text = result.parts[0].text
    assert "diagram_signed_temp" in part_text or part_text.startswith("Download: file:///")
    assert ctx.state["processed_urls"] is True


def test_after_agent_callback_processes_dict_output():
    ctx = MagicMock()
    ctx.final_content = {
        "link": "gs://wrong-bucket/file.xml",
        "nested": {"url": "https://storage.googleapis.com/another/file.xml"},
    }
    ctx.state = {}

    sanitized = callback_module.after_agent_callback(ctx)
    assert sanitized is not None
    text = sanitized.parts[0].text
    assert "diagram_signed_temp" in text
    assert ctx.state["gcs_urls_corrected"] is True


def test_validate_and_extract_helpers():
    good_https = "https://storage.googleapis.com/diagram_signed_temp/file.xml"
    bad_https = "https://storage.googleapis.com/other/file.txt"
    good_gs = "gs://diagram_signed_temp/file.xml"
    assert callback_module.validate_gcs_url(good_https) is True
    assert callback_module.validate_gcs_url(good_gs) is True
    assert callback_module.validate_gcs_url(bad_https) is False

    content = genai_types.Content(parts=[genai_types.Part(text=f"See {good_https}")])
    urls = callback_module.extract_urls_from_content(content)
    assert urls == [good_https]


def test_ensure_correct_gcs_url_wrapper(monkeypatch):
    ctx = MagicMock()
    ctx.final_content = "https://storage.googleapis.com/other/file.xml"

    with patch.object(callback_module, "after_agent_callback", return_value="patched") as wrapper:
        result = callback_module.ensure_correct_gcs_url_wrapper(ctx)

    assert result == "patched"
    wrapper.assert_called_once()


def test_override_with_canonical_urls(monkeypatch):
    canonical = {
        "signed_url": "https://storage.googleapis.com/diagram_signed_temp/canonical.xml",
        "gcs_blob_name": "gs://diagram_signed_temp/canonical.xml",
    }
    monkeypatch.setattr(callback_module, "_get_last_generation_result", lambda: canonical)

    raw_text = "https://storage.googleapis.com/wrong/file.xml and gs://wrong/file.xml"
    fixed = callback_module._override_with_canonical_urls(raw_text)
    assert fixed.count("canonical.xml") == 2


def test_correct_single_url_variants():
    corrected_https = callback_module._correct_single_url("https://storage.googleapis.com/other-bucket/test.xml")
    assert corrected_https.endswith("diagram_signed_temp/test.xml")
    corrected_gs = callback_module._correct_single_url("gs://wrong-bucket/test.xml")
    assert corrected_gs.endswith("diagram_signed_temp/test.xml")
    unchanged = callback_module._correct_single_url("not-a-url")
    assert unchanged == "not-a-url"


def test_sanitize_content_parts_no_modifications():
    content = genai_types.Content(parts=[genai_types.Part(text="No URLs here")])
    assert callback_module._sanitize_content_parts(content) is None


def test_after_agent_callback_without_output():
    ctx = MagicMock()
    ctx.final_content = None
    ctx.content = None
    ctx.state = {}
    assert callback_module.after_agent_callback(ctx) is None
