# Self-Test Lab

The **Self-Test Lab** is a reference solution built with the Google Cloud Dynamic Agents Starter Pack. It orchestrates validation
scenarios that exercise agents, tools, and runtime plugins to ensure integrations behave as expected before they are promoted to
production workflows.

## Key capabilities
- Runs guided self-assessment flows defined in `app/workflow.yaml`.
- Uses custom callbacks located under `app/tools` to track assertions and capture telemetry.
- Can be deployed with the Terraform blueprints available in `deployment/terraform`.

## Getting started
Install the project with [uv](https://github.com/astral-sh/uv) or your preferred tool:

```bash
uv sync
uv run python -m app.agent
```

## Deployment
Refer to [`deployment/README.md`](deployment/README.md) for detailed infrastructure and CI/CD setup instructions.
