"""Newman Monitoring Generator - Generates monitoring and alerting configurations."""

from typing import Dict, Any


def generate_monitoring_config(domain: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate monitoring and alerting configuration."""

    return {
        "monitors": [
            {
                "name": f"{domain.title()} API Health Monitor",
                "collection": f"{domain}_api_collection",
                "environment": f"{domain}_prod",
                "schedule": {
                    "cron": "0 */5 * * * *",  # Every 5 minutes
                    "timezone": "UTC"
                },
                "options": {
                    "stopOnError": False,
                    "stopOnFailure": False
                },
                "notifications": [
                    {
                        "type": "webhook",
                        "url": config.get("webhook_url", "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"),
                        "events": ["run.failure", "run.start"]
                    }
                ]
            }
        ],
        "alerts": [
            {
                "name": f"{domain.title()} Response Time Alert",
                "condition": "response_time > 5000",
                "severity": "warning",
                "description": "API response time exceeds 5 seconds"
            },
            {
                "name": f"{domain.title()} Error Rate Alert",
                "condition": "error_rate > 5",
                "severity": "critical",
                "description": "API error rate exceeds 5%"
            }
        ]
    }
