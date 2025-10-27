"""Newman Environment Generator - Generates multi-environment configurations."""

from typing import Dict, Any, List


def generate_multi_environment_configs(
    environment_stages: List[str],
    domain: str,
    config: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Generate environment configurations for different stages."""

    environments = {}

    for stage in environment_stages:
        environments[stage] = {
            "name": f"{domain.title()} - {stage.upper()}",
            "values": [
                {
                    "key": "base_url",
                    "value": _get_environment_url(stage, domain, config),
                    "type": "default",
                    "enabled": True
                },
                {
                    "key": "api_key",
                    "value": f"{{{{api_key_{stage}}}}}",
                    "type": "secret",
                    "enabled": True
                },
                {
                    "key": "auth_token",
                    "value": f"{{{{auth_token_{stage}}}}}",
                    "type": "secret",
                    "enabled": True
                },
                {
                    "key": "environment",
                    "value": stage,
                    "type": "default",
                    "enabled": True
                },
                {
                    "key": "debug_mode",
                    "value": "true" if stage in ["dev", "test"] else "false",
                    "type": "default",
                    "enabled": True
                }
            ]
        }

    return environments


def _get_environment_url(stage: str, domain: str, config: Dict[str, Any]) -> str:
    """Get URL for specific environment stage."""

    url_map = {
        "dev": f"http://localhost:8080",
        "test": f"https://test-api.{domain}.com",
        "staging": f"https://staging-api.{domain}.com",
        "prod": f"https://api.{domain}.com"
    }

    # Use custom URLs if provided
    custom_urls = config.get("environment_urls", {})
    return custom_urls.get(stage, url_map.get(stage, f"https://api.{domain}.com"))
