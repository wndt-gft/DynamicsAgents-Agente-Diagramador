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

"""Generic CI/CD Pipeline Generator - Universal pipeline for any domain."""

from typing import Dict, Any


def generate_ci_cd_pipeline(domain: str, config: Dict[str, Any] = None) -> str:
    """Generate universal CI/CD pipeline for any domain."""

    return f"""# .github/workflows/{domain}-karate.yml
# Universal CI/CD Pipeline for {domain} Karate API Tests

name: {domain.title()} Karate API Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM

env:
  DOMAIN: {domain}

jobs:
  karate-api-tests:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        environment: [test, staging]
        test-suite: [smoke, regression, security, performance]
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Setup Java
      uses: actions/setup-java@v4
      with:
        java-version: '17'
        distribution: 'temurin'
        cache: maven
    
    - name: Setup {domain} test environment
      run: |
        echo "Setting up {domain} API testing environment"
        mkdir -p target/reports
    
    - name: Run Karate tests
      run: |
        mvn test -Dkarate.env=${{{{ matrix.environment }}}} \\
                 -Dkarate.options="--tags @${{{{ matrix.test-suite }}}}" \\
                 -Dtest={domain.title()}ApiTest
    
    - name: Generate test reports
      if: always()
      run: |
        mvn surefire-report:report
        
    - name: Upload test results
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: karate-results-{domain}-${{{{ matrix.environment }}}}-${{{{ matrix.test-suite }}}}
        path: |
          target/karate-reports
          target/surefire-reports
        retention-days: 30
    
    - name: Publish test results
      uses: dorny/test-reporter@v1
      if: always()
      with:
        name: Karate Tests ({domain} - ${{{{ matrix.environment }}}}-${{{{ matrix.test-suite }}}})
        path: target/surefire-reports/*.xml
        reporter: java-junit

  notify-results:
    runs-on: ubuntu-latest
    needs: [karate-api-tests]
    if: always()
    
    steps:
    - name: Notify test results
      run: |
        echo "Test results for {domain}:"
        if [ "${{{{ needs.karate-api-tests.result }}}}" == "success" ]; then
          echo "✅ All {domain} API tests passed successfully"
        else
          echo "❌ Some {domain} API tests failed"
        fi"""
