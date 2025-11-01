"""Discovery Engine search tool with graceful fallbacks for missing SDKs.

This module is imported at application start-up by :mod:`app.agent`.  The
original implementation assumed the Google Cloud Discovery Engine SDK and the
Google ADK runtime were always installed.  In the constrained testing
environment used by the unit tests those dependencies are absent which caused
an :class:`ImportError` during test collection.  The tests never exercise the
real Discovery Engine integration, they only need the module to be importable
so that the surrounding application can be tested.

To keep the production behaviour intact while allowing the tests to run we
provide lightweight shims for the optional dependencies.  When the Discovery
Engine client libraries are not available the tool returns an informative
placeholder response instead of failing at import time.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional dependency: Google ADK ToolContext
# ---------------------------------------------------------------------------
try:  # pragma: no cover - exercised when the dependency is installed.
    from google.adk.tools import ToolContext as _ToolContext  # type: ignore
except Exception:  # pragma: no cover - handled in tests where SDK is missing.

    @dataclass
    class ToolContext:  # type: ignore[override]
        """Minimal stand-in for :class:`google.adk.tools.ToolContext`.

        Only the attributes accessed by the codebase are provided.  Using a
        dataclass keeps the representation helpful for logging while remaining
        completely dependency free.
        """

        user_id: Optional[str] = None
        session_id: Optional[str] = None
        metadata: Dict[str, Any] = field(default_factory=dict)

    _HAS_ADK = False
else:  # pragma: no cover - exercised when the dependency is installed.
    ToolContext = _ToolContext
    _HAS_ADK = True


# ---------------------------------------------------------------------------
# Optional dependency: Google Cloud Discovery Engine SDK
# ---------------------------------------------------------------------------
try:  # pragma: no cover - requires external dependency.
    from google.api_core.client_options import ClientOptions
    from google.cloud import discoveryengine_v1 as discoveryengine
except Exception:  # pragma: no cover - the branch used in the test env.
    ClientOptions = None  # type: ignore
    discoveryengine = None  # type: ignore


def discovery_search_tool(search_query: str, tool_context: ToolContext) -> str:
    """Execute a Discovery Engine search or return a graceful fallback.

    Parameters
    ----------
    search_query:
        The query provided by the agent.
    tool_context:
        Runtime metadata supplied by the Google ADK environment.  The value is
        accepted for compatibility but is not strictly required when running in
        the test environment.
    """

    if discoveryengine is None or ClientOptions is None:
        logger.warning(
            "Discovery Engine client libraries not available. "
            "Returning fallback response for query '%s'.",
            search_query,
        )
        return str([])

    project_id = os.getenv("DISCOVERY_PROJECT_ID")
    location = os.getenv("DISCOVERY_LOCATION", "global")
    engine_id = os.getenv("DISCOVERY_ENGINE_ID")

    if not all([project_id, location, engine_id]):
        logger.warning(
            "Discovery Engine configuration incomplete (project_id=%s, "
            "location=%s, engine_id=%s). Returning fallback response.",
            project_id,
            location,
            engine_id,
        )
        return str([])

    client_options = (
        ClientOptions(api_endpoint=f"{location}-discoveryengine.googleapis.com")
        if location != "global"
        else None
    )

    client = discoveryengine.SearchServiceClient(client_options=client_options)
    serving_config = (
        f"projects/{project_id}/locations/{location}/collections/default_collection/"
        f"engines/{engine_id}/servingConfigs/default_config"
    )

    request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=search_query,
        page_size=4,
        query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
            condition=discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO
        ),
        spell_correction_spec=discoveryengine.SearchRequest.SpellCorrectionSpec(
            mode=(
                discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.SUGGESTION_ONLY
            )
        ),
    )

    page_result = client.search(request)
    formatted_results = _filter_and_format_documents(page_result.results)

    logger.info("\n" + "=" * 80)
    logger.info("🚀 RETRIEVED CONTEXT: %s", formatted_results)
    logger.info("=" * 80 + "\n")

    return str(formatted_results)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------
def _filter_and_format_documents(
    search_results: Iterable[Any], similarity_threshold: float = 0.6
) -> List[Dict[str, Any]]:
    """Filter Discovery Engine results and surface relevant fields."""

    def _get_similarity_score(search_result: Any) -> float:
        rank_signals = getattr(search_result, "rank_signals", None)
        if rank_signals and hasattr(rank_signals, "semantic_similarity_score"):
            return float(rank_signals.semantic_similarity_score)
        return 0.0

    filtered_docs = [
        doc for doc in search_results if _get_similarity_score(doc) >= similarity_threshold
    ]
    sorted_docs = sorted(filtered_docs, key=_get_similarity_score, reverse=True)

    formatted_docs: List[Dict[str, Any]] = []
    for search_result in sorted_docs:
        struct_data = getattr(getattr(search_result, "document", None), "struct_data", {})
        formatted_doc = {
            key: struct_data.get(key)
            for key in (
                "u_acronym",
                "u_tribe_name",
                "u_service_classification",
                "comments",
                "u_squad_name",
                "u_install_status",
                "u_tower",
                "environment",
            )
        }
        formatted_doc["similarity_score"] = _get_similarity_score(search_result)
        formatted_docs.append(formatted_doc)

    return formatted_docs


__all__ = ["ToolContext", "discovery_search_tool"]

