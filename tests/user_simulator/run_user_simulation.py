#!/usr/bin/env python3
"""Simulador de usuário para validar o agente Diagramador com Google ADK real."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


try:
    from dotenv import load_dotenv  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - dependency optional em testes offline
    load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def _without_repo_google_package():
    """Temporariamente remove o pacote local ``google`` do ``sys.path``.

    O repositório contém stubs mínimos para ``google.adk`` e ``google.genai``
    que são úteis nos testes offline, mas atrapalham quando queremos carregar
    os pacotes oficiais instalados via ``pip``. Para garantir que as versões
    reais sejam utilizadas, removemos entradas que apontam para o repositório
    (incluindo ``''``) e limpamos módulos previamente importados antes de
    executar os imports críticos. Ao final, restauramos ``sys.path`` sem
    efeitos colaterais.
    """

    original_sys_path = list(sys.path)

    filtered_sys_path = []
    for entry in original_sys_path:
        try:
            resolved = Path(entry or ".").resolve()
        except Exception:
            filtered_sys_path.append(entry)
            continue
        if resolved == REPO_ROOT:
            continue
        filtered_sys_path.append(entry)

    sys.path[:] = filtered_sys_path

    # Remove módulos carregados a partir do repositório para permitir que os
    # pacotes oficiais sejam importados em seguida.
    for name, module in list(sys.modules.items()):
        if not (name == "google" or name.startswith("google.")):
            continue
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        try:
            module_path = Path(module_file).resolve()
        except Exception:
            continue
        if REPO_ROOT in module_path.parents or module_path == REPO_ROOT:
            sys.modules.pop(name, None)

    try:
        yield
    finally:
        sys.path[:] = original_sys_path

with _without_repo_google_package():
    try:
        from google.adk.runners import InMemoryRunner  # type: ignore[attr-defined]
        from google.adk.agents.run_config import RunConfig  # type: ignore[attr-defined]
    except ModuleNotFoundError as exc:  # pragma: no cover - executado apenas em ambiente real
        raise SystemExit(
            "Este script exige os pacotes oficiais 'google-adk' e 'google-genai'. "
            "Instale-os com 'pip install -r tests/user_simulator/requirements.txt'."
        ) from exc
    except Exception as exc:  # pragma: no cover - executado apenas em ambiente real
        raise SystemExit(
            "Falha ao carregar Google ADK. Verifique a instalação e as dependências."
        ) from exc

with _without_repo_google_package():
    try:
        from google.genai import errors as genai_errors  # type: ignore[attr-defined]
        from google.genai import types  # type: ignore[attr-defined]
    except ModuleNotFoundError as exc:  # pragma: no cover - executado apenas em ambiente real
        raise SystemExit(
            "O pacote 'google-genai' é obrigatório. Instale-o com 'pip install -r "
            "tests/user_simulator/requirements.txt'."
        ) from exc
    except Exception as exc:  # pragma: no cover - executado apenas em ambiente real
        raise SystemExit("Falha ao carregar google-genai. Verifique a instalação.") from exc
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.diagramador.agent import get_root_agent  # noqa: E402
from agents.diagramador.prompt import ORCHESTRATOR_PROMPT  # noqa: E402


def _load_environment() -> None:
    """Carrega variáveis de ambiente definidas em arquivos ``.env``."""

    if load_dotenv is None:
        return

    env_candidates = [REPO_ROOT / ".env", REPO_ROOT / "tests" / "user_simulator" / ".env"]
    for env_file in env_candidates:
        if env_file.exists():
            load_dotenv(env_file, override=False)


def _ensure_credentials() -> None:
    """Valida que credenciais necessárias estão configuradas."""

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GENAI_API_KEY")
    project = os.getenv("VERTEXAI_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("VERTEXAI_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION")

    if api_key or (project and location):
        return

    raise SystemExit(
        "Credenciais não configuradas. Defina GOOGLE_API_KEY ou as variáveis "
        "VERTEXAI_PROJECT e VERTEXAI_LOCATION (ou GOOGLE_CLOUD_PROJECT/GOOGLE_CLOUD_LOCATION)."
    )


def _utcnow() -> datetime:
    """Retorna o horário atual em UTC com timezone explícito."""

    return datetime.now(timezone.utc)


_load_environment()


@dataclass
class StepDefinition:
    name: str
    type: str
    prompt_template: str | None = None
    message: str | None = None
    expect: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StepDefinition":
        return cls(
            name=payload.get("name", "step"),
            type=payload.get("type", "user_history"),
            prompt_template=payload.get("prompt_template"),
            message=payload.get("message"),
            expect=payload.get("expect"),
        )


@dataclass
class FlowDefinition:
    case_id: str
    description: str
    user_id: str
    session_id: str
    steps: list[StepDefinition] = field(default_factory=list)
    expected_outcomes: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "FlowDefinition":
        payload = json.loads(path.read_text(encoding="utf-8"))
        steps = [StepDefinition.from_dict(item) for item in payload.get("steps", [])]
        return cls(
            case_id=payload.get("case_id", path.parent.name),
            description=payload.get("description", ""),
            user_id=payload.get("user_id", "sim-user"),
            session_id=payload.get("session_id", f"session-{path.parent.name}"),
            steps=steps,
            expected_outcomes=list(payload.get("expected_outcomes", [])),
        )


@dataclass
class ArtifactRecord:
    filename: str
    mime_type: str | None
    version: int
    absolute_path: Path


@dataclass
class EventRecord:
    index: int
    step: str
    author: str
    summary: str
    event_payload: dict[str, Any]
    session_state_path: Path
    artifacts: list[ArtifactRecord] = field(default_factory=list)


def _sanitize_token(value: str, fallback: str = "token") -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    text = text.strip("-")
    return text or fallback


async def _create_session(runner: InMemoryRunner, user_id: str, session_id: str):
    return await runner.session_service.create_session(
        app_name=runner.app_name, user_id=user_id, session_id=session_id
    )


async def _fetch_session_snapshot(
    runner: InMemoryRunner, user_id: str, session_id: str
):
    return await runner.session_service.get_session(
        app_name=runner.app_name, user_id=user_id, session_id=session_id
    )


async def _load_artifact(
    runner: InMemoryRunner, user_id: str, session_id: str, filename: str, version: int
):
    return await runner.artifact_service.load_artifact(  # type: ignore[attr-defined]
        app_name=runner.app_name,
        user_id=user_id,
        session_id=session_id,
        filename=filename,
        version=version,
    )


def _ensure_bytes(data: Any) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    raise TypeError(f"Não foi possível serializar o artefato do tipo {type(data)!r}")


def _extract_text_from_event(event: dict[str, Any]) -> str:
    parts = event.get("content", {}).get("parts", []) if event.get("content") else []
    texts: list[str] = []
    for part in parts:
        text = part.get("text")
        if text:
            texts.append(str(text))
    return "\n".join(texts)


def _build_user_message(step: StepDefinition, user_history: str) -> str:
    if step.type == "user_history":
        template = step.prompt_template or "{user_history}"
        return template.format(user_history=user_history)
    if step.message:
        return step.message
    raise ValueError(f"Step {step.name} não possui mensagem definida.")


def _copy_static_assets(case_dir: Path, run_dir: Path) -> None:
    (run_dir / "Agent_diagramador_prompt.txt").write_text(
        ORCHESTRATOR_PROMPT, encoding="utf-8"
    )
    # Copia a história e o fluxo para referência rápida.
    for filename in ("user_history.txt", "flow.json"):
        source = case_dir / filename
        if source.exists():
            (run_dir / filename).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def run_simulation(case_dir: Path, flow: FlowDefinition, *, run_name: str, dry_run: bool) -> Path:
    timestamp = _utcnow().strftime("%Y%m%d-%H%M%S")
    run_identifier = f"{timestamp}-{run_name}" if run_name else timestamp
    run_dir = case_dir / "results" / run_identifier
    artefacts_dir = run_dir / "artefacts"
    artefacts_dir.mkdir(parents=True, exist_ok=True)

    _copy_static_assets(case_dir, run_dir)

    session_log_path = run_dir / "session.log"
    flow_result_path = run_dir / "flow_result.json"
    summary_path = run_dir / "structured_summary.md"

    if dry_run:
        session_log_path.write_text(
            "Simulação executada em modo dry-run. Nenhuma chamada ao modelo foi realizada.\n",
            encoding="utf-8",
        )
        flow_result_path.write_text(
            json.dumps(
                {
                    "case_id": flow.case_id,
                    "description": flow.description,
                    "expected_outcomes": flow.expected_outcomes,
                    "dry_run": True,
                    "timestamp": _utcnow().isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        summary_path.write_text(
            "# Dry-run\n\nNenhuma interação com a LLM foi realizada.",
            encoding="utf-8",
        )
        try:
            (case_dir / "session.log").write_text(
                session_log_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
        except Exception:
            pass
        return run_dir

    user_history = (case_dir / "user_history.txt").read_text(encoding="utf-8")

    _ensure_credentials()

    agent = get_root_agent()
    runner = InMemoryRunner(agent=agent)

    session = asyncio.run(
        _create_session(runner, user_id=flow.user_id, session_id=flow.session_id)
    )

    run_config = RunConfig()

    events: list[EventRecord] = []
    final_agent_text: list[str] = []
    model_error: dict[str, Any] | None = None

    with session_log_path.open("w", encoding="utf-8") as session_log:
        for step in flow.steps:
            user_message = _build_user_message(step, user_history)
            content = types.Content(
                role="user",
                parts=[types.Part(text=user_message)],
            )
            session_log.write(
                json.dumps(
                    {
                        "timestamp": _utcnow().isoformat(),
                        "step": step.name,
                        "event_type": "user_message",
                        "payload": user_message,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

            try:
                for event in runner.run(
                    user_id=session.user_id,
                    session_id=session.id,
                    new_message=content,
                    run_config=run_config,
                ):
                    event_payload = event.model_dump(mode="json")
                    session_log.write(
                        json.dumps(
                            {
                                "timestamp": _utcnow().isoformat(),
                                "step": step.name,
                                "event_type": "agent_event",
                                "payload": event_payload,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

                    snapshot = asyncio.run(
                        _fetch_session_snapshot(
                            runner, user_id=session.user_id, session_id=session.id
                        )
                    )
                    state_filename = _make_state_filename(
                        event_index=len(events) + 1, event=event
                    )
                    state_path = run_dir / state_filename

                    artifacts_records = _persist_artifacts(
                        runner,
                        artefacts_dir,
                        event,
                        user_id=session.user_id,
                        session_id=session.id,
                    )

                    record = EventRecord(
                        index=len(events) + 1,
                        step=step.name,
                        author=event.author,
                        summary=_extract_text_from_event(event_payload),
                        event_payload=event_payload,
                        session_state_path=state_path,
                        artifacts=artifacts_records,
                    )
                    events.append(record)

                    _write_session_state_snapshot(
                        state_path=state_path,
                        snapshot=snapshot,
                        event_payload=event_payload,
                        artifacts=artifacts_records,
                    )

                    if event.author != "user":
                        text = _extract_text_from_event(event_payload)
                        if text:
                            final_agent_text.append(text)
            except genai_errors.ClientError as exc:  # pragma: no cover - requer ambiente real
                model_error = _serialize_model_error(exc)
                session_log.write(
                    json.dumps(
                        {
                            "timestamp": _utcnow().isoformat(),
                            "step": step.name,
                            "event_type": "model_error",
                            "payload": model_error,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                session_log.flush()
                break

        if model_error:
            break

    flow_result = {
        "case_id": flow.case_id,
        "description": flow.description,
        "expected_outcomes": flow.expected_outcomes,
        "events_processed": len(events),
        "steps": [step.name for step in flow.steps],
        "artifacts_saved": [
            {
                "index": record.index,
                "files": [artifact.filename for artifact in record.artifacts],
            }
            for record in events
            if record.artifacts
        ],
    }

    if model_error:
        flow_result["model_error"] = model_error

    flow_result_path.write_text(
        json.dumps(flow_result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if final_agent_text:
        summary_body = "\n\n".join(final_agent_text[-2:])
        summary_text = f"# Detalhamento estruturado e sugestões\n\n{summary_body}"
    elif model_error:
        code = model_error.get("status_code", "desconhecido")
        message = model_error.get("message", "Sem detalhes fornecidos pelo provedor.")
        suggestion = model_error.get("suggestion")
        summary_lines = [
            "# Detalhamento estruturado e sugestões",
            "",
            "A simulação foi interrompida devido a um erro ao acionar a LLM.",
            "",
            f"- Código: {code}",
            f"- Mensagem: {message}",
        ]
        if suggestion:
            summary_lines.extend(["", f"Sugestão: {suggestion}"])
        summary_text = "\n".join(summary_lines)
    else:
        summary_text = (
            "# Detalhamento estruturado e sugestões\n\n"
            "Nenhuma resposta textual do agente foi capturada. Verifique os logs em "
            "session.log para detalhes."
        )
    summary_path.write_text(summary_text, encoding="utf-8")

    asyncio.run(runner.close())

    # Atualiza o log consolidado na raiz do cenário para facilitar inspeção rápida.
    try:
        (case_dir / "session.log").write_text(
            session_log_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    except Exception:
        # O arquivo na raiz é apenas uma conveniência; falhas aqui não devem
        # invalidar a execução da simulação.
        pass

    return run_dir


def _make_state_filename(*, event_index: int, event: Any) -> str:
    agent_token = _sanitize_token(getattr(event, "author", "agent"), "agent")
    tool_name = "message"
    interaction = "response"

    calls = event.get_function_calls() if hasattr(event, "get_function_calls") else []
    responses = (
        event.get_function_responses()
        if hasattr(event, "get_function_responses")
        else []
    )
    if calls:
        tool_name = calls[0].name or "function_call"
        interaction = "call"
    elif responses:
        tool_name = responses[0].name or "function_response"
        interaction = "response"
    elif agent_token == "user":
        tool_name = "user_message"
        interaction = "request"

    return (
        f"{event_index:03d}-{_sanitize_token(agent_token)}-"
        f"{_sanitize_token(tool_name)}-{interaction}_session_state.json"
    )


def _write_session_state_snapshot(
    *,
    state_path: Path,
    snapshot: Any,
    event_payload: dict[str, Any],
    artifacts: Iterable[ArtifactRecord],
) -> None:
    payload = {
        "timestamp": _utcnow().isoformat(),
        "session": snapshot.model_dump(mode="json") if hasattr(snapshot, "model_dump") else {},
        "event": event_payload,
        "artifacts": [
            {
                "filename": artifact.filename,
                "version": artifact.version,
                "mime_type": artifact.mime_type,
                "absolute_path": str(artifact.absolute_path),
            }
            for artifact in artifacts
        ],
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _persist_artifacts(
    runner: InMemoryRunner,
    artefacts_dir: Path,
    event: Any,
    *,
    user_id: str,
    session_id: str,
) -> list[ArtifactRecord]:
    artifact_delta = {}
    if getattr(event, "actions", None):
        artifact_delta = getattr(event.actions, "artifact_delta", {}) or {}

    records: list[ArtifactRecord] = []
    if not artifact_delta:
        return records

    for filename, version in artifact_delta.items():
        part = asyncio.run(
            _load_artifact(
                runner,
                user_id=user_id,
                session_id=session_id,
                filename=filename,
                version=version,
            )
        )
        if part is None:
            continue
        mime_type = None
        raw_bytes: bytes | None = None

        if part.inline_data is not None:
            mime_type = part.inline_data.mime_type
            raw_bytes = _ensure_bytes(part.inline_data.data)
        elif part.text is not None:
            mime_type = "text/plain"
            raw_bytes = part.text.encode("utf-8")
        elif part.file_data is not None:
            mime_type = part.file_data.mime_type or "application/octet-stream"
            file_data_bytes = getattr(part.file_data, "data", None)
            raw_bytes = _ensure_bytes(file_data_bytes) if file_data_bytes else None
        else:
            raw_bytes = None

        suffix = _guess_extension(mime_type, filename)
        target_path = artefacts_dir / f"{_sanitize_token(filename)}-v{version}{suffix}"
        if raw_bytes:
            target_path.write_bytes(raw_bytes)
        else:
            target_path.write_text(json.dumps(part.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")

        records.append(
            ArtifactRecord(
                filename=filename,
                mime_type=mime_type,
                version=version,
                absolute_path=target_path,
            )
        )

    return records


def _guess_extension(mime_type: str | None, filename: str) -> str:
    if not mime_type:
        return ".json"
    if "svg" in mime_type:
        return ".svg"
    if "png" in mime_type:
        return ".png"
    if "json" in mime_type:
        return ".json"
    if "xml" in mime_type:
        return ".xml"
    if "html" in mime_type:
        return ".html"
    if "pdf" in mime_type:
        return ".pdf"
    if filename.lower().endswith(".json"):
        return ".json"
    return ".bin"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simula uma conversa completa com o agente Diagramador usando o Google ADK."
    )
    parser.add_argument(
        "--case",
        default="pix_container",
        help="Identificador do caso em tests/user_simulator/test-cases/",
    )
    parser.add_argument(
        "--run-name",
        default="",
        help="Nome opcional para o diretório de resultados (padrão: timestamp UTC).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Não aciona a LLM; apenas prepara a estrutura de diretórios e arquivos.",
    )
    return parser.parse_args(argv)


def _serialize_model_error(exc: Exception) -> dict[str, Any]:
    """Converte erros do modelo em um dicionário serializável."""

    payload: dict[str, Any] = {
        "type": type(exc).__name__,
        "message": str(exc),
    }

    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status_code is not None:
        payload["status_code"] = status_code

    reason = getattr(exc, "reason", None)
    if reason:
        payload["reason"] = reason

    if status_code == 429:
        payload["suggestion"] = (
            "A chamada foi recusada por limite de uso (código 429). Aguarde alguns minutos "
            "e tente novamente ou reduza o volume de requisições simultâneas."
        )

    return payload


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    base_dir = Path(__file__).resolve().parent
    case_dir = base_dir / "test-cases" / args.case
    if not case_dir.exists():
        raise SystemExit(f"Caso '{args.case}' não encontrado em {case_dir.parent}.")

    flow = FlowDefinition.load(case_dir / "flow.json")
    run_dir = run_simulation(case_dir, flow, run_name=args.run_name, dry_run=args.dry_run)
    print(f"Simulação concluída. Resultados em: {run_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover - execução direta
    raise SystemExit(main())
