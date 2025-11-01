"""Utilidades opcionais para enviar diagramas ao Google Cloud Storage.

O módulo é resiliente à ausência do SDK do Google Cloud. Quando o cliente não
está disponível ou qualquer etapa do upload falha, retornamos ``(None, None)``
para que os chamadores possam manter o fluxo utilizando apenas o arquivo local.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def _load_storage_client(project: Optional[str] = None):  # pragma: no cover - import dinâmico
    try:
        from google.cloud import storage  # type: ignore
    except Exception as exc:  # noqa: BLE001 - qualquer erro invalida o upload
        logger.warning("Cliente Google Cloud Storage indisponível: %s", exc)
        return None

    try:
        return storage.Client(project=project) if project else storage.Client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Não foi possível instanciar storage.Client: %s", exc)
        return None


def upload_xml_to_gcs(
    xml_content: str,
    filename: str,
    *,
    bucket_name: str,
    project: Optional[str] = None,
    expiration_hours: int = 24,
) -> Tuple[Optional[str], Optional[str]]:
    """Envia o XML para GCS e gera uma URL assinada (quando possível).

    Parameters
    ----------
    xml_content:
        Conteúdo completo do XML ArchiMate.
    filename:
        Nome desejado para o objeto no bucket.
    bucket_name:
        Nome do bucket GCS (já existente).
    project:
        Projeto GCP a ser utilizado. Quando ``None`` utiliza a configuração
        padrão do ambiente.
    expiration_hours:
        Tempo de expiração da URL assinada.

    Returns
    -------
    tuple
        ``(gcs_blob_path, signed_url)`` quando o upload é bem sucedido. Caso
        contrário retorna ``(None, None)``.
    """

    client = _load_storage_client(project)
    if client is None:
        return None, None

    try:
        bucket = client.bucket(bucket_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bucket GCS '%s' indisponível: %s", bucket_name, exc)
        return None, None

    blob = bucket.blob(filename)

    try:
        blob.upload_from_string(xml_content, content_type="application/xml; charset=utf-8")
        logger.info("XML enviado para GCS: gs://%s/%s", bucket_name, filename)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao enviar XML para GCS: %s", exc)
        return None, None

    signed_url: Optional[str] = None
    try:
        expiration = _dt.datetime.utcnow() + _dt.timedelta(hours=expiration_hours)
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=expiration,
            method="GET",
        )
        logger.info("URL assinada gerada para gs://%s/%s", bucket_name, filename)
    except Exception as exc:  # noqa: BLE001 - gera fallback público
        logger.warning("Não foi possível gerar URL assinada: %s", exc)
        try:
            blob.make_public()
            signed_url = blob.public_url
            logger.info("URL pública disponibilizada para gs://%s/%s", bucket_name, filename)
        except Exception as pub_exc:  # noqa: BLE001
            logger.warning("Falha ao tornar blob público: %s", pub_exc)
            signed_url = None

    gcs_path = f"gs://{bucket_name}/{blob.name}"
    return gcs_path, signed_url


__all__ = ["upload_xml_to_gcs"]
