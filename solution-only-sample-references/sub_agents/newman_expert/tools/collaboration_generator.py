"""Newman Collaboration Generator - Generates collaboration features configurations."""

from typing import Dict, Any


def generate_collaboration_features(domain: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate collaboration features configuration."""

    return {
        "workspace": {
            "name": f"{domain.title()} API Testing Workspace",
            "description": f"Collaborative workspace for {domain} API testing",
            "visibility": "team"
        },
        "documentation": {
            "name": f"{domain.title()} API Documentation",
            "description": f"Comprehensive API documentation for {domain}",
            "sections": [
                {
                    "name": "Getting Started",
                    "content": f"# {domain.title()} API Testing Guide\\n\\nThis collection contains comprehensive tests for the {domain} API."
                },
                {
                    "name": "Authentication",
                    "content": "## Authentication Methods\\n\\nThis API supports multiple authentication methods..."
                },
                {
                    "name": "Error Handling",
                    "content": "## Error Responses\\n\\nThe API returns standard HTTP status codes..."
                }
            ]
        },
        "team_sharing": {
            "permissions": {
                "view": ["team_member"],
                "edit": ["team_lead", "qa_engineer"],
                "admin": ["project_admin"]
            }
        }
    }
