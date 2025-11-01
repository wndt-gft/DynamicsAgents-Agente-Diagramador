#!/usr/bin/env python3
"""Utility to synchronize project metadata with a release version.

The release workflow derives the version number from the pushed tag and uses
this helper to rewrite the project metadata so the built artifacts always carry
an accurate version string.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

VERSION_PATTERN = re.compile(
    r"^(?P<prefix>\s*version\s*=\s*")(?P<version>[^"\n]+)(?P<suffix>".*)$",
    re.MULTILINE,
)


def _validate_version(value: str) -> str:
    pep440 = re.compile(r"^[0-9]+(\.[0-9]+)*([a-zA-Z0-9]+[0-9]*)?(?:[.-][a-zA-Z0-9]+)*$")
    if not pep440.match(value):
        raise argparse.ArgumentTypeError(
            "release version must follow PEP 440 semantics (examples: 1.2.0, 1.2.0rc1)"
        )
    return value


def _update_pyproject(path: Path, version: str) -> None:
    content = path.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(content)
    if not match:
        raise RuntimeError(f"Unable to locate 'version = ""' field in {path}")
    updated = VERSION_PATTERN.sub(f"\\g<prefix>{version}\\g<suffix>", content, count=1)
    path.write_text(updated, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync project version from release tag")
    parser.add_argument("pyproject", type=Path, help="Path to the pyproject.toml file")
    parser.add_argument("version", type=_validate_version, help="Normalized release version")
    args = parser.parse_args(argv)

    if not args.pyproject.is_file():
        raise SystemExit(f"pyproject file not found: {args.pyproject}")

    _update_pyproject(args.pyproject, args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
