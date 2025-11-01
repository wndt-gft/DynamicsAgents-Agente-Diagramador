"""
ADK Patch module to resolve YAML loading issues
"""

import logging

logger = logging.getLogger(__name__)

def patch_yaml_loading():
    """
    Patch YAML loading issues in ADK environment
    """
    try:
        # Import yaml safely
        import yaml

        # Test if yaml is working properly - don't modify SafeLoader
        try:
            # Simple test to ensure YAML is functional
            test_yaml = "test: value"
            yaml.safe_load(test_yaml)
            logger.info("✅ YAML funcionando corretamente")
        except Exception as yaml_error:
            logger.warning(f"⚠️ YAML test failed: {yaml_error}")

        # Try to patch ADK components if available
        try:
            from google.adk.cli.utils import agent_loader

            def _dummy_load_from_yaml_config(self, agent_name: str):
                """Dummy function que bypassa completamente o YAML loading."""
                logger.info(f"🔄 Bypass YAML loading para agente: {agent_name}")
                return None

            if hasattr(agent_loader.AgentLoader, '_load_from_yaml_config'):
                agent_loader.AgentLoader._load_from_yaml_config = _dummy_load_from_yaml_config
                logger.info("✅ Patch no AgentLoader aplicado")

        except ImportError:
            logger.debug("⚠️ AgentLoader não disponível - patch não necessário")

        logger.info("✅ ADK YAML patch aplicado com sucesso")
        return True

    except ImportError:
        logger.warning("⚠️ PyYAML não encontrado - patch não necessário")
        return False
    except Exception as e:
        logger.warning(f"⚠️ Patch YAML não necessário: {e}")
        return False

# Aplicar patches automaticamente quando o módulo for importado
patch_yaml_loading()
