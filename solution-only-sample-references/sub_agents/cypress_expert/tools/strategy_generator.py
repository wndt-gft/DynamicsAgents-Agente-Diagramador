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

"""Testing Strategy Generator - Domain-agnostic expert tool."""

from typing import Dict, Any, List


def generate_testing_strategies(domain: str) -> Dict[str, Any]:
    """Generate comprehensive testing strategies for any domain."""

    # Basic domain analysis without domain_config dependency
    domain_analysis = {"type": "general", "complexity": "medium"}

    strategies = {
        "execution_guide": _generate_execution_guide(domain, domain_analysis),
        "maintenance_guide": _generate_maintenance_guide(domain, domain_analysis),
        "performance_strategy": _generate_performance_strategy(domain, domain_analysis),
        "accessibility_strategy": _generate_accessibility_strategy(domain, domain_analysis),
        "debugging_strategy": _generate_debugging_strategy(domain, domain_analysis)
    }

    return strategies


def _generate_execution_guide(domain: str, analysis: Dict[str, Any]) -> str:
    """Generate domain-specific execution guide."""

    # Determine optimal execution parameters
    parallel_workers = _get_parallel_workers(analysis)
    retry_strategy = _get_retry_strategy(analysis)
    timeout_strategy = _get_timeout_strategy(analysis)

    return f"""# {domain.title()} Cypress Execution Guide

## 🚀 Optimized Execution Strategy

### Quick Start Commands
```bash
# Run all tests with domain optimization
npm run cy:run:{domain}

# Run tests in interactive mode
npm run cy:open:{domain}

# Run with domain-specific configuration
npx cypress run --env domain={domain}
```

### Advanced Execution
```bash
# Parallel execution (optimized for {domain})
npx cypress run --parallel --record --key $CYPRESS_RECORD_KEY \\
  --env domain={domain} \\
  --config numTestsKeptInMemory=0

# Browser-specific execution
{_generate_browser_commands(analysis)}

# Environment-specific execution
{_generate_environment_commands(domain, analysis)}
```

### Performance Optimization
```bash
# High-performance execution
npx cypress run \\
  --config video=false,screenshotOnRunFailure=false \\
  --env domain={domain},performanceMode=true \\
  --parallel --ci-build-id $BUILD_ID

# Memory-optimized execution
npx cypress run \\
  --config numTestsKeptInMemory=1 \\
  --env domain={domain},memoryOptimized=true
```

## ⚙️ Domain-Specific Configuration

### Parallel Execution
- **Optimal Workers**: {parallel_workers}
- **Memory Management**: {_get_memory_strategy(analysis)}
- **Load Balancing**: {_get_load_balancing_strategy(analysis)}

### Retry Strategy
{retry_strategy}

### Timeout Configuration
{timeout_strategy}

## 🎯 Test Execution Patterns

### Smoke Tests
```bash
npx cypress run --spec "cypress/e2e/**/smoke*.cy.js" \\
  --env domain={domain},testType=smoke
```

### Regression Tests
```bash
npx cypress run --spec "cypress/e2e/**/regression*.cy.js" \\
  --env domain={domain},testType=regression
```

{_generate_domain_specific_test_patterns(domain, analysis)}

## 📊 Monitoring and Reporting

### Real-time Monitoring
```bash
# Enable performance monitoring
npx cypress run --env domain={domain},monitoring=true

# Enable detailed logging
DEBUG=cypress:* npx cypress run --env domain={domain}
```

### Custom Reporting
```bash
# Generate comprehensive reports
npx cypress run \\
  --reporter mochawesome \\
  --reporter-options reportDir=reports/{domain},overwrite=false
```"""


def _get_parallel_workers(analysis: Dict[str, Any]) -> int:
    """Get optimal number of parallel workers."""
    if analysis.get("performance_critical"):
        return 8  # More workers for performance-critical domains
    elif analysis.get("security_level") == "high":
        return 4  # Moderate parallelism for security domains
    else:
        return 6  # Standard parallelism


