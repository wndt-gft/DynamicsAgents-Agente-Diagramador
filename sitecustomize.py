"""Configurações de importação para ambientes de testes locais."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _ensure_repo_on_path() -> Path:
    """Insere a raiz do repositório no ``sys.path`` e a retorna."""

    root = Path(__file__).resolve().parent
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def _bootstrap_google_stubs(repo_root: Path) -> None:
    """Garante que os módulos stub ``google`` sejam carregados antes dos oficiais."""

    stubs_dir = repo_root / "google"
    init_file = stubs_dir / "__init__.py"
    if not init_file.exists():
        return

    # Cria um módulo "google" baseado nos stubs incluídos no repositório.
    spec = importlib.util.spec_from_file_location("google", init_file)
    if spec is None or spec.loader is None:
        return

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.__path__ = [str(stubs_dir)]  # type: ignore[attr-defined]
    sys.modules["google"] = module

    # Precarrega submódulos essenciais para evitar importações externas.
    importlib.import_module("google.genai")
    importlib.import_module("google.adk")


def configure_environment() -> None:
    repo_root = _ensure_repo_on_path()
    _bootstrap_google_stubs(repo_root)


configure_environment()

