import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.diagramador.app.agents.acronym_lookup_agent.tools.interactions.acronym_lookup_tool.tool import (
    Tool,
)


def _build_tool(tmp_path, entries):
    database_path = tmp_path / "acronyms.json"
    database_path.write_text(json.dumps(entries), encoding="utf-8")
    return Tool(metadata={"database": str(database_path)})


def test_search_acronyms_accepts_dict_input(tmp_path):
    tool = _build_tool(
        tmp_path,
        [
            {
                "acronym": "PIXG",
                "meaning": "Plataforma PIX Gateway",
                "keywords": ["pix", "transferências"],
            },
            {
                "acronym": "MOBI",
                "meaning": "Aplicativo Mobile",
            },
        ],
    )

    payload = {
        "text": "Como cliente quero realizar transferências via PIX com confirmação.",
        "metadata": {"source": "user"},
    }

    response = tool.search_acronyms(payload)

    assert response["acronym_lookup"]["query"].startswith("Como cliente")
    acronyms = {item["acronym"] for item in response["acronym_lookup"]["results"]}
    assert "PIXG" in acronyms


def test_normalize_user_story_collects_nested_values(tmp_path):
    tool = _build_tool(
        tmp_path,
        [
            {
                "acronym": "DICT",
                "meaning": "Diretório de Identificadores de Contas Transacionais",
                "keywords": ["dict", "identificadores"],
            }
        ],
    )

    payload = {
        "value": {
            "content": [
                "Integração com o DICT",
                {"additional": "Validação de identificadores"},
            ]
        }
    }

    response = tool.search_acronyms(payload)

    assert "DICT" in {item["acronym"] for item in response["acronym_lookup"]["results"]}
    # Garante que a consulta armazenada combina os fragmentos coletados.
    assert "Integração" in response["acronym_lookup"]["query"]
    assert "Validação" in response["acronym_lookup"]["query"]


def test_accepts_text_keyword_and_prevents_duplicate_history(tmp_path):
    tool = _build_tool(
        tmp_path,
        [
            {
                "acronym": "GCP",
                "meaning": "Google Cloud Platform",
                "keywords": ["cloud"],
            }
        ],
    )

    state = {}
    response = tool.search_acronyms(text="Migração para cloud.", state=state)

    assert "GCP" in {item["acronym"] for item in response["acronym_lookup"]["results"]}
    assert len(response["acronym_search"]) == 1

    # Invocação repetida com o mesmo conteúdo não deve duplicar o histórico.
    response = tool.search_acronyms(text="Migração para cloud.", state=state)
    assert len(response["acronym_search"]) == 1


def test_falls_back_to_request_when_state_pointer_is_received(tmp_path):
    tool = _build_tool(
        tmp_path,
        [
            {
                "acronym": "PIX",
                "meaning": "Pagamento Instantâneo",
                "keywords": ["transferências"],
            }
        ],
    )

    response = tool.search_acronyms(
        user_story={"$state": "analysis.user_story"},
        request="Transferências instantâneas via PIX.",
    )

    assert response["acronym_lookup"]["query"].startswith("Transferências")
    assert any(item["acronym"] == "PIX" for item in response["acronym_lookup"]["results"])


def test_resolves_complex_state_reference(tmp_path):
    tool = _build_tool(
        tmp_path,
        [
            {
                "acronym": "PIX",
                "meaning": "Pagamento Instantâneo",
                "keywords": ["transferências"],
            }
        ],
    )

    state = {
        "analysis": {
            "user_story": {
                "text": "Cliente realiza pagamentos PIX a partir do aplicativo.",
                "metadata": {"source": "user"},
            }
        }
    }

    response = tool.search_acronyms(
        user_story={"$state": {"path": "analysis.user_story"}},
        state=state,
    )

    assert "Cliente realiza" in response["acronym_lookup"]["query"]
    assert any(item["acronym"] == "PIX" for item in response["acronym_lookup"]["results"])


