import sys
from pathlib import Path
from typing import Any, Dict

import pytest

THIS_FILE = Path(__file__).resolve()
ROOT = next(parent for parent in THIS_FILE.parents if (parent / "pyproject.toml").exists())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dynamic_agents import RuntimeToolError, SESSION_REGISTRY_KEY  # noqa: E402
from dynamic_agents import runtime as runtime_module  # noqa: E402


def test_web_travel_search_flights_uses_state_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from dynamic_agents.template_samples.travel_planner.tools.interactions.web_travel_search.tool import (  # noqa: E402
        SearchResult,
        Tool,
    )

    tool = Tool(metadata={})
    state: Dict[str, Any] = {
        "origin": "CWB",
        "destination": "CDG",
        "travel_dates": {"departure": "2025-03-02", "return": "2025-03-13"},
        "specialists": {
            "flight": {"inputs": {"origin": "CWB", "destination": "CDG"}}
        },
    }

    def fake_safe_search(self, query, *, limit, fallback, context):  # type: ignore[override]
        assert query.startswith("flight CWB to CDG")
        assert context == {
            "origin": "CWB",
            "destination": "CDG",
            "departure_date": "2025-03-02",
            "return_date": "2025-03-13",
            "type": "flight",
        }
        return (
            [
                SearchResult(
                    title="Option A",
                    url="https://example.com",
                    description="Synthetic option",
                    provider="synthetic",
                )
            ],
            {"provider": "synthetic"},
        )

    monkeypatch.setattr(Tool, "_safe_search", fake_safe_search, raising=False)

    payload = tool.search_flights(
        origin=None,
        destination="",
        departure_date=None,
        return_date=None,
        state=state,
    )

    assert payload["itineraries"][0]["title"] == "Option A"
    assert state["travel_dates"]["departure"] == "2025-03-02"
    assert state["travel_dates"]["return"] == "2025-03-13"


def test_web_travel_search_flights_requires_context_when_unavailable() -> None:
    from dynamic_agents.template_samples.travel_planner.tools.interactions.web_travel_search.tool import Tool  # noqa: E402

    tool = Tool(metadata={})
    with pytest.raises(RuntimeToolError) as excinfo:
        tool.search_flights(origin=None, destination=None, state={})

    assert "Parâmetros obrigatórios ausentes" in str(excinfo.value)


def test_web_travel_search_flights_infers_from_request_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agents.template_samples.travel_planner.tools.interactions.web_travel_search.tool import (  # noqa: E402
        SearchResult,
        Tool,
    )

    tool = Tool(metadata={})
    request = (
        "Por favor, encontre opções de voo para uma pessoa, saindo de Curitiba (CWB) para Paris (CDG/ORY) "
        "do dia 02/03 ao dia 13/03 dentro de R$10.000."
    )
    state: Dict[str, Any] = {
        "specialists": {
            "flight_specialist": {
                "inputs": {
                    "request": request,
                }
            }
        }
    }

    def fake_safe_search(self, query, *, limit, fallback, context):  # type: ignore[override]
        assert "flight Curitiba" in query
        assert "Paris" in query
        assert context["origin"].startswith("Curitiba")
        assert context["destination"].startswith("Paris")
        assert context["departure_date"] == "02/03"
        assert context["return_date"] == "13/03"
        return (
            [
                SearchResult(
                    title="Opção Econômica",
                    url="https://example.com/flight",
                    description="Voo de teste",
                    provider="synthetic",
                )
            ],
            {"provider": "synthetic"},
        )

    monkeypatch.setattr(Tool, "_safe_search", fake_safe_search, raising=False)

    payload = tool.search_flights(state=state)

    assert payload["itineraries"][0]["title"] == "Opção Econômica"
    assert state["origin"].startswith("Curitiba")
    assert state["destination"].startswith("Paris")
    assert state["travel_dates"]["departure"] == "02/03"
    assert state["travel_dates"]["return"] == "13/03"


def test_web_travel_search_flights_infers_from_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agents.template_samples.travel_planner.tools.interactions.web_travel_search.tool import (  # noqa: E402
        SearchResult,
        Tool,
    )

    tool = Tool(metadata={})
    transcript_entry = {
        "payload": {
            "content": {
                "parts": [
                    {
                        "text": (
                            "Recebi os detalhes da viagem:\n"
                            "* **Origem:** Curitiba (CWB)\n"
                            "* **Destino:** Paris (CDG)\n"
                            "* **Datas:** 02/03 a 13/03\n"
                        )
                    }
                ]
            }
        }
    }
    state: Dict[str, Any] = {"transcript": [transcript_entry]}

    def fake_safe_search(self, query, *, limit, fallback, context):  # type: ignore[override]
        assert "Curitiba" in context["origin"]
        assert "Paris" in context["destination"]
        assert context["departure_date"] == "02/03"
        assert context["return_date"] == "13/03"
        return (
            [
                SearchResult(
                    title="Opção Direta",
                    url="https://example.com/direct",
                    description="Voo direto",
                    provider="synthetic",
                )
            ],
            {"provider": "synthetic"},
        )

    monkeypatch.setattr(Tool, "_safe_search", fake_safe_search, raising=False)

    payload = tool.search_flights(state=state)

    assert payload["itineraries"][0]["title"] == "Opção Direta"
    assert state["origin"].startswith("Curitiba")
    assert state["destination"].startswith("Paris")
    assert state["travel_dates"]["departure"] == "02/03"
    assert state["travel_dates"]["return"] == "13/03"


