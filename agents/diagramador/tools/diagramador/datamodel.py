"""Funções para consolidar e exportar o datamodel aprovado pelo usuário."""

from __future__ import annotations

import json
from pathlib import Path
from typing import MutableMapping

from ..archimate_exchange import xml_exchange
from .artifacts import (
    SESSION_ARTIFACT_ARCHIMATE_XML,
    SESSION_ARTIFACT_FINAL_DATAMODEL,
    SESSION_ARTIFACT_SAVED_DATAMODEL,
)
from .constants import (
    DEFAULT_DATAMODEL_FILENAME,
    DEFAULT_DIAGRAM_FILENAME,
    DEFAULT_TEMPLATE,
    DEFAULT_XSD_DIR,
    OUTPUT_DIR,
)
from .session import get_cached_artifact, store_artifact
from .templates import load_template_metadata, resolve_template_path

__all__ = [
    "finalize_datamodel",
    "save_datamodel",
    "generate_archimate_diagram",
]


def _resolve_template(template_path: str | None) -> Path:
    return resolve_template_path(template_path)


def _normalize_datamodel(datamodel: str | dict | None) -> tuple[dict[str, object], str]:
    if isinstance(datamodel, dict):
        payload = datamodel
    elif isinstance(datamodel, str):
        payload = json.loads(datamodel)
    else:
        raise ValueError("O datamodel fornecido é obrigatório para finalização.")

    formatted = json.dumps(payload, indent=2, ensure_ascii=False)
    return payload, formatted


def finalize_datamodel(
    datamodel: str | dict,
    template_path: str | None,
    *,
    session_state: MutableMapping[str, object] | None = None,
) -> dict[str, object]:
    target_template = _resolve_template(template_path)
    metadata = load_template_metadata(target_template)
    payload, formatted = _normalize_datamodel(datamodel)

    payload.setdefault("model_identifier", metadata.model_identifier or "id-model")
    payload.setdefault(
        "model_name",
        {"text": metadata.model_name or metadata.model_identifier or "Modelo"},
    )

    artifact = {
        "template": str(target_template),
        "json": formatted,
        "datamodel": payload,
    }

    if session_state is not None:
        store_artifact(session_state, SESSION_ARTIFACT_FINAL_DATAMODEL, artifact)
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_FINAL_DATAMODEL,
            "element_count": len(payload.get("elements", [])),
        }

    return artifact


def _resolve_datamodel_source(
    datamodel: str | dict | None,
    session_state: MutableMapping[str, object] | None,
) -> tuple[Path, str]:
    if isinstance(datamodel, (str, dict)):
        payload, formatted = _normalize_datamodel(datamodel)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        target = OUTPUT_DIR / DEFAULT_DATAMODEL_FILENAME
        target.write_text(formatted, encoding="utf-8")
        return target, formatted

    artifact = get_cached_artifact(session_state, SESSION_ARTIFACT_FINAL_DATAMODEL) if session_state else None
    if isinstance(artifact, dict) and isinstance(artifact.get("json"), str):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        target = OUTPUT_DIR / DEFAULT_DATAMODEL_FILENAME
        target.write_text(artifact["json"], encoding="utf-8")
        return target, artifact["json"]

    raise ValueError("Não há datamodel disponível. Finalize o modelo antes de salvar.")


def save_datamodel(
    datamodel: str | dict | None,
    filename: str | None,
    *,
    session_state: MutableMapping[str, object] | None = None,
) -> dict[str, object]:
    output_name = filename or DEFAULT_DATAMODEL_FILENAME
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source_path, formatted = _resolve_datamodel_source(datamodel, session_state)
    target_path = OUTPUT_DIR / output_name
    target_path.write_text(formatted, encoding="utf-8")

    artifact = {
        "path": str(target_path),
        "source": str(source_path),
    }

    if session_state is not None:
        store_artifact(session_state, SESSION_ARTIFACT_SAVED_DATAMODEL, artifact)
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_SAVED_DATAMODEL,
            "path": str(target_path),
        }

    return artifact


def _load_final_datamodel(session_state: MutableMapping[str, object] | None) -> Path:
    if session_state is None:
        raise ValueError("O estado de sessão é obrigatório para localizar o datamodel.")
    artifact = get_cached_artifact(session_state, SESSION_ARTIFACT_SAVED_DATAMODEL)
    if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
        return Path(artifact["path"]).resolve()
    artifact = get_cached_artifact(session_state, SESSION_ARTIFACT_FINAL_DATAMODEL)
    if isinstance(artifact, dict) and isinstance(artifact.get("json"), str):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / DEFAULT_DATAMODEL_FILENAME
        path.write_text(artifact["json"], encoding="utf-8")
        return path.resolve()
    raise ValueError(
        "Nenhum datamodel final encontrado. Finalize e salve o datamodel antes de gerar o XML."
    )


def generate_archimate_diagram(
    model_json_path: str | None,
    *,
    output_filename: str | None = None,
    template_path: str | None = None,
    validate: bool = True,
    xsd_dir: str | None = None,
    session_state: MutableMapping[str, object] | None = None,
) -> dict[str, object]:
    target_template = _resolve_template(template_path)
    datamodel_path = (
        Path(model_json_path).resolve()
        if model_json_path
        else _load_final_datamodel(session_state)
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_name = output_filename or DEFAULT_DIAGRAM_FILENAME
    output_path = OUTPUT_DIR / output_name
    xml_exchange.patch_template_with_model(target_template, datamodel_path, output_path)

    validation_dir = Path(xsd_dir) if xsd_dir else DEFAULT_XSD_DIR
    validated = False
    report: list[str] = []
    if validate:
        validation_dir = validation_dir.resolve()
        if validation_dir.exists():
            validated, report = xml_exchange.validate_with_full_xsd(output_path, validation_dir)

    artifact = {
        "path": str(output_path.resolve()),
        "validated": validated,
        "validation_report": report,
    }

    if session_state is not None:
        store_artifact(session_state, SESSION_ARTIFACT_ARCHIMATE_XML, artifact)
        return {
            "status": "ok",
            "artifact": SESSION_ARTIFACT_ARCHIMATE_XML,
            "path": artifact["path"],
            "validated": validated,
        }

    return artifact
