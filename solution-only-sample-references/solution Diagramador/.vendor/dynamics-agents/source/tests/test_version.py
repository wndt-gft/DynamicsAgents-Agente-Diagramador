from __future__ import annotations

from pathlib import Path

import pytest

import tomllib

from dynamic_agents import __version__


def test_package_version_matches_metadata():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    expected = data["project"]["version"]
    if __version__ == "0.0.0":
        pytest.skip("dynamics-agents is not installed; metadata version unavailable")
    assert __version__ == expected
