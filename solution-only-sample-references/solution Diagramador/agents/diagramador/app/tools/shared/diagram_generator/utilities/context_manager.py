"""
Agent Context Manager
Manages agent state and context throughout the conversation
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AgentContext:
    """Manages agent conversation context and state"""

    def __init__(self):
        self._last_analysis: Optional[Dict[str, Any]] = None
        self._last_user_story: Optional[str] = None

    @property
    def last_analysis(self) -> Optional[Dict[str, Any]]:
        """Get the last analysis result"""
        return self._last_analysis

    @last_analysis.setter
    def last_analysis(self, analysis: Dict[str, Any]) -> None:
        """Set the last analysis result"""
        self._last_analysis = analysis
        logger.info("📊 Analysis context updated")

    @property
    def last_user_story(self) -> Optional[str]:
        """Get the last user story"""
        return self._last_user_story

    @last_user_story.setter
    def last_user_story(self, user_story: str) -> None:
        """Set the last user story"""
        self._last_user_story = user_story
        logger.info("📝 User story context updated")

    def has_context(self) -> bool:
        """Check if there's valid context available"""
        return self._last_analysis is not None and self._last_user_story is not None

    def clear_context(self) -> None:
        """Clear all context"""
        self._last_analysis = None
        self._last_user_story = None
        logger.info("🧹 Context cleared")

    def get_context_summary(self) -> str:
        """Get a summary of current context"""
        if not self.has_context():
            return "Nenhum contexto disponível"

        story_preview = (self._last_user_story[:50] + "...") if len(self._last_user_story) > 50 else self._last_user_story
        analysis_elements = len(self._last_analysis.get('business_layer', {}).get('actors', []))

        return f"User story: {story_preview} | Elementos analisados: {analysis_elements}"


# Global context instance
_agent_context = AgentContext()


def get_agent_context() -> AgentContext:
    """Get the global agent context instance"""
    return _agent_context


class DiagramContextManager:
    """Wrapper compatível com a interface legada baseada em classe."""

    def __init__(self) -> None:
        self._context = _agent_context

    def get_context(self) -> AgentContext:
        return self._context

    def get_last_analysis(self) -> Optional[Dict[str, Any]]:
        return self._context.last_analysis

    def set_last_analysis(self, analysis: Dict[str, Any]) -> None:
        self._context.last_analysis = analysis

    def get_last_user_story(self) -> Optional[str]:
        return self._context.last_user_story

    def set_last_user_story(self, user_story: str) -> None:
        self._context.last_user_story = user_story

    def reset(self) -> None:
        self._context.clear_context()
