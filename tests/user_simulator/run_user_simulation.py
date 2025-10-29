#!/usr/bin/env python3
"""Simulador de usuário para validar o agente Diagramador com Google ADK real."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import shutil
import sys
import textwrap
from collections.abc import MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence

from binascii import Error as BinasciiError


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

with _without_repo_google_package():
    try:
        from google import genai as genai_module  # type: ignore[attr-defined]
    except ModuleNotFoundError:
        genai_module = None
    except Exception:
        genai_module = None
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



def _emit_cli(message: str = "") -> None:
    """Imprime mensagens no CLI garantindo flush imediato."""

    print(message, flush=True)


def _shorten_cli_preview(text: str, *, width: int = 120) -> str:
    """Produz um resumo em linha única para exibição no terminal."""

    normalized = " ".join(text.split())
    if not normalized:
        return "[sem texto]"
    try:
        return textwrap.shorten(normalized, width=width, placeholder="…")
    except Exception:
        return normalized[: max(1, width - 1)] + ("…" if len(normalized) > width else "")


DATA_URI_PATTERN = re.compile(r"data:(?P<mime>[-\w.+/]+);base64,(?P<data>[A-Za-z0-9+/=_-]+)")


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
class ToolInteractionRecord:
    """Representa o uso de uma ferramenta durante um evento do agente."""

    name: str
    direction: Literal["call", "response"]
    detail: str


@dataclass
class EventRecord:
    index: int
    step: str
    author: str
    summary: str
    event_payload: dict[str, Any]
    session_state_path: Path
    tools: list[ToolInteractionRecord] = field(default_factory=list)
    artifacts: list[ArtifactRecord] = field(default_factory=list)


@dataclass
class ExpectationReport:
    step: str
    expected: str | None
    responses: list[str]
    evaluation: dict[str, Any] | None = None
    error: str | None = None


_EVALUATION_CLIENT: Any | None = None


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


def _scrub_thought_signature(payload: Any) -> Any:
    """Remove a propriedade ``thought_signature`` de estruturas arbitrárias."""

    if isinstance(payload, dict):
        return {
            key: _scrub_thought_signature(value)
            for key, value in payload.items()
            if key != "thought_signature"
        }
    if isinstance(payload, list):
        return [_scrub_thought_signature(item) for item in payload]
    return payload


def _truncate_json(value: Any, *, limit: int = 200) -> str:
    """Converte um payload em JSON compacto limitado a ``limit`` caracteres."""

    try:
        text = json.dumps(value, ensure_ascii=False)
    except TypeError:
        text = str(value)

    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _extract_tool_interactions(
    event: Any, sanitized_payload: dict[str, Any]
) -> list[ToolInteractionRecord]:
    """Extrai interações de ferramentas presentes no evento."""

    interactions: list[ToolInteractionRecord] = []

    def _append_interaction(name: str | None, direction: Literal["call", "response"], detail: Any):
        if not name:
            name = "function_call" if direction == "call" else "function_response"
        scrubbed_detail = _scrub_thought_signature(detail)
        interactions.append(
            ToolInteractionRecord(
                name=str(name),
                direction=direction,
                detail=_truncate_json(scrubbed_detail, limit=240),
            )
        )

    try:
        if hasattr(event, "get_function_calls"):
            for call in event.get_function_calls() or []:
                _append_interaction(
                    getattr(call, "name", None),
                    "call",
                    getattr(call, "args", None),
                )
        if hasattr(event, "get_function_responses"):
            for response in event.get_function_responses() or []:
                _append_interaction(
                    getattr(response, "name", None),
                    "response",
                    getattr(response, "response", None),
                )
    except Exception:
        # fallback to payload structure when ADK helpers não estão disponíveis
        pass

    if interactions:
        return interactions

    # Fallback baseado no payload serializado em caso de objetos simples.
    parts = sanitized_payload.get("content", {}).get("parts", [])
    for part in parts if isinstance(parts, Sequence) else []:
        if isinstance(part, MutableMapping):
            if part.get("function_call"):
                call = part["function_call"]
                _append_interaction(
                    call.get("name") if isinstance(call, MutableMapping) else None,
                    "call",
                    call.get("args") if isinstance(call, MutableMapping) else None,
                )
            if part.get("function_response"):
                response = part["function_response"]
                _append_interaction(
                    response.get("name") if isinstance(response, MutableMapping) else None,
                    "response",
                    response.get("response") if isinstance(response, MutableMapping) else None,
                )

    return interactions


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


def _write_alias_notice(alias_dir: Path, target_dir: Path) -> None:
    alias_dir.mkdir(parents=True, exist_ok=True)
    notice_path = alias_dir / "REDIRECT.txt"
    try:
        relative_target = os.path.relpath(target_dir, alias_dir)
    except ValueError:
        relative_target = str(target_dir)
    notice_message = textwrap.dedent(
        f"""
        Esta pasta é mantida apenas por compatibilidade.

        Todos os artefatos gerados na execução atual são gravados em:
            {target_dir}

        Caso esteja procurando os arquivos manualmente, utilize a pasta acima
        (relativo a este diretório: {relative_target}).
        """
    ).strip()
    notice_path.write_text(notice_message + "\n", encoding="utf-8")


def _prepare_artifact_alias(alias_dir: Path, target_dir: Path) -> None:
    target_resolved = target_dir.resolve()
    if alias_dir.exists():
        if alias_dir.is_symlink():
            try:
                if alias_dir.resolve() == target_resolved:
                    return
            except OSError:
                alias_dir.unlink(missing_ok=True)
        else:
            if alias_dir.is_dir():
                for item in list(alias_dir.iterdir()):
                    target = target_dir / item.name
                    if target.exists():
                        continue
                    try:
                        item.replace(target)
                    except OSError:
                        continue
            try:
                if alias_dir.is_dir():
                    shutil.rmtree(alias_dir)
                else:
                    alias_dir.unlink()
            except OSError:
                _write_alias_notice(alias_dir, target_dir)
                return
    alias_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        alias_dir.symlink_to(target_resolved, target_is_directory=True)
    except Exception:
        _write_alias_notice(alias_dir, target_dir)


def run_simulation(case_dir: Path, flow: FlowDefinition, *, run_name: str, dry_run: bool) -> Path:
    timestamp = _utcnow().strftime("%Y%m%d-%H%M%S")
    run_identifier = f"{timestamp}-{run_name}" if run_name else timestamp
    run_dir = case_dir / "results" / run_identifier
    artefacts_dir = run_dir / "artefacts"
    artefacts_dir.mkdir(parents=True, exist_ok=True)

    _prepare_artifact_alias(run_dir / "artfacts", artefacts_dir)
    _prepare_artifact_alias(run_dir / "artifacts", artefacts_dir)

    _copy_static_assets(case_dir, run_dir)

    session_log_path = run_dir / "session.log"
    flow_result_path = run_dir / "flow_result.json"
    summary_path = run_dir / "structured_summary.md"

    _emit_cli(f"📁 Resultados serão gravados em: {run_dir}")

    if dry_run:
        _emit_cli("⚙️ Modo dry-run ativado. Nenhuma chamada ao modelo será executada.")
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
        _emit_cli("✅ Dry-run concluído.")
        return run_dir

    user_history = (case_dir / "user_history.txt").read_text(encoding="utf-8")

    _ensure_credentials()

    agent = get_root_agent()
    runner = InMemoryRunner(agent=agent)

    _emit_cli("🚀 Iniciando simulação real com o agente Diagramador…")

    session = asyncio.run(
        _create_session(runner, user_id=flow.user_id, session_id=flow.session_id)
    )

    run_config = RunConfig()

    events: list[EventRecord] = []
    expectation_reports: list[ExpectationReport] = []
    final_agent_text: list[str] = []
    model_error: dict[str, Any] | None = None

    with session_log_path.open("w", encoding="utf-8") as session_log:
        session_log.write("# Log de sessão do usuário com o agente Diagramador\n\n")
        for step in flow.steps:
            _emit_cli(f"➡️ Passo '{step.name}': enviando mensagem ao agente.")
            user_message = _build_user_message(step, user_history)
            content = types.Content(
                role="user",
                parts=[types.Part(text=user_message)],
            )
            step_timestamp = _utcnow().isoformat()
            session_log.write(
                f"## Passo: {step.name}\n"
                f"Horário: {step_timestamp}\n\n"
                "**Usuário**\n"
                "--------------\n"
                f"{user_message}\n\n"
            )
            _emit_cli(f"   ↳ Usuário: {_shorten_cli_preview(user_message)}")

            abort_step = False
            agent_responses: list[str] = []

            try:
                for event in runner.run(
                    user_id=session.user_id,
                    session_id=session.id,
                    new_message=content,
                    run_config=run_config,
                ):
                    event_payload = event.model_dump(mode="json")
                    sanitized_payload = _scrub_thought_signature(event_payload)
                    event_index = len(events) + 1
                    (
                        sanitized_payload,
                        inline_artifacts,
                        inline_notes,
                    ) = _extract_inline_artifacts_from_payload(
                        sanitized_payload,
                        artefacts_dir=artefacts_dir,
                        event_index=event_index,
                        run_dir=run_dir,
                    )
                    event_timestamp = _utcnow().isoformat()
                    tool_interactions = _extract_tool_interactions(event, sanitized_payload)

                    session_log.write(
                        "**Agente Diagramador**\n"
                        "----------------------\n"
                        f"Horário: {event_timestamp}\n"
                        f"{_extract_text_from_event(sanitized_payload) or '[sem texto disponível]'}\n\n"
                    )
                    if tool_interactions:
                        session_log.write("**Uso de ferramentas**\n")
                        session_log.write("---------------------\n")
                        for interaction in tool_interactions:
                            action = "chamada" if interaction.direction == "call" else "resposta"
                            session_log.write(
                                f"- {interaction.name} ({action}): {interaction.detail}\n"
                            )
                        session_log.write("\n")
                    session_log.write(
                        "```json\n"
                        f"{json.dumps(sanitized_payload, ensure_ascii=False, indent=2)}\n"
                        "```\n\n"
                    )
                    if inline_notes:
                        session_log.write("**Artefatos extraídos do payload**\n")
                        session_log.write("--------------------------------\n")
                        for note in inline_notes:
                            session_log.write(f"- {note}\n")
                        session_log.write("\n")
                    preview = _shorten_cli_preview(
                        _extract_text_from_event(sanitized_payload)
                    )
                    author = getattr(event, "author", "agent") or "agent"
                    _emit_cli(f"   ↳ {author}: {preview}")
                    if tool_interactions:
                        for interaction in tool_interactions:
                            action = "chamada" if interaction.direction == "call" else "resposta"
                            _emit_cli(
                                f"      ↳ ferramenta {interaction.name} ({action}): {interaction.detail}"
                            )

                    snapshot = asyncio.run(
                        _fetch_session_snapshot(
                            runner, user_id=session.user_id, session_id=session.id
                        )
                    )
                    state_filename = _make_state_filename(
                        event_index=event_index, event=event
                    )
                    state_path = run_dir / state_filename

                    artifacts_records = _persist_artifacts(
                        runner,
                        artefacts_dir,
                        event,
                        user_id=session.user_id,
                        session_id=session.id,
                    )
                    if inline_artifacts:
                        artifacts_records.extend(inline_artifacts)

                    if artifacts_records:
                        session_log.write("**Artefatos armazenados**\n")
                        session_log.write("------------------------\n")
                        for record in artifacts_records:
                            rel_path = record.absolute_path.relative_to(run_dir)
                            session_log.write(
                                f"- {record.filename} (v{record.version}, {record.mime_type or 'mime desconhecido'}) → ./{rel_path}\n"
                            )
                        session_log.write("\n")
                    if inline_notes:
                        for note in inline_notes:
                            _emit_cli(f"      ↳ artefato extraído: {note}")

                    record = EventRecord(
                        index=event_index,
                        step=step.name,
                        author=event.author,
                        summary=_extract_text_from_event(sanitized_payload),
                        event_payload=sanitized_payload,
                        session_state_path=state_path,
                        tools=list(tool_interactions),
                        artifacts=artifacts_records,
                    )
                    events.append(record)

                    _write_session_state_snapshot(
                        state_path=state_path,
                        snapshot=snapshot,
                        event_payload=sanitized_payload,
                        artifacts=artifacts_records,
                    )

                    if event.author != "user":
                        text = _extract_text_from_event(sanitized_payload)
                        if text:
                            final_agent_text.append(text)
                            agent_responses.append(text)
                    if artifacts_records:
                        for record_artifact in artifacts_records:
                            _emit_cli(
                                "      ↳ artefato salvo: "
                                f"{record_artifact.absolute_path.as_uri()}"
                            )
            except genai_errors.ClientError as exc:  # pragma: no cover - requer ambiente real
                model_error = _serialize_model_error(exc)
                session_log.write(
                    "**Erro do Modelo**\n"
                    "------------------\n"
                    f"Horário: {_utcnow().isoformat()}\n"
                    f"{json.dumps(model_error, ensure_ascii=False, indent=2)}\n\n"
                )
                session_log.flush()
                abort_step = True
                _emit_cli("❌ Erro retornado pelo provedor durante o passo. Consulte session.log.")

            expected_text = step.expect or "Nenhum resultado esperado definido."
            _emit_cli(f"🧪 Avaliando respostas do passo '{step.name}'…")
            analysis_text, expectation_report, raw_evaluation_json = _analyze_expectation(
                runner,
                step,
                expected=step.expect,
                responses=agent_responses,
                model_error=model_error,
            )
            session_log.write(
                "**Esperado**\n"
                "-----------\n"
                f"{expected_text}\n\n"
                "**Resultado**\n"
                "------------\n"
                f"{analysis_text}\n\n"
            )
            if raw_evaluation_json:
                session_log.write("```json\n")
                session_log.write(f"{raw_evaluation_json}\n")
                session_log.write("```\n\n")
            session_log.write("---\n\n")

            if expectation_report and expectation_report.evaluation:
                verdict = expectation_report.evaluation.get("verdict") or "N/D"
                _emit_cli(f"🧾 Veredito do passo '{step.name}': {verdict}")
            else:
                _emit_cli(
                    f"📝 Resultado do passo '{step.name}': {_shorten_cli_preview(analysis_text)}"
                )

            if expectation_report:
                expectation_reports.append(expectation_report)

            if abort_step:
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

    if expectation_reports:
        flow_result["expectation_reports"] = [
            {
                "step": report.step,
                "expected": report.expected,
                "responses": report.responses,
                "evaluation": report.evaluation,
                "error": report.error,
            }
            for report in expectation_reports
        ]

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

    results_md_path = run_dir / "RESULTS.md"
    results_md_path.write_text(
        _generate_results_markdown(
            flow=flow,
            run_dir=run_dir,
            events=events,
            expectation_reports=expectation_reports,
            flow_result=flow_result,
            model_error=model_error,
        ),
        encoding="utf-8",
    )

    asyncio.run(runner.close())

    _emit_cli("🏁 Simulação concluída.")

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
    session_payload: dict[str, Any] = {}
    if hasattr(snapshot, "model_dump"):
        try:
            session_payload = snapshot.model_dump(mode="json")  # type: ignore[call-arg]
        except TypeError:
            session_payload = snapshot.model_dump()  # type: ignore[misc]
    elif isinstance(snapshot, MutableMapping):
        session_payload = dict(snapshot)

    session_payload = _scrub_thought_signature(session_payload)

    payload = {
        "timestamp": _utcnow().isoformat(),
        "session": session_payload,
        "event": _scrub_thought_signature(event_payload),
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
        serialized_text: str | None = None
        if raw_bytes:
            target_path.write_bytes(raw_bytes)
        else:
            try:
                model_payload = part.model_dump(mode="json")  # type: ignore[call-arg]
            except TypeError:
                model_payload = part.model_dump()  # type: ignore[misc]
            serialized_text = json.dumps(
                _scrub_thought_signature(model_payload), ensure_ascii=False, indent=2
            )
            target_path.write_text(serialized_text, encoding="utf-8")

        records.append(
            ArtifactRecord(
                filename=filename,
                mime_type=mime_type,
                version=version,
                absolute_path=target_path,
            )
        )

    return records
def _store_inline_bytes(
    *,
    artefacts_dir: Path,
    event_index: int,
    counter: int,
    mime_type: str | None,
    hint: str,
    data: bytes,
) -> tuple[ArtifactRecord, Path]:
    sanitized_hint = _sanitize_token(hint or f"inline-{counter:02d}", fallback=f"inline-{counter:02d}")
    suffix = _guess_extension(mime_type, sanitized_hint)
    filename = f"{event_index:03d}-{sanitized_hint}-inline{counter}{suffix}"
    target_path = artefacts_dir / filename
    target_path.write_bytes(data)

    record = ArtifactRecord(
        filename=filename,
        mime_type=mime_type,
        version=0,
        absolute_path=target_path,
    )
    return record, target_path


def _extract_inline_artifacts_from_payload(
    payload: dict[str, Any],
    *,
    artefacts_dir: Path,
    event_index: int,
    run_dir: Path,
) -> tuple[dict[str, Any], list[ArtifactRecord], list[str]]:
    counter = 0
    extracted: list[ArtifactRecord] = []
    notes: list[str] = []

    def _register_artifact(data_bytes: bytes, mime_type: str | None, hint: str) -> Path:
        nonlocal counter
        counter += 1
        record, saved_path = _store_inline_bytes(
            artefacts_dir=artefacts_dir,
            event_index=event_index,
            counter=counter,
            mime_type=mime_type,
            hint=hint,
            data=data_bytes,
        )
        extracted.append(record)
        rel_path = saved_path.relative_to(run_dir)
        notes.append(
            f"{record.filename} ({mime_type or 'mime desconhecido'}) → {saved_path.as_uri()} [./{rel_path}]"
        )
        return saved_path

    def _process(node: Any, hint: str) -> Any:
        if isinstance(node, dict):
            inline_data = node.get("inline_data")
            if isinstance(inline_data, MutableMapping):
                raw_data = inline_data.pop("data", None)
                mime_type = inline_data.get("mime_type")
                if isinstance(raw_data, str) and raw_data.strip():
                    try:
                        data_bytes = base64.b64decode(raw_data, validate=False)
                    except (BinasciiError, ValueError):
                        data_bytes = b""
                    if data_bytes:
                        saved_path = _register_artifact(data_bytes, mime_type, hint)
                        inline_data["uri"] = saved_path.as_uri()
                        inline_data["relative_path"] = str(saved_path.relative_to(run_dir))
                    else:
                        inline_data["data_truncated"] = True
            file_data = node.get("file_data")
            if isinstance(file_data, MutableMapping):
                raw_data = file_data.pop("data", None)
                mime_type = file_data.get("mime_type")
                if isinstance(raw_data, str) and raw_data.strip():
                    try:
                        data_bytes = base64.b64decode(raw_data, validate=False)
                    except (BinasciiError, ValueError):
                        data_bytes = b""
                    if data_bytes:
                        saved_path = _register_artifact(data_bytes, mime_type, hint)
                        file_data["uri"] = saved_path.as_uri()
                        file_data["relative_path"] = str(saved_path.relative_to(run_dir))
                    else:
                        file_data["data_truncated"] = True
            for key, value in list(node.items()):
                node[key] = _process(value, f"{hint}.{key}" if hint else key)
            return node
        if isinstance(node, list):
            return [
                _process(item, f"{hint}[{index}]")
                for index, item in enumerate(node)
            ]
        if isinstance(node, str):
            def _replace(match: re.Match) -> str:
                mime_type = match.group("mime")
                data_str = match.group("data")
                data_bytes = b""
                try:
                    data_bytes = base64.b64decode(data_str, validate=False)
                except (BinasciiError, ValueError):
                    return match.group(0)
                saved_path = _register_artifact(data_bytes, mime_type, hint)
                return saved_path.as_uri()

            return DATA_URI_PATTERN.sub(_replace, node)
        return node

    processed_payload = _process(payload, "event") if isinstance(payload, MutableMapping) else payload
    return processed_payload, extracted, notes


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


def _escape_markdown_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br/>")


def _format_tool_cell(tools: Sequence[ToolInteractionRecord]) -> str:
    if not tools:
        return "—"
    entries = [
        f"{tool.name} ({'chamada' if tool.direction == 'call' else 'resposta'})"
        for tool in tools
    ]
    return "<br/>".join(_escape_markdown_cell(entry) for entry in entries)


def _format_artifact_cell(artifacts: Sequence[ArtifactRecord]) -> str:
    if not artifacts:
        return "—"
    entries = [f"{artifact.filename} (v{artifact.version})" for artifact in artifacts]
    return "<br/>".join(_escape_markdown_cell(entry) for entry in entries)


def _aggregate_tool_usage(events: Sequence[EventRecord]) -> list[tuple[str, int, int]]:
    usage: dict[str, dict[str, int]] = {}
    for event in events:
        for tool in event.tools:
            counters = usage.setdefault(tool.name, {"call": 0, "response": 0})
            counters[tool.direction] += 1
    aggregated: list[tuple[str, int, int]] = []
    for tool_name, counters in sorted(usage.items()):
        aggregated.append((tool_name, counters.get("call", 0), counters.get("response", 0)))
    return aggregated


def _compute_quality_stats(
    expectation_reports: Sequence[ExpectationReport],
) -> tuple[float | None, list[dict[str, Any]]]:
    detailed: list[dict[str, Any]] = []
    collected_scores: list[float] = []

    for report in expectation_reports:
        evaluation = report.evaluation or {}
        step_scores: dict[str, float | None] = {}
        for key in ("relevance", "cohesion", "coherence"):
            score = _normalize_score(evaluation.get(key))
            step_scores[key] = score
            if score is not None:
                collected_scores.append(score)
        detail = {
            "step": report.step,
            "expected": report.expected,
            "responses": report.responses,
            "evaluation": evaluation,
            "scores": step_scores,
            "average": None,
        }
        values = [value for value in step_scores.values() if value is not None]
        if values:
            detail["average"] = sum(values) / len(values)
        detailed.append(detail)

    overall = None
    if collected_scores:
        overall = sum(collected_scores) / len(collected_scores)

    return overall, detailed


def _build_bpm_diagram(
    flow: FlowDefinition,
    events: Sequence[EventRecord],
    artifacts: Sequence[ArtifactRecord],
) -> str:
    tool_names = sorted({tool.name for event in events for tool in event.tools}) or ["(nenhuma)"]
    event_nodes = []
    for event in events:
        label = _escape_markdown_cell(_shorten_cli_preview(event.summary, width=60))
        node_id = f"EV{event.index}"
        event_nodes.append((node_id, f"{event.step} / {event.author}", label))

    artifact_nodes: list[str] = []

    lines = ["```mermaid", "flowchart LR"]
    lines.append("    subgraph Usuario")
    lines.append("        U0([Início da simulação])")
    step_ids: list[str] = []
    for step in flow.steps:
        sanitized = _sanitize_token(step.name)
        step_id = f"U_{sanitized}"
        step_ids.append(step_id)
        lines.append(
            f"        {step_id}{{Envio do passo '{_escape_markdown_cell(step.name)}'}}"
        )
    lines.append("    end")

    lines.append("    subgraph Orquestracao")
    lines.append("        O0[Criação da sessão InMemoryRunner]")
    for node_id, title, label in event_nodes:
        lines.append(f"        {node_id}[{title}\\n{label}]")
    lines.append("    end")

    lines.append("    subgraph Ferramentas")
    for idx, tool_name in enumerate(tool_names, start=1):
        lines.append(f"        T{idx}[[{_escape_markdown_cell(tool_name)}]]")
    lines.append("    end")

    lines.append("    subgraph Artefatos")
    if artifacts:
        for index, artifact in enumerate(artifacts, start=1):
            node_id = f"AR{index}"
            artifact_nodes.append(node_id)
            lines.append(
                f"        {node_id}({_escape_markdown_cell(artifact.filename)}\\n"
                f"v{artifact.version})"
            )
    else:
        lines.append("        A0((Nenhum artefato gerado))")
        artifact_nodes.append("A0")
    lines.append("    end")

    lines.append("    subgraph Avaliacao")
    lines.append("        E0[(Comparação com resultados esperados)]")
    lines.append("    end")

    lines.append("    subgraph Relatorios")
    lines.append("        R0[Atualização do session.log]")
    lines.append("        R1[Gerar structured_summary.md]")
    lines.append("        R2[Gerar RESULTS.md]")
    lines.append("    end")

    lines.append("    U0 --> O0")
    last_node = "O0"
    if step_ids:
        lines.append(f"    O0 --> {step_ids[0]}")
        for previous, current in zip(step_ids, step_ids[1:]):
            lines.append(f"    {previous} --> {current}")
        last_node = step_ids[-1]

    if event_nodes:
        lines.append(f"    {last_node} --> {event_nodes[0][0]}")
        for (current_id, _, _), (next_id, _, _) in zip(event_nodes, event_nodes[1:]):
            lines.append(f"    {current_id} --> {next_id}")
        lines.append(f"    {event_nodes[-1][0]} --> E0")
        last_event = event_nodes[-1][0]
    else:
        lines.append(f"    {last_node} --> E0")
        last_event = "E0"

    if tool_names:
        for idx, tool_name in enumerate(tool_names, start=1):
            node = event_nodes[min(idx - 1, len(event_nodes) - 1)][0] if event_nodes else last_node
            lines.append(f"    {node} -.-> T{idx}")

    if artifact_nodes:
        for artifact_node in artifact_nodes:
            lines.append(f"    {last_event} --> {artifact_node}")
            lines.append(f"    {artifact_node} --> R2")

    lines.append("    E0 --> R0 --> R1 --> R2")
    lines.append("```")
    return "\n".join(lines)


def _generate_results_markdown(
    *,
    flow: FlowDefinition,
    run_dir: Path,
    events: Sequence[EventRecord],
    expectation_reports: Sequence[ExpectationReport],
    flow_result: dict[str, Any],
    model_error: dict[str, Any] | None,
) -> str:
    total_artifacts = sum(len(event.artifacts) for event in events)
    all_artifacts = [artifact for event in events for artifact in event.artifacts]

    overall_quality, detailed_quality = _compute_quality_stats(expectation_reports)

    lines: list[str] = []
    lines.append(f"# RESULTADOS - {flow.case_id}")
    lines.append("")
    lines.append("## Visão Geral")
    lines.append("")
    lines.append(f"- Diretório de execução: `{run_dir}`")
    lines.append(f"- Caso: **{flow.case_id}** — {flow.description or 'sem descrição fornecida'}")
    lines.append(f"- Usuário simulado: `{flow.user_id}`")
    lines.append(f"- Sessão: `{flow.session_id}`")
    lines.append(f"- Eventos processados: {len(events)}")
    lines.append(f"- Artefatos gerados: {total_artifacts}")
    if model_error:
        lines.append(f"- Erro do modelo: {json.dumps(model_error, ensure_ascii=False)}")
    lines.append("")

    if flow.expected_outcomes:
        lines.append("## Objetivos esperados do cenário")
        lines.append("")
        for outcome in flow.expected_outcomes:
            lines.append(f"- {outcome}")
        lines.append("")

    lines.append("## Histórico de Interações")
    lines.append("")
    lines.append("| Evento | Passo | Autor | Resumo | Ferramentas | Artefatos |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for event in events:
        summary = _escape_markdown_cell(_shorten_cli_preview(event.summary, width=160))
        lines.append(
            "| {idx} | {step} | {author} | {summary} | {tools} | {artifacts} |".format(
                idx=event.index,
                step=_escape_markdown_cell(event.step),
                author=_escape_markdown_cell(event.author),
                summary=summary,
                tools=_format_tool_cell(event.tools),
                artifacts=_format_artifact_cell(event.artifacts),
            )
        )
    if not events:
        lines.append("| — | — | — | Nenhum evento registrado | — | — |")
    lines.append("")

    lines.append("## Consolidação do fluxo de execução")
    lines.append("")
    lines.append(
        f"- Eventos registrados (runner): {flow_result.get('events_processed', len(events))}"
    )
    lines.append(
        "- Passos processados: "
        + (", ".join(flow_result.get("steps", [])) or "nenhum passo informado")
    )
    artifacts_saved = flow_result.get("artifacts_saved", [])
    if artifacts_saved:
        lines.append("- Artefatos por evento:")
        for entry in artifacts_saved:
            files = entry.get("files", [])
            lines.append(
                "  - Evento {idx}: {files}".format(
                    idx=entry.get("index", "?"),
                    files=", ".join(files) if files else "nenhum arquivo reportado",
                )
            )
    else:
        lines.append("- Nenhum artefato foi registrado pelo runner.")
    lines.append("")

    lines.append("## Uso consolidado de ferramentas")
    lines.append("")
    tool_usage = _aggregate_tool_usage(events)
    if tool_usage:
        lines.append("| Ferramenta | Chamadas | Respostas |")
        lines.append("| --- | ---: | ---: |")
        for tool_name, calls, responses in tool_usage:
            lines.append(f"| {tool_name} | {calls} | {responses} |")
    else:
        lines.append("Nenhuma ferramenta foi acionada durante a simulação.")
    lines.append("")

    lines.append("## Artefatos gerados")
    lines.append("")
    if all_artifacts:
        for artifact in all_artifacts:
            lines.append(
                f"- `{artifact.filename}` (v{artifact.version}) — {artifact.mime_type or 'mime desconhecido'} — "
                f"{artifact.absolute_path}"
            )
    else:
        lines.append("- Nenhum artefato foi persistido.")
    lines.append("")

    lines.append("## Avaliação de qualidade")
    lines.append("")
    if detailed_quality:
        lines.append("| Passo | Veredito | Relevância | Coesão | Coerência | Score médio |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for detail in detailed_quality:
            evaluation = detail.get("evaluation") or {}
            verdict = evaluation.get("verdict", "N/D")
            scores = detail.get("scores") or {}
            lines.append(
                "| {step} | {verdict} | {rel} | {coh} | {coer} | {avg} |".format(
                    step=_escape_markdown_cell(detail.get("step", "—")),
                    verdict=_escape_markdown_cell(str(verdict)),
                    rel=_format_score(scores.get("relevance")),
                    coh=_format_score(scores.get("cohesion")),
                    coer=_format_score(scores.get("coherence")),
                    avg=_format_score(detail.get("average")),
                )
            )
            summary_text = evaluation.get("summary")
            if summary_text:
                lines.append(f"> {summary_text}")
        lines.append("")
    else:
        lines.append("- Avaliação automática indisponível (verifique credenciais do avaliador).")

    if overall_quality is not None:
        lines.append(
            f"- **Qualidade consolidada**: {overall_quality * 100:.1f}% (média dos indicadores avaliados)."
        )
    else:
        lines.append("- **Qualidade consolidada**: N/D")
    lines.append("")

    lines.append("## Análise detalhada")
    lines.append("")
    if expectation_reports:
        for detail in detailed_quality:
            evaluation = detail.get("evaluation") or {}
            summary_text = evaluation.get("summary") or "Sem resumo fornecido pelo avaliador."
            verdict = evaluation.get("verdict", "N/D")
            lines.append(
                f"- **{detail.get('step', 'Passo')}** — Veredito: {verdict}. "
                f"Resumo: {summary_text}"
            )
    else:
        lines.append("- Não foi possível gerar análise automática; utilize os logs para revisão manual.")
    lines.append("")

    lines.append("## Sugestões estruturadas de melhoria")
    lines.append("")
    lines.append("### Prompt do agente")
    lines.append(
        "- Revisar instruções do prompt em `agents/diagramador/prompt.py` para reforçar a geração completa do datamodel, "
        "especialmente destacando requisitos de validação PIX e evidenciando quando nenhuma ferramenta adicional for necessária."
    )
    lines.append(
        "- Incluir exemplos orientando a responder com confirmações explícitas sobre a criação de artefatos para evitar dúvidas do avaliador."
    )
    lines.append("")
    lines.append("### Orquestração e agente")
    lines.append(
        "- Expandir `agents/diagramador/agent.py` para registrar no estado de sessão os metadados do template selecionado, facilitando reuso entre passos."  # noqa: E501
    )
    lines.append(
        "- Monitorar latência de cada ferramenta via logging estruturado para identificar gargalos durante execuções reais."
    )
    lines.append("")
    lines.append("### Ferramentas e geração de artefatos")
    lines.append(
        "- Ajustar `agents/diagramador/tools/diagramador/operations.py` para validar a existência dos arquivos no diretório `outputs/` após cada salvamento, "
        "emitindo alertas quando nenhum artefato for criado."
    )
    lines.append(
        "- Automatizar testes de ponta-a-ponta no script de simulação garantindo que `generate_archimate_diagram` seja acionado pelo menos uma vez em cada cenário crítico."
    )
    lines.append("")

    lines.append("## Diagrama BPM do fluxo da simulação")
    lines.append("")
    lines.append(
        _build_bpm_diagram(flow=flow, events=events, artifacts=all_artifacts),
    )
    lines.append("")

    return "\n".join(lines)


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


def _resolve_evaluation_client() -> Any | None:
    global _EVALUATION_CLIENT
    if _EVALUATION_CLIENT is not None:
        return _EVALUATION_CLIENT

    if genai_module is None:
        return None

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GENAI_API_KEY")
    project = os.getenv("VERTEXAI_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("VERTEXAI_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION")

    base_kwargs: dict[str, Any] = {}
    if api_key:
        base_kwargs["api_key"] = api_key

    candidate_kwargs: list[dict[str, Any]] = [dict(base_kwargs)]
    if project and location:
        candidate_kwargs.append({**base_kwargs, "project": project, "location": location})
        candidate_kwargs.append(
            {
                **base_kwargs,
                "vertexai_project": project,
                "vertexai_location": location,
            }
        )

    for kwargs in candidate_kwargs:
        try:
            _EVALUATION_CLIENT = genai_module.Client(**kwargs)  # type: ignore[call-arg]
            if _EVALUATION_CLIENT is not None:
                break
        except TypeError:
            continue
        except Exception:
            continue

    return _EVALUATION_CLIENT


def _resolve_evaluation_model(runner: InMemoryRunner | None = None) -> str:
    if runner is not None:
        for attribute in ("evaluation_model", "default_model", "model"):
            candidate = getattr(runner, attribute, None)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
    return (
        os.getenv("USER_SIM_EVALUATION_MODEL")
        or os.getenv("EVALUATION_MODEL")
        or os.getenv("GENAI_EVALUATION_MODEL")
        or "gemini-1.5-flash"
    )


def _extract_text_from_generic_response(response: Any) -> str:
    if response is None:
        return ""

    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    if hasattr(response, "model_dump"):
        try:
            payload = response.model_dump(mode="json")  # type: ignore[call-arg]
        except TypeError:
            payload = response.model_dump()  # type: ignore[misc]
        except Exception:
            payload = None
        if isinstance(payload, dict):
            extracted = _extract_text_from_event(payload)
            if extracted:
                return extracted

    candidates = getattr(response, "candidates", None)
    texts: list[str] = []
    if candidates:
        for candidate in candidates:
            content = getattr(candidate, "content", None) or getattr(candidate, "message", None)
            parts = getattr(content, "parts", None)
            if parts is None and isinstance(candidate, dict):
                parts = candidate.get("parts")
            if parts:
                for part in parts:
                    value = getattr(part, "text", None)
                    if value is None and isinstance(part, dict):
                        value = part.get("text")
                    if value:
                        texts.append(str(value))
    if texts:
        return "\n".join(texts)

    if hasattr(response, "to_dict"):
        try:
            payload = response.to_dict()  # type: ignore[call-arg]
        except Exception:
            payload = None
        if isinstance(payload, dict):
            extracted = _extract_text_from_event(payload)
            if extracted:
                return extracted

    return str(response)


def _extract_json_payload(raw_text: str) -> tuple[dict[str, Any], str]:
    text = raw_text.strip()
    if not text:
        raise json.JSONDecodeError("Resposta vazia.", raw_text, 0)

    try:
        parsed = json.loads(text)
        return parsed, text
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start : end + 1]
        parsed = json.loads(snippet)
        return parsed, snippet

    raise json.JSONDecodeError("JSON não localizado na resposta do avaliador.", raw_text, 0)


def _normalize_score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return score


def _format_score(value: float | None) -> str:
    if value is None:
        return "N/D"
    return f"{value:.2f}"


def _run_expectation_evaluator(
    expected: str, collected: str, runner: InMemoryRunner | None = None
) -> dict[str, Any]:
    client = _resolve_evaluation_client()
    if client is None:
        raise RuntimeError(
            "Cliente LLM para avaliação não disponível. Instale e configure 'google-genai' e as credenciais."
        )

    model = _resolve_evaluation_model(runner)
    prompt = textwrap.dedent(
        f"""
        Você é um avaliador crítico que compara o resultado de um agente com o objetivo esperado.

        Produza um JSON com a seguinte estrutura:
        {{
          "summary": "resuma em português o alinhamento do resultado com o esperado",
          "relevance": valor entre 0 e 1 indicando o quanto a resposta está relacionada ao objetivo,
          "cohesion": valor entre 0 e 1 indicando a consistência interna da resposta,
          "coherence": valor entre 0 e 1 indicando se o raciocínio geral é coerente,
          "verdict": "APROVADO" ou "REPROVADO" de acordo com o atendimento ao objetivo
        }}

        ### Objetivo esperado
        {expected.strip()}

        ### Resposta do agente
        {collected.strip()}

        Retorne apenas o JSON.
        """
    ).strip()

    models_client = getattr(client, "models", None)
    if models_client and hasattr(models_client, "generate_content"):
        generate_content = models_client.generate_content  # type: ignore[assignment]
    elif hasattr(client, "generate_content"):
        generate_content = getattr(client, "generate_content")  # type: ignore[assignment]
    else:
        raise RuntimeError(
            "Cliente LLM não expõe método 'generate_content'. Atualize o pacote google-genai."
        )

    try:
        response = generate_content(  # type: ignore[misc]
            model=model,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
        )
    except Exception as exc:  # pragma: no cover - depende do cliente oficial
        raise RuntimeError(f"Falha ao chamar o modelo de avaliação: {exc}") from exc

    raw_text = _extract_text_from_generic_response(response)
    if not raw_text.strip():
        raise RuntimeError("O modelo de avaliação não retornou conteúdo textual.")

    try:
        parsed, json_snippet = _extract_json_payload(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Não foi possível interpretar o retorno do avaliador: {exc}") from exc

    summary = parsed.get("summary") or parsed.get("resumo") or ""
    relevance = _normalize_score(parsed.get("relevance") or parsed.get("relatividade"))
    cohesion = _normalize_score(parsed.get("cohesion") or parsed.get("coesao") or parsed.get("coesão"))
    coherence = _normalize_score(parsed.get("coherence") or parsed.get("coerencia") or parsed.get("coerência"))
    verdict = parsed.get("verdict") or parsed.get("veredito")

    evaluation = {
        "summary": summary,
        "relevance": relevance,
        "cohesion": cohesion,
        "coherence": coherence,
        "verdict": verdict,
        "model": model,
        "raw_json": parsed,
        "raw_text": json_snippet,
    }

    return evaluation


def _analyze_expectation(
    runner: InMemoryRunner,
    step: StepDefinition,
    *,
    expected: str | None,
    responses: Iterable[str],
    model_error: dict[str, Any] | None,
) -> tuple[str, ExpectationReport | None, str | None]:
    if model_error:
        message = (
            "A execução foi interrompida por um erro do provedor. Consulte o bloco de erro "
            "acima para detalhes."
        )
        report = ExpectationReport(
            step=step.name,
            expected=expected,
            responses=list(responses),
            error="Erro do provedor durante o passo.",
        )
        return message, report, None

    collected = "\n".join(response for response in responses if response)

    if not expected or not expected.strip():
        narrative = (
            "Nenhum resultado esperado foi definido para este passo. A resposta capturada foi registrada "
            "para acompanhamento manual."
        )
        report = ExpectationReport(
            step=step.name,
            expected=expected,
            responses=list(responses),
            evaluation=None,
            error="Resultado esperado ausente.",
        )
        return narrative, report, None

    if not collected:
        narrative = "Nenhuma resposta do agente foi registrada para comparação."
        report = ExpectationReport(
            step=step.name,
            expected=expected,
            responses=list(responses),
            evaluation=None,
            error="Resposta do agente ausente.",
        )
        return narrative, report, None

    try:
        evaluation = _run_expectation_evaluator(expected, collected, runner)
    except RuntimeError as exc:
        narrative = (
            "⚠️ Não foi possível concluir a avaliação automática das expectativas: "
            f"{exc}."
        )
        report = ExpectationReport(
            step=step.name,
            expected=expected,
            responses=list(responses),
            evaluation=None,
            error=str(exc),
        )
        return narrative, report, None

    relevance = _format_score(evaluation.get("relevance"))
    cohesion = _format_score(evaluation.get("cohesion"))
    coherence = _format_score(evaluation.get("coherence"))
    verdict = evaluation.get("verdict") or "N/D"
    summary = evaluation.get("summary") or "Sem resumo gerado."

    lines = [
        summary,
        "",
        f"- Relatividade: {relevance}",
        f"- Coesão: {cohesion}",
        f"- Coerência: {coherence}",
        f"- Veredito: {verdict}",
        f"- Modelo de avaliação: {evaluation.get('model')}",
    ]

    report = ExpectationReport(
        step=step.name,
        expected=expected,
        responses=list(responses),
        evaluation=evaluation,
    )

    return "\n".join(lines), report, evaluation.get("raw_text")


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
