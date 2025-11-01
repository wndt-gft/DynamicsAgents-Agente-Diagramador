"""Module entry-point allowing ``python -m dynamic_agents`` usage."""

from __future__ import annotations

from .runtime import main

if __name__ == "__main__":
    raise SystemExit(main())
