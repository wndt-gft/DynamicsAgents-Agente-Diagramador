# Deployment

This directory contains the Terraform configurations for provisioning the necessary Google Cloud infrastructure for the **Travel Planner** solution.

The recommended way to deploy the infrastructure and set up the CI/CD pipeline is by using the `agent-starter-pack setup-cicd` command from the root of your project.

However, for a more hands-on approach, you can always apply the Terraform configurations manually for a do-it-yourself setup.

## Runtime configuration
When wiring the agent into Cloud Run, Workflows or Vertex AI, propagate the runtime variables documented in [`.env.sample`](../../../.env.sample) to keep behaviours aligned between local runs and CI/CD pipelines:

| Variable | Purpose |
|----------|---------|
| `TRAVEL_PLANNER_DEFAULT_ORIGIN` | Cidade ou aeroporto padrão usado quando o viajante não informa o ponto de partida |
| `TRAVEL_PLANNER_DEFAULT_DESTINATION` | Destino padrão aplicado em simulações ou demonstrações |
| `TRAVEL_PLANNER_DATA_DIR` | Diretório com os recursos de catálogo sintético consumidos pelas ferramentas da solução |

A seleção de modelos e parâmetros de orquestração é controlada diretamente no arquivo [`app/workflow.yaml`](../app/workflow.yaml) sob a chave `model_settings`. Ajuste os modelos ali definidos (por exemplo, `gemini-2.5-pro`) para refletir os provedores homologados na sua organização.

For detailed information on the deployment process, infrastructure, and CI/CD pipelines, please refer to the official documentation:

**[Agent Starter Pack Deployment Guide](https://googlecloudplatform.github.io/agent-starter-pack/guide/deployment.html)**
