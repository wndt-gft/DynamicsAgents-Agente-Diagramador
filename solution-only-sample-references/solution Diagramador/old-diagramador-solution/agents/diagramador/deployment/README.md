# Deployment

This directory contains the Terraform configurations for provisioning the necessary Google Cloud infrastructure for your agent.

The recommended way to deploy the infrastructure and set up the CI/CD pipeline is by using the `agent-starter-pack setup-cicd` command from the root of your project.

However, for a more hands-on approach, you can always apply the Terraform configurations manually for a do-it-yourself setup.

## Runtime configuration
When wiring the agent into Cloud Run, Workflows or Vertex AI, remember to propagate the new model variables consumed by `agents/model_register.configure_model`:

| Variable | Purpose |
|----------|---------|
| `MODEL_AGENT_ARCHITECT` | Overrides the primary architect agent model identifier |
| `MODEL_AGENT_ARCHITECT_LIB` | Optional registry path (`module:Class`) for custom architect models |
| `MODEL_AGENT_SEARCH` | Overrides the embedded search agent model |
| `MODEL_AGENT_SEARCH_LIB` | Optional registry path for the search agent (ex.: Anthropic Claude) |

Values can be expressed as plain identifiers (`gemini-2.5-pro`), delimiter tokens (`modelo::pacote.modulo:Classe`) or JSON payloads (`{"model": "provider/model", "registry": "pkg:Cls"}`). If no variable is set, the deployment falls back to `gemini-2.5-pro` and treats it as a native ADK model. Para modelos externos, como Anthropic Claude, utilize a matriz completa de variáveis:

```bash
# Exemplo de configuração do modelo para Anthropic Claude
MODEL_AGENT_ARCHITECT=claude-opus-4-1@20250805                      # modelo real a ser usado pelo agente diagramador
MODEL_AGENT_ARCHITECT_LIB=google.adk.models.anthropic_llm:Claude    # opcional, factory customizada para Claude
MODEL_AGENT_SEARCH=claude-opus-4-1@20250805                         # modelo real a ser usado pelo agente de busca das siglas
MODEL_AGENT_SEARCH_LIB=google.adk.models.anthropic_llm:Claude       # opcional, factory customizada para Claude
```

For detailed information on the deployment process, infrastructure, and CI/CD pipelines, please refer to the official documentation:

**[Agent Starter Pack Deployment Guide](https://googlecloudplatform.github.io/agent-starter-pack/guide/deployment.html)**