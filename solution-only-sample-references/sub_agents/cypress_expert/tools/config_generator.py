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

"""Cypress Configuration Generator - Domain-agnostic expert tool."""

from typing import Dict, Any, List


def generate_cypress_config(
    domain: str,
    browsers: List[str] = None,
    accessibility: bool = True,
    performance: bool = True
) -> str:
    """Generate optimized Cypress configuration for any domain."""

    # Basic defaults without domain_config dependency
    browsers = browsers or ["chrome", "firefox", "edge"]

    base_config = _generate_base_config(domain)
    env_vars = _generate_environment_variables(domain)
    plugins_config = _generate_plugins_config(accessibility, performance)

    return f"""// cypress.config.js - Expert Configuration for {domain}
// Generated dynamically based on domain analysis
const {{ defineConfig }} = require('cypress');

module.exports = defineConfig({{
{base_config}
  
  // Environment-specific settings
  env: {{
{env_vars}
  }},
  
  setupNodeEvents(on, config) {{
{plugins_config}
    
    return config;
  }}
}});"""


def _generate_base_config(domain: str) -> str:
    """Generate base configuration."""

    config = f"""  e2e: {{
    baseUrl: process.env.BASE_URL || 'http://localhost:3000',
    
    // Expert browser configuration
    browser: {{
      name: 'chrome',
      family: 'chromium',
      channel: 'stable',
      displayName: 'Chrome',
      version: 'latest',
      path: '',
      minSupportedVersion: 64,
      majorVersion: 'latest'
    }},
    
    // Performance optimizations
    video: process.env.CI ? false : true,
    screenshotOnRunFailure: true,
    trashAssetsBeforeRuns: true,
    watchForFileChanges: false,
    
    // Expert retry configuration
    retries: {{
      runMode: 2,
      openMode: 0
    }},
    
    // Security-specific browser configuration
    chromeWebSecurity: false,
    experimentalStudio: true,
    args: ['--disable-web-security', '--disable-features=VizDisplayCompositor']
  }},"""

    return config


def _generate_environment_variables(domain: str) -> str:
    """Generate environment variables based on domain configuration."""

    env_vars = [
        f"    domain: '{domain}'",
        f"    environment: process.env.NODE_ENV || 'development'",
        f"    apiUrl: process.env.API_URL || 'http://localhost:3001'",
    ]

    return ",\n".join(env_vars)


def _generate_plugins_config(accessibility: bool, performance: bool) -> str:
    """Generate plugins configuration based on requirements."""

    plugins = []

    # Base plugins
    plugins.append("""    // Expert logging and debugging
    on('task', {
      log(message) {
        console.log(message);
        return null;
      },
      table(message) {
        console.table(message);
        return null;
      }
    });""")

    # Accessibility plugin
    if accessibility:
        plugins.append("""
    // Accessibility testing integration
    on('task', {
      validateAccessibility: require('./plugins/accessibility-validator')
    });""")

    # Performance monitoring plugin
    if performance:
        plugins.append("""
    // Performance monitoring integration
    on('task', {
      measurePerformance: require('./plugins/performance-monitor')
    });""")

    # Code coverage for all domains
    plugins.append("""
    // Code coverage integration
    require('@cypress/code-coverage/task')(on, config);""")

    return "\n".join(plugins)