def _get_memory_strategy(analysis: Dict[str, Any]) -> str:
    """Get memory management strategy."""
    if analysis.get("performance_critical"):
        return "Aggressive cleanup with numTestsKeptInMemory=0"
    elif analysis.get("compliance_required"):
        return "Conservative with detailed logging"
    else:
        return "Balanced approach with numTestsKeptInMemory=1"


def _get_load_balancing_strategy(analysis: Dict[str, Any]) -> str:
    """Get load balancing strategy."""
    if analysis.get("security_level") == "high":
        return "Security-focused with isolated test execution"
    elif analysis.get("performance_critical"):
        return "Performance-optimized with smart test distribution"
    else:
        return "Standard load balancing"


def _get_retry_strategy(analysis: Dict[str, Any]) -> str:
    """Get retry strategy configuration."""
    if analysis.get("security_level") == "high":
        return """- **Run Mode**: 3 retries (security validations can be flaky)
- **Open Mode**: 0 retries (for debugging)
- **Strategy**: Exponential backoff with security validation"""
    elif analysis.get("performance_critical"):
        return """- **Run Mode**: 1 retry (fast feedback)
- **Open Mode**: 0 retries
- **Strategy**: Quick retry with performance monitoring"""
    else:
        return """- **Run Mode**: 2 retries (standard resilience)
- **Open Mode**: 0 retries
- **Strategy**: Standard retry with smart detection"""


def _get_timeout_strategy(analysis: Dict[str, Any]) -> str:
    """Get timeout strategy configuration."""
    if analysis.get("security_level") == "high":
        return """- **Command Timeout**: 12000ms (security operations take longer)
- **Request Timeout**: 15000ms (secure API calls)
- **Page Load**: 90000ms (security validations)"""
    elif analysis.get("performance_critical"):
        return """- **Command Timeout**: 6000ms (fast feedback)
- **Request Timeout**: 8000ms (quick API responses)
- **Page Load**: 30000ms (performance optimized)"""
    else:
        return """- **Command Timeout**: 8000ms (standard operations)
- **Request Timeout**: 10000ms (standard API calls)
- **Page Load**: 60000ms (standard loading)"""


def _generate_browser_commands(analysis: Dict[str, Any]) -> str:
    """Generate browser-specific commands."""
    commands = []

    if analysis.get("security_level") == "high":
        commands.append("# Security-optimized browsers")
        commands.append("npx cypress run --browser chrome --config chromeWebSecurity=false")
        commands.append("npx cypress run --browser firefox --config firefoxGcInterval=1")

    if analysis.get("performance_critical"):
        commands.append("# Performance-optimized browsers")
        commands.append("npx cypress run --browser chrome --config video=false")
        commands.append("npx cypress run --browser edge --config screenshotOnRunFailure=false")

    if not commands:
        commands = [
            "# Standard browser execution",
            "npx cypress run --browser chrome",
            "npx cypress run --browser firefox",
            "npx cypress run --browser edge"
        ]

    return "\n".join(commands)


def _generate_environment_commands(domain: str, analysis: Dict[str, Any]) -> str:
    """Generate environment-specific commands."""
    environments = ["dev", "staging", "prod"]

    commands = []
    for env in environments:
        if env == "prod" and analysis.get("security_level") == "high":
            commands.append(f"# {env.title()} environment (security-enhanced)")
            commands.append(f"npx cypress run --env domain={domain},environment={env},securityMode=true")
        else:
            commands.append(f"# {env.title()} environment")
            commands.append(f"npx cypress run --env domain={domain},environment={env}")

    return "\n".join(commands)


