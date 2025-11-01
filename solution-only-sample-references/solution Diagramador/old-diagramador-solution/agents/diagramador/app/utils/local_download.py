"""
Utilitário para servir arquivos XML localmente quando GCS não está disponível
"""
import os
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

def create_local_download_link(xml_file_path: str, filename: str) -> str:
    """
    Cria um link de download local quando GCS não está disponível

    Args:
        xml_file_path: Caminho para o arquivo XML local
        filename: Nome do arquivo

    Returns:
        str: URL local ou link de fallback
    """
    try:
        if os.path.exists(xml_file_path):
            # Converter para path relativo do workspace
            workspace_root = Path(__file__).parent.parent.parent.parent
            relative_path = Path(xml_file_path).relative_to(workspace_root)

            # Criar URL local para desenvolvimento
            local_url = f"file:///{xml_file_path.replace(os.sep, '/')}"
            logger.info(f"📁 Created local file URL: {local_url}")
            return local_url
        else:
            logger.error(f"❌ Local file not found: {xml_file_path}")
            return f"Arquivo local: {filename}"
    except Exception as e:
        logger.error(f"❌ Error creating local link: {e}")
        return f"Arquivo salvo como: {filename}"

def ensure_download_availability(xml_content: str, local_file_path: str, filename: str) -> tuple[str, str]:
    """
    Garante que sempre há uma forma de download do arquivo, mesmo se GCS falhar

    Returns:
        tuple: (blob_name, download_url)
    """
    try:
        # Primeiro, tenta GCS com bucket específico
        try:
            from .gcs import upload_and_get_signed_url
            # Garantir que sempre usa o bucket correto
            blob_name, signed_url = upload_and_get_signed_url(
                xml_content,
                bucket_name="diagram_signed_temp",
                filename=filename
            )
            logger.info(f"✅ GCS upload successful: {blob_name}")
            return blob_name, signed_url
        except Exception as gcs_error:
            logger.warning(f"⚠️ GCS upload failed: {gcs_error}")

            # Fallback para link local
            if local_file_path and os.path.exists(local_file_path):
                local_url = create_local_download_link(local_file_path, filename)
                blob_name = f"gs://local_files/{filename}"  # Manter formato consistente
                logger.info(f"📁 Using local file fallback: {local_url}")
                return blob_name, local_url
            else:
                # Último fallback - criar o arquivo se não existe
                if xml_content and filename:
                    outputs_dir = Path(__file__).parent.parent.parent / "outputs"
                    outputs_dir.mkdir(exist_ok=True)
                    fallback_path = outputs_dir / filename

                    with open(fallback_path, 'w', encoding='utf-8') as f:
                        f.write(xml_content)

                    local_url = create_local_download_link(str(fallback_path), filename)
                    blob_name = f"gs://local_files/{filename}"
                    logger.info(f"📁 Created fallback file: {fallback_path}")
                    return blob_name, local_url
                else:
                    # Se não temos conteúdo ou filename, retorna erro
                    logger.error("❌ No content or filename for fallback")
                    return f"gs://error/no_content", "Erro: dados não disponíveis"

    except Exception as e:
        logger.error(f"❌ Critical error in download availability: {e}")
        return f"gs://error/{filename if filename else 'unknown'}", f"Erro ao processar arquivo: {filename if filename else 'unknown'}"
