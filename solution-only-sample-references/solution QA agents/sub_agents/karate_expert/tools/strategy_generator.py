"""Generic Execution Strategies Generator - FIXED."""

from typing import Dict, Any


def generate_execution_strategies(domain: str, complexity: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Generate universal execution strategies based on complexity."""

    strategy_map = {
        "simple": {
            "parallel_threads": 3,
            "test_timeout": 30000,
            "retry_count": 2,
            "execution_order": "sequential",
            "memory_allocation": "1g"
        },
        "medium": {
            "parallel_threads": 5,
            "test_timeout": 60000,
            "retry_count": 3,
            "execution_order": "parallel",
            "memory_allocation": "2g"
        },
        "complex": {
            "parallel_threads": 10,
            "test_timeout": 120000,
            "retry_count": 3,
            "execution_order": "optimized_parallel",
            "memory_allocation": "4g"
        },
        "enterprise": {
            "parallel_threads": 20,
            "test_timeout": 300000,
            "retry_count": 5,
            "execution_order": "distributed",
            "memory_allocation": "8g"
        }
    }

    base_strategy = strategy_map.get(complexity, strategy_map["medium"])

    # Apply custom configuration overrides if provided
    if config:
        for key, value in config.items():
            if key in base_strategy:
                base_strategy[key] = value

    # ✅ FIX: Pre-calculate domain variations BEFORE passing to functions
    domain_safe = domain.replace(' ', '_').lower()
    domain_title = domain.title()
    
    # Add execution guide
    base_strategy["execution_guide"] = _generate_execution_guide(domain, domain_safe, domain_title, base_strategy)
    base_strategy["troubleshooting_guide"] = _generate_troubleshooting_guide(domain, domain_safe, domain_title, base_strategy)

    return base_strategy


def _generate_execution_guide(domain: str, domain_safe: str, domain_title: str, strategy: Dict[str, Any]) -> str:
    """Generate execution guide for the strategy."""
    
    # ✅ FIX: Use pre-calculated variables
    parallel_threads = strategy['parallel_threads']
    test_timeout = strategy['test_timeout']
    retry_count = strategy['retry_count']
    execution_order = strategy['execution_order']
    memory_allocation = strategy['memory_allocation']
    fork_count = parallel_threads // 2

    return f"""# {domain_title} Karate Execution Guide

## Quick Start Commands

### Basic Execution
```bash
# Run all tests
mvn test -Ddomain={domain_safe}

# Run specific test suite
mvn test -Dkarate.options="--tags @smoke" -Ddomain={domain_safe}

# Run with specific environment
mvn test -Dkarate.env=test -Ddomain={domain_safe}
```

### Advanced Execution
```bash
# Parallel execution with {parallel_threads} threads
mvn test -Dkarate.options="--parallel {parallel_threads}" -Ddomain={domain_safe}

# Debug mode execution
mvn test -Dkarate.options="--tags @debug" -Ddomain={domain_safe}

# Performance testing
mvn test -Dkarate.options="--tags @performance" -Ddomain={domain_safe}
```

### Environment-Specific Execution
```bash
# Development environment
mvn test -Dkarate.env=dev -Ddomain={domain_safe}

# Test environment
mvn test -Dkarate.env=test -Ddomain={domain_safe}

# Staging environment
mvn test -Dkarate.env=staging -Ddomain={domain_safe}

# Production monitoring
mvn test -Dkarate.env=prod -Dkarate.options="--tags @smoke" -Ddomain={domain_safe}
```

## Configuration Parameters

- **Parallel Threads**: {parallel_threads}
- **Test Timeout**: {test_timeout}ms
- **Retry Count**: {retry_count}
- **Execution Order**: {execution_order}
- **Memory Allocation**: {memory_allocation}

## Performance Optimization

### JVM Tuning
```bash
export MAVEN_OPTS="-Xmx{memory_allocation} -XX:+UseG1GC -XX:+UseStringDeduplication"
mvn test -Ddomain={domain_safe}
```

### Parallel Optimization
```bash
# Optimal parallel execution for {domain}
mvn test -Dkarate.options="--parallel {parallel_threads}" \\
         -DforkCount={fork_count} \\
         -DreuseForks=true \\
         -Ddomain={domain_safe}
```"""


def _generate_troubleshooting_guide(domain: str, domain_safe: str, domain_title: str, strategy: Dict[str, Any]) -> str:
    """Generate troubleshooting guide."""
    
    # ✅ FIX: Use pre-calculated variables
    test_timeout = strategy['test_timeout']
    memory_allocation = strategy['memory_allocation']
    parallel_threads = strategy['parallel_threads']
    retry_count = strategy['retry_count']
    timeout_doubled = test_timeout * 2
    threads_halved = parallel_threads // 2

    return f"""# {domain_title} Karate Troubleshooting Guide

## Common Issues and Solutions

### Test Execution Issues
- **Timeout Errors**: Increase timeout to {timeout_doubled}ms
- **Memory Issues**: Increase heap size beyond {memory_allocation}
- **Connection Issues**: Check API availability and network connectivity

### Performance Issues
- **Slow Execution**: Reduce parallel threads from {parallel_threads} to {threads_halved}
- **Resource Exhaustion**: Monitor system resources and adjust memory allocation
- **Flaky Tests**: Implement retry logic with {retry_count} retries

### Debugging Commands
```bash
# Enable verbose logging
mvn test -Dkarate.options="--tags @debug" \\
         -Dlogback.configurationFile=logback-debug.xml \\
         -Ddomain={domain_safe}

# Run single feature
mvn test -Dtest=SingleFeatureTest \\
         -Dkarate.options="classpath:features/{domain_safe}/debug.feature" \\
         -Ddomain={domain_safe}

# Performance profiling
mvn test -Dkarate.options="--tags @performance" \\
         -XX:+FlightRecorder \\
         -Ddomain={domain_safe}
```

## Environment-Specific Troubleshooting

### Development Environment
- Verify local services are running
- Check test data setup
- Validate configuration files

### Test Environment
- Confirm environment variables
- Check service connectivity
- Verify authentication setup

### Production Environment
- Monitor real-time metrics
- Check SSL certificates
- Validate security configurations

## Best Practices for {domain_title}

1. **Test Organization**: Group related tests by functionality
2. **Data Management**: Use environment-specific test data
3. **Error Handling**: Implement comprehensive error scenarios
4. **Performance**: Monitor response times and throughput
5. **Maintenance**: Regular review and optimization of test suite"""