def _generate_domain_specific_test_patterns(domain: str, analysis: Dict[str, Any]) -> str:
    """Generate domain-specific test execution patterns."""
    patterns = []

    if analysis.get("security_level") == "high":
        patterns.append("""### Security Tests
```bash
npx cypress run --spec "cypress/e2e/**/security*.cy.js" \\
  --env domain={domain},testType=security,securityLevel=high
```""")

    if analysis.get("performance_critical"):
        patterns.append("""### Performance Tests
```bash
npx cypress run --spec "cypress/e2e/**/performance*.cy.js" \\
  --env domain={domain},testType=performance,monitoring=true
```""")

    if analysis.get("compliance_required"):
        patterns.append("""### Compliance Tests
```bash
npx cypress run --spec "cypress/e2e/**/compliance*.cy.js" \\
  --env domain={domain},testType=compliance,auditMode=true
```""")

    if analysis.get("privacy_level") == "maximum":
        patterns.append("""### Privacy Tests
```bash
npx cypress run --spec "cypress/e2e/**/privacy*.cy.js" \\
  --env domain={domain},testType=privacy,privacyMode=maximum
```""")

    return "\n\n".join(patterns).format(domain=domain)


def _generate_maintenance_guide(domain: str, analysis: Dict[str, Any]) -> str:
    """Generate maintenance guide based on domain needs."""

    return f"""# {domain.title()} Cypress Maintenance Guide

## 🔧 Regular Maintenance Tasks

### Daily Tasks
- Monitor test execution metrics
- Review failed tests and flaky patterns
- Update test data as needed
- Check performance benchmarks

### Weekly Tasks
- Review and update selectors
- Analyze test coverage reports
- Update dependencies and security patches
- Performance optimization review

### Monthly Tasks
- Comprehensive test suite audit
- Update test documentation
- Review domain-specific configurations
- Capacity planning for test infrastructure

## 🎯 Domain-Specific Maintenance

{_generate_domain_maintenance_tasks(domain, analysis)}

## 📈 Performance Optimization

### Test Execution Optimization
- Monitor test execution times
- Identify and eliminate flaky tests
- Optimize test data management
- Review parallel execution efficiency

### Resource Management
- Monitor memory usage during test runs
- Optimize browser resource consumption
- Manage test artifacts and cleanup
- Infrastructure scaling recommendations

## 🔍 Monitoring and Alerting

### Key Metrics to Track
{_generate_monitoring_metrics(analysis)}

### Alert Thresholds
{_generate_alert_thresholds(analysis)}

## 🛠️ Troubleshooting Common Issues

{_generate_troubleshooting_guide(domain, analysis)}"""


def _generate_domain_maintenance_tasks(domain: str, analysis: Dict[str, Any]) -> str:
    """Generate domain-specific maintenance tasks."""
    tasks = []

    if analysis.get("security_level") == "high":
        tasks.append("""### Security Maintenance
- Update security test scenarios monthly
- Review authentication token management
- Validate SSL/TLS certificate handling
- Audit security compliance coverage""")

    if analysis.get("performance_critical"):
        tasks.append("""### Performance Maintenance
- Benchmark performance baselines weekly
- Update performance thresholds quarterly
- Monitor Core Web Vitals trends
- Optimize test execution performance""")

    if analysis.get("compliance_required"):
        tasks.append("""### Compliance Maintenance
- Review compliance test coverage
- Update regulatory requirement tests
- Audit trail validation
- Documentation compliance checks""")

    if not tasks:
        tasks.append(f"""### Standard {domain.title()} Maintenance
- Review business logic test coverage
- Update user workflow validations
- Monitor application-specific metrics
- Maintain test data integrity""")

    return "\n\n".join(tasks)


def _generate_monitoring_metrics(analysis: Dict[str, Any]) -> str:
    """Generate monitoring metrics based on domain."""
    metrics = [
        "- Test execution time and success rate",
        "- Test flakiness and stability metrics",
        "- Resource utilization (CPU, memory)",
        "- Browser compatibility metrics"
    ]

    if analysis.get("performance_critical"):
        metrics.extend([
            "- Page load times and performance budgets",
            "- Core Web Vitals (LCP, FID, CLS)",
            "- Network request metrics"
        ])

    if analysis.get("security_level") == "high":
        metrics.extend([
            "- Security test coverage metrics",
            "- Authentication failure rates",
            "- Security scan results"
        ])

    return "\n".join(metrics)


