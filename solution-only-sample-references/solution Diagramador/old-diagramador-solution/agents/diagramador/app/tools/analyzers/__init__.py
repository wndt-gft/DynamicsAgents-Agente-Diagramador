"""
Analyzers package - Simplified: only core analyze_user_story retained.
"""

try:
    from .analyzer import analyze_user_story
    __all__ = ['analyze_user_story', 'UnifiedStoryAnalyzer']
except ImportError:
    __all__ = ['analyze_user_story', 'UnifiedStoryAnalyzer']
    def analyze_user_story(*_a, **_k):
        return {"error": "analyzer unavailable", "elements": [], "relationships": []}

class UnifiedStoryAnalyzer:
    """Unified interface kept for compatibility; wraps analyze_user_story."""
    def analyze_story(self, story_text: str, domain: str = "Banking") -> dict:
        try:
            return analyze_user_story(story_text, domain)
        except Exception:
            return {"error": "analysis failed", "elements": [], "relationships": []}
    def enhanced_analysis(self, story_text: str) -> dict:  # legacy method
        return self.analyze_story(story_text)
