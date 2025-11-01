# Deployment

This directory contains the Terraform configurations for provisioning the necessary Google Cloud infrastructure for the **Self-Test Lab** solution.

The recommended way to deploy the infrastructure and set up the CI/CD pipeline is by using the `agent-starter-pack setup-cicd` command from the root of your project.

However, for a more hands-on approach, you can always apply the Terraform configurations manually for a do-it-yourself setup.

## Runtime configuration
When promoting the Self-Test Lab to Cloud Run, Workflows or Vertex AI, keep the environment variables in [`.env.sample`](../../../.env.sample) in sync across stages:


For detailed information on the deployment process, infrastructure, and CI/CD pipelines, please refer to the official documentation:

**[Agent Starter Pack Deployment Guide](https://googlecloudplatform.github.io/agent-starter-pack/guide/deployment.html)**
