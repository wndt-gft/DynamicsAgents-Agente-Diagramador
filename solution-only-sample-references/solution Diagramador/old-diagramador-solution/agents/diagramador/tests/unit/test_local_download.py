"""Tests for local download helper ensuring coverage of fallback paths."""

import os
import sys
from pathlib import Path
import types

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = PROJECT_ROOT / "app"
for p in (PROJECT_ROOT, APP_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app.utils import local_download  # noqa: E402


@pytest.fixture
def temp_xml_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "diagram.xml"
    file_path.write_text("<model/>", encoding="utf-8")
    return file_path


def test_create_local_download_link_existing_file(temp_xml_file: Path) -> None:
    url = local_download.create_local_download_link(str(temp_xml_file), temp_xml_file.name)
    assert temp_xml_file.name in url


def test_create_local_download_link_missing_file() -> None:
    url = local_download.create_local_download_link("/non/existent/file.xml", "missing.xml")
    assert url.endswith("missing.xml")


def test_ensure_download_availability_gcs_success(monkeypatch, temp_xml_file: Path) -> None:
    stub_module = types.SimpleNamespace(
        upload_and_get_signed_url=lambda xml_content, bucket_name, filename: (f"gs://{bucket_name}/{filename}", f"https://example.com/{filename}")
    )
    monkeypatch.setitem(sys.modules, "app.utils.gcs", stub_module)

    blob, url = local_download.ensure_download_availability("<model/>", str(temp_xml_file), temp_xml_file.name)
    assert blob.endswith(temp_xml_file.name)
    assert url.startswith("https://")


def test_ensure_download_availability_local_fallback(monkeypatch, temp_xml_file: Path) -> None:
    stub_module = types.SimpleNamespace(
        upload_and_get_signed_url=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("gcs fail"))
    )
    monkeypatch.setitem(sys.modules, "app.utils.gcs", stub_module)

    blob, url = local_download.ensure_download_availability("<model/>", str(temp_xml_file), temp_xml_file.name)
    assert blob.startswith("gs://local_files")
    assert temp_xml_file.name in url


def test_ensure_download_availability_creates_file(monkeypatch, tmp_path: Path) -> None:
    stub_module = types.SimpleNamespace(
        upload_and_get_signed_url=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("gcs fail"))
    )
    monkeypatch.setitem(sys.modules, "app.utils.gcs", stub_module)

    filename = "generated.xml"
    blob, url = local_download.ensure_download_availability("<model>auto</model>", "", filename)
    assert blob.endswith(filename)
    assert url.endswith(filename)
    outputs_dir = APP_ROOT.parent / "outputs"
    try:
        created_file = outputs_dir / filename
        assert created_file.exists()
    finally:
        if created_file.exists():
            created_file.unlink()


def test_ensure_download_availability_error_branch(monkeypatch) -> None:
    stub_module = types.SimpleNamespace(
        upload_and_get_signed_url=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("gcs fail"))
    )
    monkeypatch.setitem(sys.modules, "app.utils.gcs", stub_module)

    blob, url = local_download.ensure_download_availability("", "", "")
    assert blob.startswith("gs://error")
    assert "Erro" in url


def test_ensure_download_availability_critical_error(monkeypatch):
    stub_module = types.SimpleNamespace(
        upload_and_get_signed_url=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("gcs fail"))
    )
    monkeypatch.setitem(sys.modules, "app.utils.gcs", stub_module)
    monkeypatch.setattr(local_download, "create_local_download_link", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    blob, url = local_download.ensure_download_availability("<xml/>", "/tmp/nonexistent.xml", "critical.xml")
    assert blob.endswith("critical.xml")
    assert "Erro ao processar arquivo" in url
