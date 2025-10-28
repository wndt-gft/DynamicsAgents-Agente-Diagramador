from __future__ import annotations

from pathlib import Path
import sys
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "agents" / "diagramador"))

import sitecustomize  # noqa: F401 - ensure stubs are loaded before other imports
import pytest

from agents.diagramador import agent
from agents.diagramador.tools.diagramador import (
    BLUEPRINT_CACHE_KEY,
    DEFAULT_TEMPLATE,
    SESSION_STATE_ROOT,
)
from agents.diagramador.tools.diagramador import operations


def _sample_template_path() -> Path:
    return operations._resolve_package_path(DEFAULT_TEMPLATE)


@pytest.fixture()
def sample_payload() -> str:
    model_path = operations._resolve_package_path(
        Path("tools/archimate_exchange/samples/pix_solution_case/pix_container_datamodel.json")
    )
    return model_path.read_text(encoding="utf-8")


@pytest.fixture()
def session_state() -> dict:
    return {}


@pytest.fixture(autouse=True)
def stub_mermaid_validation(monkeypatch):
    response = mock.Mock()
    response.raise_for_status = mock.Mock()
    response.text = "<svg id='mermaidInkSvg'></svg>"
    validator = mock.Mock(return_value=response)
    monkeypatch.setattr(operations, "_mermaid_validation_request", validator)
    return validator


def test_describe_template_uses_session_state_cache():
    session_state: dict = {}
    template_path = str(_sample_template_path())

    guidance = agent.describe_template(template_path, session_state=session_state)

    assert guidance["model"]["identifier"]
    bucket = session_state[SESSION_STATE_ROOT]
    cache = bucket[BLUEPRINT_CACHE_KEY]
    assert template_path in cache


def test_finalize_datamodel_passes_session_state(sample_payload, session_state):
    template_path = str(_sample_template_path())
    agent.describe_template(template_path, session_state=session_state)

    with mock.patch(
        "agents.diagramador.tools.diagramador.operations._parse_template_blueprint",
        side_effect=AssertionError("blueprint should be reused from session cache"),
    ):
        result = agent.finalize_datamodel(
            sample_payload,
            template_path,
            session_state=session_state,
        )

    assert result["element_count"] > 0


def test_generate_mermaid_preview_passes_session_state(sample_payload, session_state):
    template_path = str(_sample_template_path())
    agent.describe_template(template_path, session_state=session_state)

    with mock.patch(
        "agents.diagramador.tools.diagramador.operations._parse_template_blueprint",
        side_effect=AssertionError("template parsing should be skipped when cached"),
    ):
        preview = agent.generate_mermaid_preview(
            sample_payload,
            template_path,
            session_state=session_state,
        )

    assert preview["view_count"] >= 1


def test_wrappers_accept_session_state_json(sample_payload):
    template_path = str(_sample_template_path())
    session_state_json = "{}"

    guidance = agent.describe_template(template_path, session_state=session_state_json)
    assert guidance["model"]["identifier"]

    preview = agent.generate_mermaid_preview(
        sample_payload,
        template_path,
        session_state=session_state_json,
    )

    assert preview["view_count"] >= 1


def test_wrappers_reject_invalid_session_state_json():
    template_path = str(_sample_template_path())

    with pytest.raises(ValueError):
        agent.describe_template(template_path, session_state="not-json")
