"""Notebook-style tool that stores structured checkpoints in the shared state."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from dynamic_agents import RuntimeToolError


class Tool:
    """Persists structured entries into the shared notebook state."""

    def __init__(self, metadata: Optional[Dict[str, Any]] = None):
        self.metadata = metadata or {}

    def record_entry(
        self,
        scope: str,
        title: str,
        data: Optional[Dict[str, Any]] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Append an entry to the notebook under the given scope."""

        if not scope:
            raise RuntimeToolError("O campo 'scope' é obrigatório.")
        if not title:
            raise RuntimeToolError("O campo 'title' é obrigatório.")

        state = state or {}
        notebook = state.setdefault("notebook", {})
        scoped_entries = notebook.setdefault(scope, [])
        entry = {
            "title": title,
            "data": data or {},
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        scoped_entries.append(entry)
        notebook[scope] = scoped_entries

        timeline = state.setdefault("testing", {}).setdefault("timeline", [])
        timeline.append({"scope": scope, "title": title, "timestamp": entry["timestamp"]})

        return {"notebook": notebook, "testing": {"timeline": timeline}}