def test_uses_state_fallback_when_inputs_missing(tmp_path):
    tool = _build_tool(
        tmp_path,
        [
            {
                "acronym": "MOBI",
                "meaning": "Aplicativo Mobile",
                "keywords": ["mobile"],
            }
        ],
    )

    state = {
        "analysis": {
            "last_presented": {
                "user_story": {"text": "Usuário acessa serviços pelo app mobile (MOBI)."}
            }
        }
    }

    response = tool.search_acronyms(state=state)

    assert "app mobile" in response["acronym_lookup"]["query"].lower()
    assert any(item["acronym"] == "MOBI" for item in response["acronym_lookup"]["results"])


def test_resolves_user_story_from_input_pointer(tmp_path):
    tool = _build_tool(
        tmp_path,
        [
            {
                "acronym": "PIX",
                "meaning": "Pagamento Instantâneo",
                "keywords": ["pix"],
            }
        ],
    )

    state = {
        "inputs": {
            "user_story": {
                "text": "Como cliente desejo realizar transferências PIX com confirmação.",
            }
        }
    }

    response = tool.search_acronyms(
        user_story={"$input": "user_story"},
        state=state,
    )

    assert "transferências pix" in response["acronym_lookup"]["query"].lower()
    assert any(item["acronym"] == "PIX" for item in response["acronym_lookup"]["results"])


def test_collects_story_from_conversation_history(tmp_path):
    tool = _build_tool(
        tmp_path,
        [
            {
                "acronym": "DICT",
                "meaning": "Diretório de Identificadores",
                "keywords": ["dict"],
            }
        ],
    )

    state = {
        "conversation": {
            "history": [
                {"parts": [{"text": "Olá"}]},
                {
                    "parts": [
                        {
                            "text": (
                                "Como cliente corporativo do banco,\n"
                                "Quero registrar chaves PIX no DICT com segurança,\n"
                                "Para automatizar transferências recorrentes.\n"
                                "Critérios de Aceite: Validação DICT e auditoria completa."
                            )
                        }
                    ]
                },
            ]
        }
    }

    response = tool.search_acronyms(state=state)

    query = response["acronym_lookup"]["query"].lower()
    assert "cliente corporativo" in query
    assert any(item["acronym"] == "DICT" for item in response["acronym_lookup"]["results"])


def test_collects_short_story_from_conversation_history(tmp_path):
    tool = _build_tool(
        tmp_path,
        [
            {
                "acronym": "API",
                "meaning": "Gateway de APIs",
                "keywords": ["api"],
            }
        ],
    )

    state = {
        "conversation": {
            "history": [
                {"parts": [{"text": "Olá"}]},
                {"parts": [{"text": "Quero uma API"}]},
            ]
        }
    }

    response = tool.search_acronyms(state=state)

    query = response["acronym_lookup"]["query"].lower()
    assert "api" in query
    assert any(item["acronym"] == "API" for item in response["acronym_lookup"]["results"])


def test_max_results_accepts_string_values(tmp_path):
    tool = _build_tool(
        tmp_path,
        [
            {
                "acronym": "BIO1",
                "meaning": "Biometria Fase 1",
                "keywords": ["biometria", "pix"],
            },
            {
                "acronym": "BIO2",
                "meaning": "Biometria Fase 2",
                "keywords": ["biometria", "pix"],
            },
            {
                "acronym": "BIO3",
                "meaning": "Biometria Fase 3",
                "keywords": ["biometria", "pix"],
            },
        ],
    )

    response = tool.search_acronyms(text="Integração de biometria com PIX", max_results="2")

    assert [item["acronym"] for item in response["acronym_lookup"]["results"]] == ["BIO1", "BIO2"]


def test_max_results_falls_back_to_metadata_when_invalid(tmp_path):
    database_path = tmp_path / "acronyms.json"
    database_path.write_text(
        json.dumps(
            [
                {
                    "acronym": "BIOA",
                    "meaning": "Biometria Alpha",
                    "keywords": ["biometria"],
                },
                {
                    "acronym": "BIOB",
                    "meaning": "Biometria Beta",
                    "keywords": ["biometria"],
                },
            ]
        ),
        encoding="utf-8",
    )

    tool = Tool(
        metadata={
            "database": str(database_path),
            "max_results": "1",
        }
    )

    response = tool.search_acronyms(text="Projeto de biometria facial", max_results="invalid")

    assert [item["acronym"] for item in response["acronym_lookup"]["results"]] == ["BIOA"]
