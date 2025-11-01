import os
from pathlib import Path

import app.settings as settings


def test_get_template_directory_defaults_to_c4_model(tmp_path, monkeypatch):
    monkeypatch.delenv("DIAGRAMADOR_TEMPLATE_DIR", raising=False)
    directory = settings.get_template_directory()
    assert directory.name == "C4-Model"
    assert directory.exists()


def test_get_template_directory_env_override(tmp_path, monkeypatch):
    custom_dir = tmp_path / "templates"
    custom_dir.mkdir()
    monkeypatch.setenv("DIAGRAMADOR_TEMPLATE_DIR", str(custom_dir))
    assert settings.get_template_directory() == custom_dir.resolve()


def test_get_template_and_metamodel_path_overrides(monkeypatch, tmp_path):
    template_file = tmp_path / "layout.xml"
    template_file.write_text("<xml />", encoding="utf-8")
    metamodel_file = tmp_path / "metamodel.xml"
    metamodel_file.write_text("<xml />", encoding="utf-8")
    monkeypatch.setenv("DIAGRAMADOR_TEMPLATE_PATH", str(template_file))
    monkeypatch.setenv("DIAGRAMADOR_METAMODEL_PATH", str(metamodel_file))
    assert settings.get_template_path() == template_file.resolve()
    assert settings.get_metamodel_path() == metamodel_file.resolve()


def test_get_output_root_override(monkeypatch, tmp_path):
    output_dir = tmp_path / "outputs"
    monkeypatch.setenv("DIAGRAMADOR_OUTPUT_ROOT", str(output_dir))
    assert settings.get_output_root() == output_dir.resolve()
