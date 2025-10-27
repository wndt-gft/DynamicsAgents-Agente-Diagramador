"""Newman Execution Generator - Generates execution strategies based on complexity."""

from typing import Dict, Any


def generate_execution_strategies(domain: str, complexity: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate execution strategies based on complexity."""

    strategies = {
        "simple": {
            "parallel_runs": 1,
            "iterations": 1,
            "delay_request": 0,
            "timeout_request": 30000,
            "timeout_script": 5000
        },
        "medium": {
            "parallel_runs": 3,
            "iterations": 2,
            "delay_request": 100,
            "timeout_request": 60000,
            "timeout_script": 10000
        },
        "complex": {
            "parallel_runs": 5,
            "iterations": 3,
            "delay_request": 200,
            "timeout_request": 120000,
            "timeout_script": 15000
        },
        "enterprise": {
            "parallel_runs": 10,
            "iterations": 5,
            "delay_request": 500,
            "timeout_request": 300000,
            "timeout_script": 30000
        }
    }

    base_strategy = strategies.get(complexity, strategies["medium"])

    return {
        "newman_options": {
            "collection": f"{domain}_api_collection.json",
            "environment": f"{domain}_{{env}}.json",
            "reporters": ["cli", "json", "html"],
            "reporter": {
                "html": {
                    "export": f"reports/{domain}-newman-report.html"
                },
                "json": {
                    "export": f"reports/{domain}-newman-report.json"
                }
            },
            "iterationCount": base_strategy["iterations"],
            "delayRequest": base_strategy["delay_request"],
            "timeoutRequest": base_strategy["timeout_request"],
            "timeoutScript": base_strategy["timeout_script"],
            "ignoreRedirects": False,
            "insecure": False
        },
        "parallel_execution": {
            "enabled": True,
            "workers": base_strategy["parallel_runs"],
            "strategy": "collection_split"
        }
    }
