# architect_agent/config/__init__.py
"""
Módulo de configuração do Architect Agent
"""

from .settings import Settings, get_settings
from .prompts import ANALYSIS_PROMPTS
from .patterns import BANKING_PATTERNS

__all__ = [
    "Settings",
    "get_settings",
    "ANALYSIS_PROMPTS",
    "BANKING_PATTERNS"
]