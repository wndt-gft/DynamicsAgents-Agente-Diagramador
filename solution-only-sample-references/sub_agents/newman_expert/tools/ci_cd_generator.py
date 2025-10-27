"""Newman CI/CD Generator - Generates CI/CD integration configurations."""

import json
from typing import Dict, Any


def generate_ci_cd_integration(domain: str, config: Dict[str, Any]) -> Dict[str, str]:
    """Generate CI/CD integration configurations."""

    github_workflow = f"""# .github/workflows/{domain}-newman.yml
# Universal CI/CD Pipeline for {domain} Newman API Tests

name: {domain.title()} Newman API Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours

env:
  DOMAIN: {domain}

jobs:
  newman-api-tests:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        environment: [test, staging]
        test-suite: [smoke, regression, security]
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Setup Node.js
      uses: actions/setup-node@v4
      with:
        node-version: '18'
        cache: 'npm'
    
    - name: Install Newman
      run: |
        npm install -g newman
        npm install -g newman-reporter-htmlextra
    
    - name: Run Newman tests
      run: |
        newman run collections/{domain}-api-collection.json \\
               --environment environments/{domain}-${{{{ matrix.environment }}}}.json \\
               --reporters cli,htmlextra,json \\
               --reporter-htmlextra-export reports/{domain}-${{{{ matrix.environment }}}}-${{{{ matrix.test-suite }}}}.html \\
               --reporter-json-export reports/{domain}-${{{{ matrix.environment }}}}-${{{{ matrix.test-suite }}}}.json \\
               --iteration-count 2 \\
               --delay-request 100
    
    - name: Upload test results
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: newman-results-{domain}-${{{{ matrix.environment }}}}-${{{{ matrix.test-suite }}}}
        path: |
          reports/
          newman/
    
    - name: Publish test results
      uses: dorny/test-reporter@v1
      if: success() || failure()
      with:
        name: Newman Tests - {domain.title()} ${{{{ matrix.environment }}}} ${{{{ matrix.test-suite }}}}
        path: 'reports/{domain}-${{{{ matrix.environment }}}}-${{{{ matrix.test-suite }}}}.json'
        reporter: newman"""

    jenkins_pipeline = f"""// Jenkinsfile for {domain} Newman API Tests
pipeline {{
    agent any
    
    parameters {{
        choice(
            name: 'ENVIRONMENT',
            choices: ['test', 'staging', 'prod'],
            description: 'Environment to run tests against'
        )
        choice(
            name: 'TEST_SUITE',
            choices: ['smoke', 'regression', 'security'],
            description: 'Test suite to execute'
        )
    }}
    
    stages {{
        stage('Setup') {{
            steps {{
                script {{
                    sh 'npm install -g newman newman-reporter-htmlextra'
                }}
            }}
        }}
        
        stage('Run Newman Tests') {{
            steps {{
                script {{
                    sh '''
                        newman run collections/{domain}-api-collection.json \\
                               --environment environments/{domain}-${{ENVIRONMENT}}.json \\
                               --reporters cli,htmlextra,json \\
                               --reporter-htmlextra-export reports/{domain}-${{ENVIRONMENT}}-${{TEST_SUITE}}.html \\
                               --reporter-json-export reports/{domain}-${{ENVIRONMENT}}-${{TEST_SUITE}}.json \\
                               --iteration-count 3 \\
                               --delay-request 200
                    '''
                }}
            }}
        }}
        
        stage('Archive Results') {{
            steps {{
                archiveArtifacts artifacts: 'reports/**/*', fingerprint: true
                publishHTML([
                    allowMissing: false,
                    alwaysLinkToLastBuild: true,
                    keepAll: true,
                    reportDir: 'reports',
                    reportFiles: '{domain}-${{ENVIRONMENT}}-${{TEST_SUITE}}.html',
                    reportName: '{domain.title()} Newman Test Report'
                ])
            }}
        }}
    }}
    
    post {{
        always {{
            cleanWs()
        }}
        failure {{
            emailext subject: '{domain.title()} API Tests Failed',
                     body: 'Newman API tests failed for environment: ${{ENVIRONMENT}}',
                     to: '${{BUILD_USER_EMAIL}}'
        }}
    }}
}}"""

    return {
        "github_workflow": github_workflow,
        "jenkins_pipeline": jenkins_pipeline,
        "package_json": generate_package_json(domain),
        "npm_scripts": generate_npm_scripts(domain)
    }


def generate_package_json(domain: str) -> str:
    """Generate package.json for Newman project."""

    package_config = {
        "name": f"{domain}-newman-tests",
        "version": "1.0.0",
        "description": f"Newman API tests for {domain}",
        "scripts": {
            "test": f"newman run collections/{domain}-api-collection.json",
            "test:dev": f"newman run collections/{domain}-api-collection.json --environment environments/{domain}-dev.json",
            "test:staging": f"newman run collections/{domain}-api-collection.json --environment environments/{domain}-staging.json",
            "test:prod": f"newman run collections/{domain}-api-collection.json --environment environments/{domain}-prod.json",
            "test:smoke": f"newman run collections/{domain}-api-collection.json --folder 'Smoke Tests'",
            "test:regression": f"newman run collections/{domain}-api-collection.json --folder 'Regression Tests'",
            "test:security": f"newman run collections/{domain}-api-collection.json --folder 'Security Tests'",
            "report": f"newman run collections/{domain}-api-collection.json --reporters htmlextra --reporter-htmlextra-export reports/report.html"
        },
        "devDependencies": {
            "newman": "^6.0.0",
            "newman-reporter-htmlextra": "^1.23.0"
        },
        "keywords": ["newman", "postman", "api-testing", domain],
        "author": "QA Automation Team",
        "license": "MIT"
    }

    return json.dumps(package_config, indent=2)


def generate_npm_scripts(domain: str) -> str:
    """Generate additional npm scripts."""

    return f"""#!/bin/bash
# {domain} Newman Test Scripts

# Run all tests
npm run test

# Run environment-specific tests
npm run test:dev
npm run test:staging  
npm run test:prod

# Run test suites
npm run test:smoke
npm run test:regression
npm run test:security

# Generate HTML report
npm run report

# Run tests with custom options
newman run collections/{domain}-api-collection.json \\
       --environment environments/{domain}-test.json \\
       --iteration-count 3 \\
       --delay-request 100 \\
       --timeout-request 30000 \\
       --reporters cli,json,htmlextra \\
       --reporter-htmlextra-export reports/custom-report.html
"""
