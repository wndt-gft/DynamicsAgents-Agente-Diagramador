from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _ensure_app_package_importable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Add the solution root to ``sys.path`` for all tests.

    Os testes herdados da solução antiga assumem que o pacote ``app`` está no
    ``sys.path``. O fixture autouse garante essa configuração em todo o
    conjunto de testes, inclusive para módulos novos que exercitam ferramentas
    individuais.
    """

    tests_dir = Path(__file__).resolve().parent
    solution_root = tests_dir.parent
    repo_root = solution_root.parent
    monkeypatch.syspath_prepend(str(solution_root))
    monkeypatch.syspath_prepend(str(repo_root))
