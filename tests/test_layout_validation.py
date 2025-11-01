from pathlib import Path

import pytest

from agents.diagramador.tools.diagramador.layouts import (
    LayoutValidationError,
    generate_layout_preview,
)
from agents.diagramador.tools.diagramador.templates import TemplateMetadata, ViewMetadata


def _patch_template_sources(monkeypatch, metadata: TemplateMetadata, blueprint: dict) -> None:
    from agents.diagramador.tools.diagramador import layouts

    monkeypatch.setattr(layouts, "_resolve_template_path", lambda *_: metadata.path)
    monkeypatch.setattr(layouts, "load_template_metadata", lambda *_: metadata)
    monkeypatch.setattr(layouts, "load_template_blueprint", lambda *_: blueprint)
    # Impede tentativas de renderização caso a validação não dispare erros.
    monkeypatch.setattr(
        layouts,
        "render_view_layout",
        lambda *_, **__: {"svg_data_uri": "data:image/svg+xml;base64,AAA"},
    )


def _metadata(view_id: str = "view-1") -> TemplateMetadata:
    view_meta = ViewMetadata(
        identifier=view_id,
        name="Visão 1",
        documentation=None,
        viewpoint=None,
        index=0,
    )
    return TemplateMetadata(
        path=Path("template.xml"),
        model_identifier="template",
        model_name="Template",
        documentation=None,
        views=(view_meta,),
    )


def test_generate_layout_preview_errors_on_missing_element_ref(monkeypatch):
    metadata = _metadata()
    blueprint = {
        "elements": [
            {"id": "existing", "name": "Elemento Blueprint", "documentation": "Doc base"}
        ],
        "views": {"diagrams": [{"id": "view-1", "name": "Visão 1", "nodes": []}]},
    }
    _patch_template_sources(monkeypatch, metadata, blueprint)

    datamodel = {
        "model_name": "Modelo do Usuário",
        "elements": [
            {"id": "existing", "name": "Elemento Atualizado"},
        ],
        "views": [
            {
                "id": "view-1",
                "name": "Visão 1",
                "nodes": [
                    {
                        "id": "custom-node",
                        "elementRef": "missing-element",
                        "bounds": {"x": 0, "y": 0, "w": 100, "h": 80},
                    }
                ],
            }
        ],
    }

    with pytest.raises(LayoutValidationError, match="custom-node") as exc:
        generate_layout_preview(datamodel, "template.xml")

    assert "missing-element" in str(exc.value)
    assert any("custom-node" in issue for issue in exc.value.issues)


def test_generate_layout_preview_errors_on_blueprint_metadata(monkeypatch):
    metadata = _metadata()
    blueprint = {
        "elements": [
            {
                "id": "placeholder",
                "name": "Elemento Placeholder",
                "documentation": "Doc placeholder",
            },
            {
                "id": "customizable",
                "name": "Elemento Custom",
                "documentation": "Doc template",
            },
        ],
        "views": {
            "diagrams": [
                {
                    "id": "view-1",
                    "name": "Visão 1",
                    "nodes": [
                        {
                            "id": "node-placeholder",
                            "elementRef": "placeholder",
                            "bounds": {"x": 0, "y": 0, "w": 100, "h": 80},
                        },
                        {
                            "id": "node-custom",
                            "elementRef": "customizable",
                            "bounds": {"x": 120, "y": 0, "w": 100, "h": 80},
                        },
                    ],
                }
            ]
        },
    }
    _patch_template_sources(monkeypatch, metadata, blueprint)

    datamodel = {
        "model_name": "Modelo do Usuário",
        "elements": [
            {"id": "customizable", "name": "Elemento Ajustado"},
        ],
        "views": [
            {
                "id": "view-1",
                "name": "Visão 1",
                "nodes": [
                    {
                        "id": "node-placeholder",
                        "elementRef": "placeholder",
                        "bounds": {"x": 0, "y": 0, "w": 100, "h": 80},
                    }
                ],
            }
        ],
    }

    with pytest.raises(LayoutValidationError, match="placeholder") as exc:
        generate_layout_preview(datamodel, "template.xml")

    message = str(exc.value)
    assert "Visão 1" in message or "Visão" in message
    assert "Preencha os componentes" in message
    assert exc.value.reason == "template_content_not_customized"
    assert any("node-placeholder" in issue for issue in exc.value.issues)