def _generate_alert_thresholds(analysis: Dict[str, Any]) -> str:
    """Generate alert thresholds based on domain criticality."""
    thresholds = []

    if analysis.get("performance_critical"):
        thresholds.extend([
            "- Test execution time > 150% of baseline",
            "- Success rate < 95%",
            "- Page load time > 3 seconds"
        ])
    elif analysis.get("security_level") == "high":
        thresholds.extend([
            "- Test execution time > 200% of baseline",
            "- Success rate < 98%",
            "- Security test failures > 0"
        ])
    else:
        thresholds.extend([
            "- Test execution time > 200% of baseline",
            "- Success rate < 90%",
            "- Flaky test rate > 5%"
        ])

    return "\n".join(thresholds)


def _generate_troubleshooting_guide(domain: str, analysis: Dict[str, Any]) -> str:
    """Generate troubleshooting guide."""

    guide = f"""### Common {domain.title()} Issues

#### Test Flakiness
- **Symptom**: Intermittent test failures
- **Solution**: Implement proper wait strategies and retry logic
- **Prevention**: Use domain-specific loading indicators

#### Performance Issues
- **Symptom**: Slow test execution
- **Solution**: Optimize selectors and reduce unnecessary waits
- **Prevention**: Regular performance monitoring

#### Browser Compatibility
- **Symptom**: Tests fail on specific browsers
- **Solution**: Use cross-browser compatible selectors
- **Prevention**: Regular cross-browser testing"""

    if analysis.get("security_level") == "high":
        guide += """

#### Security-Specific Issues
- **Authentication Timeouts**: Implement token refresh logic
- **CORS Issues**: Configure proper security settings
- **SSL Certificate Issues**: Update certificate handling"""

    if analysis.get("performance_critical"):
        guide += """

#### Performance-Specific Issues
- **Slow Loading**: Implement performance budgets
- **Memory Leaks**: Monitor resource cleanup
- **Network Issues**: Implement network stubbing"""

    return guide


def _generate_performance_strategy(domain: str, analysis: Dict[str, Any]) -> Dict[str, str]:
    """Generate performance testing strategy."""

    if not analysis.get("performance_critical"):
        return {
            "strategy": "Basic performance monitoring with standard thresholds"
        }

    return {
        "performance_tests": f"""// cypress/e2e/performance/{domain}-performance.cy.js
describe('{domain.title()} Performance Tests', () => {{
    beforeEach(() => {{
        cy.visit('/');
    }});

    it('should meet performance budgets', () => {{
        cy.window().then((win) => {{
            const perfData = win.performance.getEntriesByType('navigation')[0];
            const loadTime = perfData.loadEventEnd - perfData.fetchStart;
            
            // Domain-specific performance thresholds
            expect(loadTime).to.be.lessThan(2000); // Strict for performance-critical
            
            // Core Web Vitals validation
            cy.getCLS().should('be.lessThan', 0.1);
            cy.getLCP().should('be.lessThan', 2500);
            cy.getFID().should('be.lessThan', 100);
        }});
    }});

    it('should handle concurrent users', () => {{
        // Simulate multiple user interactions
        cy.simulateConcurrentLoad(10);
        cy.validatePerformanceUnderLoad();
    }});
}});""",

        "lighthouse_config": f"""// lighthouse-{domain}.json
{{
  "extends": "lighthouse:default",
  "settings": {{
    "onlyCategories": ["performance"],
    "chromeFlags": ["--headless", "--no-sandbox"]
  }},
  "audits": [
    "first-contentful-paint",
    "largest-contentful-paint", 
    "cumulative-layout-shift",
    "total-blocking-time"
  ],
  "budgets": [
    {{
      "path": "/*",
      "timings": [
        {{"metric": "first-contentful-paint", "budget": 1500}},
        {{"metric": "largest-contentful-paint", "budget": 2500}}
      ]
    }}
  ]
}}"""
    }