def test_web_travel_search_flights_reads_from_session_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agents.template_samples.travel_planner.tools.interactions.web_travel_search.tool import (  # noqa: E402
        SearchResult,
        Tool,
    )

    tool = Tool(metadata={})
    request = (
        "Preciso de passagens saindo de Curitiba para Paris entre 02/03 e 13/03 "
        "para uma pessoa com orçamento de R$10.000."
    )
    state: Dict[str, Any] = {
        SESSION_REGISTRY_KEY: {
            "abc": {
                "specialists": {
                    "flight_specialist": {
                        "inputs": {"request": request},
                    }
                }
            }
        }
    }

    def fake_safe_search(self, query, *, limit, fallback, context):  # type: ignore[override]
        assert context["origin"].lower().startswith("curitiba")
        assert context["destination"].lower().startswith("paris")
        return (
            [
                SearchResult(
                    title="Opção com conexão",
                    url="https://example.com/flight",
                    description="Voo de teste",
                    provider="synthetic",
                )
            ],
            {"provider": "synthetic"},
        )

    monkeypatch.setattr(Tool, "_safe_search", fake_safe_search, raising=False)

    payload = tool.search_flights(state=state)

    assert payload["itineraries"][0]["title"] == "Opção com conexão"
    session_state = state[SESSION_REGISTRY_KEY]["abc"]
    assert session_state["origin"].startswith("Curitiba")
    assert session_state["destination"].startswith("Paris")
    assert session_state["travel_dates"]["departure"] == "02/03"
    assert session_state["travel_dates"]["return"] == "13/03"


def test_web_travel_search_flights_reads_from_cached_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agents.template_samples.travel_planner.tools.interactions.web_travel_search.tool import (  # noqa: E402
        SearchResult,
        Tool,
    )

    session_id = "sess-flight"
    request = "Preciso de voos de Curitiba para Paris entre 02/03 e 13/03"
    initial_state = runtime_module._ensure_session_container({}, session_id)
    initial_state.setdefault("specialists", {}).setdefault("flight_specialist", {}).setdefault("inputs", {})[
        "request"
    ] = request

    state_for_tool = runtime_module._ensure_session_container({}, session_id)

    tool = Tool(metadata={})

    def fake_safe_search(self, query, *, limit, fallback, context):  # type: ignore[override]
        assert context["origin"].lower().startswith("curitiba")
        assert context["destination"].lower().startswith("paris")
        return (
            [
                SearchResult(
                    title="Opção cache",
                    url="https://example.com/cache",
                    description="Resultado da busca",
                    provider="synthetic",
                )
            ],
            {"provider": "synthetic"},
        )

    monkeypatch.setattr(Tool, "_safe_search", fake_safe_search, raising=False)

    payload = tool.search_flights(state=state_for_tool)

    assert payload["itineraries"][0]["title"] == "Opção cache"
    assert state_for_tool["origin"].startswith("Curitiba")
    assert state_for_tool["destination"].startswith("Paris")


def test_web_travel_search_flights_handles_structured_locations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dynamic_agents.template_samples.travel_planner.tools.interactions.web_travel_search.tool import (  # noqa: E402
        SearchResult,
        Tool,
    )

    tool = Tool(metadata={})
    state: Dict[str, Any] = {
        "origin": {"code": "CWB", "city": "Curitiba"},
        "destination": {"label": "Paris, France (CDG)", "code": "CDG"},
    }

    def fake_safe_search(self, query, *, limit, fallback, context):  # type: ignore[override]
        assert context["origin"] == "CWB"
        assert context["destination"] == "CDG"
        results = fallback()
        return (
            results,
            {
                "provider": results[0].provider if results else "synthetic",
                "fallback_used": True,
            },
        )

    monkeypatch.setattr(Tool, "_safe_search", fake_safe_search, raising=False)

    payload = tool.search_flights(origin=None, destination=None, state=state)

    assert payload["itineraries"]
    assert state["origin"] == "CWB"
    assert state["destination"] == "CDG"


def test_web_travel_search_hotels_handles_guests(monkeypatch: pytest.MonkeyPatch) -> None:
    from dynamic_agents.template_samples.travel_planner.tools.interactions.web_travel_search.tool import (  # noqa: E402
        SearchResult,
        Tool,
    )

    tool = Tool(metadata={})
    state: Dict[str, Any] = {
        "destination": "Paris",
        "travel": {"guests": 2},
        "specialists": {"hotel_specialist": {"inputs": {"destination": "Paris"}}},
    }

    def fake_safe_search(self, query, *, limit, fallback, context):  # type: ignore[override]
        assert query.startswith("hotel Paris best prices")
        assert "for 2 guests" in query
        assert context == {
            "destination": "Paris",
            "check_in": "2025-03-02",
            "check_out": "2025-03-13",
            "guests": 2,
            "max_budget": 4500,
            "type": "hotel",
        }
        return (
            [
                SearchResult(
                    title="Option H",
                    url="https://example.com/hotel",
                    description="Synthetic hotel",
                    provider="synthetic",
                )
            ],
            {"provider": "synthetic"},
        )

    monkeypatch.setattr(Tool, "_safe_search", fake_safe_search, raising=False)

    payload = tool.search_hotels(
        destination=None,
        check_in="2025-03-02",
        check_out="2025-03-13",
        guests=None,
        max_budget=4500,
        state=state,
    )

    assert payload["options"][0]["title"] == "Option H"
    assert state["travel"]["guests"] == 2
