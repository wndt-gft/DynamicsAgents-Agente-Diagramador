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

"""CI/CD Pipeline Generator - Domain-agnostic expert tool."""

from typing import Dict, Any, List


def generate_ci_cd_pipeline(domain: str, browsers: List[str] = None) -> str:
    """Generate CI/CD pipeline configuration for any domain."""

    # Default browsers without domain_config dependency
    browsers = browsers or ["chrome", "firefox", "edge"]

    return f"""# .github/workflows/{domain}-cypress.yml
# Expert CI/CD Pipeline for {domain} Cypress Tests
# Generated dynamically based on domain analysis

name: {domain.title()} Cypress Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]
{_generate_schedule_trigger()}

{_generate_environment_variables(domain)}

jobs:
{_generate_test_jobs(domain, browsers)}
{_generate_deployment_jobs(domain)}
{_generate_notification_jobs(domain)}"""


def _generate_schedule_trigger() -> str:
    """Generate schedule trigger based on domain criticality."""

    # Default to daily testing schedule
    return """  schedule:
    - cron: '0 6 * * *'    # Daily at 6 AM"""


def _generate_environment_variables(domain: str) -> str:
    """Generate environment variables section."""

    return f"""
env:
  CYPRESS_CACHE_FOLDER: ~/.cache/Cypress
  DOMAIN: {domain}
  NODE_ENV: test"""


def _generate_test_jobs(domain: str, browsers: List[str]) -> str:
    """Generate test job configurations."""

    # Parallel configuration
    parallel_config = f"""
    strategy:
      matrix:
        browser: {browsers}
        test-suite: ["smoke", "regression"]
      fail-fast: false"""

    # Resource requirements
    runs_on = "ubuntu-latest"

    return f"""  cypress-tests:
    runs-on: {runs_on}{parallel_config}
    
    steps:
    - name: Checkout code
      uses: actions/checkout@v4
    
    - name: Setup Node.js
      uses: actions/setup-node@v4
      with:
        node-version: '18'
        cache: 'npm'
    
    - name: Install dependencies
      run: |
        npm ci
        npx cypress install
    
    - name: Setup test environment
      run: |
        echo 'Setting up {domain} test environment'
        mkdir -p cypress/downloads cypress/screenshots cypress/videos
    
    - name: Run {domain} Cypress tests
      run: |
        npx cypress run \\
          --config baseUrl=http://localhost:3000 \\
          --env domain={domain} \\
          --reporter mochawesome \\
          --reporter-options reportDir=cypress/reports,overwrite=false,html=false,json=true
    
    - name: Upload test artifacts
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: {domain}-test-results-${{{{ matrix.browser || 'default' }}}}-${{{{ matrix.test-suite || 'all' }}}}
        path: |
          cypress/screenshots
          cypress/videos
          cypress/reports
        retention-days: 30
    
    - name: Generate {domain} test report
      if: always()
      run: |
        npx mochawesome-merge cypress/reports/*.json > cypress/reports/merged-report.json
        npx marge cypress/reports/merged-report.json --reportDir cypress/reports --inline"""


def _generate_deployment_jobs(domain: str) -> str:
    """Generate deployment-related jobs if needed."""

    return f"""
  deploy-to-staging:
    runs-on: ubuntu-latest
    needs: cypress-tests
    if: github.ref == 'refs/heads/develop' && success()
    
    steps:
    - name: Deploy {domain} to staging
      run: |
        echo "Deploying {domain} to staging environment"
        # Deployment logic here
    
    - name: Run smoke tests on staging
      run: |
        npx cypress run \\
          --config baseUrl=https://staging.{domain}.com \\
          --spec 'cypress/e2e/**/smoke*.cy.js' \\
          --env domain={domain},environment=staging
  
  deploy-to-production:
    runs-on: ubuntu-latest
    needs: cypress-tests
    if: github.ref == 'refs/heads/main' && success()
    
    steps:
    - name: Deploy {domain} to production
      run: |
        echo "Deploying {domain} to production environment"
        # Production deployment logic here
    
    - name: Run production health checks
      run: |
        npx cypress run \\
          --config baseUrl=https://{domain}.com \\
          --spec 'cypress/e2e/**/health*.cy.js' \\
          --env domain={domain},environment=production"""


def _generate_notification_jobs(domain: str) -> str:
    """Generate notification jobs for test results."""

    return f"""
  notify-results:
    runs-on: ubuntu-latest
    needs: [cypress-tests]
    if: always()
    
    steps:
    - name: Notify test results
      run: |
        echo "Notifying test results for {domain}"
        # Notification logic here
        
        if [ "${{{{ needs.cypress-tests.result }}}}" == "success" ]; then
          echo "✅ All {domain} tests passed successfully"
        else
          echo "❌ Some {domain} tests failed"
        fi"""
