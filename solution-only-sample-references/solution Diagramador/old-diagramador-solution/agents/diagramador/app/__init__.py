# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Architect Agent ADK v5.1
Agente de arquitetura para geração de diagramas C4 consolidado.
Sistema de callback para garantir URLs corretas do GCS.
"""

import logging
import sys
import os

# Add current directory to path for imports
current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Apply ADK YAML patch if available
try:
    from .adk_patch import patch_yaml_loading

    patch_yaml_loading()
except ImportError:
    # ADK patch not available, continue without it
    pass

# Import agent components
from .agent import (
    root_agent,
    architect_agent,
    diagram_generator_tool,
    quality_validator_tool,
    vertex_search_tool,
    __version__
)

from .callback import sanitize_model_response_callback as _sanitize_model_response
from .callback import sanitize_model_response_callback as _ensure_correct_gcs_url

# Configure logger
logger = logging.getLogger(__name__)

# Aliases for compatibility
diagramador = root_agent
agent = root_agent

# Main exports
__all__ = [
    # Agents
    "root_agent",
    "architect_agent",
    "diagramador",
    "agent",

    # Tools
    "diagram_generator_tool",
    "quality_validator_tool",
    "vertex_search_tool",

    # Callbacks
    "_ensure_correct_gcs_url",

    # Version
    "__version__"
]

# Log initialization
logger.info(f"🚀 Architect Agent ADK v{__version__} carregado com sucesso!")
logger.info("✅ Sistema de callback ativo para garantir URLs corretas")

# Check runtime environment
if os.environ.get('GOOGLE_ADK_RUNTIME'):
    logger.info("🌐 Executando no ambiente Google ADK Runtime")
elif os.environ.get('VERTEX_AI_AGENT_ENGINE'):
    logger.info("🚀 Executando no Vertex AI Agent Engine")
else:
    logger.info("💻 Executando em ambiente local/desenvolvimento")