def _generate_accessibility_strategy(domain: str, analysis: Dict[str, Any]) -> Dict[str, str]:
    """Generate accessibility testing strategy."""

    return {
        "a11y_tests": f"""// cypress/e2e/accessibility/{domain}-a11y.cy.js
describe('{domain.title()} Accessibility Tests', () => {{
    beforeEach(() => {{
        cy.visit('/');
        cy.injectAxe();
    }});

    it('should pass WCAG 2.1 AA standards', () => {{
        cy.checkA11y(null, {{
            runOnly: {{
                type: 'tag',
                values: ['wcag2a', 'wcag2aa']
            }}
        }});
    }});

    it('should be keyboard navigable', () => {{
        cy.get('body').tab();
        cy.focused().should('be.visible');
        
        // Domain-specific keyboard navigation tests
        cy.navigateByKeyboard();
        cy.validateKeyboardAccessibility();
    }});

    it('should have proper color contrast', () => {{
        cy.checkA11y(null, {{
            runOnly: {{
                type: 'rule',
                values: ['color-contrast']
            }}
        }});
    }});
}});""",

        "a11y_config": f"""// .axe-config.js - {domain} accessibility configuration
module.exports = {{
  rules: {{
    'color-contrast': {{ enabled: true }},
    'keyboard-navigation': {{ enabled: true }},
    'aria-labels': {{ enabled: true }},
    'heading-order': {{ enabled: true }},
    'landmark-roles': {{ enabled: true }}
  }},
  tags: ['wcag2a', 'wcag2aa', 'best-practice'],
  exclude: [
    ['[data-testid="skip-a11y"]']
  ]
}};"""
    }


def _generate_debugging_strategy(domain: str, analysis: Dict[str, Any]) -> str:
    """Generate debugging strategy guide."""

    return f"""# {domain.title()} Debugging Strategy

## 🔍 Debugging Approach

### Interactive Debugging
```bash
# Launch debug mode for {domain}
npx cypress open --env domain={domain},debugMode=true

# Debug specific test with domain context
npx cypress run --spec cypress/e2e/{domain}/*.cy.js --headed --no-exit
```

### Advanced Debugging Techniques
```javascript
// Domain-specific debugging helpers
cy.debugDomain('{domain}'); // Custom debugging command
cy.captureDomainState(); // Capture domain-specific state
cy.validateDomainContext(); // Validate domain context
```

### Performance Debugging
{_generate_performance_debugging_guide(analysis)}

### Security Debugging
{_generate_security_debugging_guide(analysis)}

## 🛠️ Debugging Tools Integration

### Chrome DevTools Integration
- Network monitoring for {domain} APIs
- Performance profiling
- Security analysis

### Custom Debugging Commands
- Domain-specific state inspection
- Business logic validation
- Error context capture"""


def _generate_performance_debugging_guide(analysis: Dict[str, Any]) -> str:
    """Generate performance debugging guide."""
    if analysis.get("performance_critical"):
        return """```javascript
// Performance debugging for critical domains
cy.measurePerformance().then((metrics) => {
    if (metrics.loadTime > 2000) {
        cy.debugPerformanceBottlenecks();
    }
});

// Memory leak detection
cy.detectMemoryLeaks();
cy.profileResourceUsage();
```"""
    else:
        return """```javascript
// Standard performance debugging
cy.checkPagePerformance();
cy.validateResponseTimes();
```"""


def _generate_security_debugging_guide(analysis: Dict[str, Any]) -> str:
    """Generate security debugging guide."""
    if analysis.get("security_level") == "high":
        return """```javascript
// Security debugging for high-security domains
cy.validateSecurityHeaders();
cy.checkCSPViolations();
cy.auditSecurityConfiguration();

// Authentication debugging
cy.debugAuthenticationFlow();
cy.validateTokenSecurity();
```"""
    else:
        return """```javascript
// Standard security debugging
cy.validateBasicSecurity();
cy.checkAuthenticationState();
```"""
