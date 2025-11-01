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

"""Professional Performance Tests Generator - Realistic performance testing."""

from typing import Dict, Any, List


def generate_performance_tests(domain: str, endpoints: List[Dict[str, Any]] = None, config: Dict[str, Any] = None) -> Dict[str, str]:
    """Generate professional performance tests with correct Karate syntax - CORRECTED."""

    config = config or {}
    num_requests = config.get("num_requests", 50)
    domain_lower = domain.lower().replace(' ', '')

    return {
        "load_tests": _generate_load_tests(domain, domain_lower, num_requests),
        "stress_tests": _generate_stress_tests(domain, domain_lower, num_requests),
        "endurance_tests": _generate_endurance_tests(domain, domain_lower, num_requests),
        "performance_readme": _generate_performance_readme(domain)
    }


def _generate_load_tests(domain: str, domain_lower: str, num_requests: int) -> str:
    """Generate load testing scenarios with correct Karate syntax - uses karate.repeat() only."""

    return f"""Feature: {domain} Load Testing

Background:
  * url baseUrl
  * def auth = callonce read('classpath:{domain_lower}/utils/common-utils.feature@Get Auth Token')
  * def token = auth.authToken
  * header Authorization = 'Bearer ' + token

@performance @load
Scenario: Load test para listagem de contas - {num_requests} requisições
  * def results = []
  * def numRequests = {num_requests}
  
  # Função para fazer requisição e medir tempo
  * def makeRequest = 
    \"\"\"
    function(i) {{
      var start = new Date().getTime();
      var response = karate.call('classpath:{domain_lower}/accounts/accounts.feature@smoke');
      var end = new Date().getTime();
      return {{
        requestNum: i + 1,
        responseTime: end - start,
        status: response.responseStatus
      }};
    }}
    \"\"\"
  
  # Executar requisições sequencialmente e coletar métricas
  * def results = karate.repeat(numRequests, makeRequest)
  
  # Calcular estatísticas de performance
  * def responseTimes = karate.map(results, function(x){{ return x.responseTime }})
  * def avgTime = responseTimes.reduce(function(a,b){{ return a+b }}, 0) / responseTimes.length
  * def maxTime = Math.max.apply(null, responseTimes)
  * def minTime = Math.min.apply(null, responseTimes)
  * def successCount = results.filter(function(x){{ return x.status == 200 }}).length
  * def successRate = (successCount / numRequests) * 100
  
  # Exibir métricas
  * print '================================='
  * print 'LOAD TEST METRICS'
  * print '================================='
  * print 'Total Requests:', numRequests
  * print 'Success Rate:', successRate, '%'
  * print 'Average Response Time:', Math.round(avgTime), 'ms'
  * print 'Max Response Time:', maxTime, 'ms'
  * print 'Min Response Time:', minTime, 'ms'
  * print '================================='
  
  # Validações de performance (Avg < 1.5s, Max < 3s, Success Rate >= 95%)
  And assert avgTime < 1500
  And assert maxTime < 3000
  And assert successRate >= 95.0
"""


def _generate_stress_tests(domain: str, domain_lower: str, num_requests: int) -> str:
    """Generate stress testing scenarios - CORRECTED: no karate.parallel()."""

    stress_requests = num_requests * 2

    return f"""Feature: {domain} Stress Testing

Background:
  * url baseUrl
  * def auth = callonce read('classpath:{domain_lower}/utils/common-utils.feature@Get Auth Token')
  * def token = auth.authToken
  * header Authorization = 'Bearer ' + token

@performance @stress
Scenario: Stress test com {stress_requests} requisições
  * def numRequests = {stress_requests}
  
  * def makeRequest = 
    \"\"\"
    function(i) {{
      var start = new Date().getTime();
      var response = karate.call('classpath:{domain_lower}/accounts/accounts.feature@smoke');
      var end = new Date().getTime();
      return {{
        requestNum: i + 1,
        responseTime: end - start,
        status: response.responseStatus,
        isError: response.responseStatus >= 500
      }};
    }}
    \"\"\"
  
  * def results = karate.repeat(numRequests, makeRequest)
  
  # Calcular métricas
  * def errorCount = results.filter(function(x){{ return x.isError }}).length
  * def errorRate = (errorCount / numRequests) * 100
  * def responseTimes = karate.map(results, function(x){{ return x.responseTime }})
  * def avgTime = responseTimes.reduce(function(a,b){{ return a+b }}, 0) / responseTimes.length
  
  * print '================================='
  * print 'STRESS TEST METRICS'
  * print '================================='
  * print 'Total Requests:', numRequests
  * print 'Server Errors (5xx):', errorCount
  * print 'Error Rate:', errorRate, '%'
  * print 'Average Response Time:', Math.round(avgTime), 'ms'
  * print '================================='
  
  # Em stress test, toleramos até 10% de erros de servidor
  And assert errorRate < 10.0
  And assert avgTime < 3000
"""


def _generate_endurance_tests(domain: str, domain_lower: str, num_requests: int) -> str:
    """Generate endurance/soak testing scenarios - CORRECTED."""

    endurance_requests = num_requests * 10

    return f"""Feature: {domain} Endurance Testing

Background:
  * url baseUrl
  * def auth = callonce read('classpath:{domain_lower}/utils/common-utils.feature@Get Auth Token')
  * def token = auth.authToken
  * header Authorization = 'Bearer ' + token

@performance @endurance
Scenario: Endurance test - {endurance_requests} requisições com intervalos
  * def numRequests = {endurance_requests}
  
  * def makeRequest = 
    \"\"\"
    function(i) {{
      # Pausa entre requisições para simular uso real
      if (i > 0 && i % 50 == 0) {{
        java.lang.Thread.sleep(1000);
        karate.log('Processed', i, 'requests...');
      }}
      var response = karate.call('classpath:{domain_lower}/accounts/accounts.feature@smoke');
      return {{
        requestNum: i + 1,
        status: response.responseStatus,
        failed: response.responseStatus != 200
      }};
    }}
    \"\"\"
  
  * def results = karate.repeat(numRequests, makeRequest)
  
  # Contar falhas
  * def failures = results.filter(function(x){{ return x.failed }})
  * def failureRate = (failures.length / numRequests) * 100
  
  * print '================================='
  * print 'ENDURANCE TEST METRICS'
  * print '================================='
  * print 'Total Requests:', numRequests
  * print 'Failed Requests:', failures.length
  * print 'Failure Rate:', failureRate, '%'
  * print '================================='
  
  # Endurance test deve ter taxa de sucesso de 99%+
  And assert failureRate < 1.0
"""


def _generate_performance_readme(domain: str) -> str:
    """Generate README explaining performance testing limitations and how to use Gatling."""

    return f"""# {domain} Performance Testing Guide

## Overview

This folder contains performance tests for the {domain} API. The tests use Karate's built-in capabilities with `karate.repeat()` and `karate.call()` for sequential load testing.

## Important Notes

### Current Implementation
- **Sequential Testing**: Tests use `karate.repeat()` which executes requests sequentially
- **Good for**: Smoke performance tests, basic load validation, CI/CD pipelines
- **Limitations**: Cannot simulate true concurrent load, limited throughput

### For True Load Testing

For production-grade performance testing with concurrent users and high throughput, you need **Karate + Gatling integration**:

#### 1. Create Gatling Simulation Class

```java
// src/test/java/performance/{domain}LoadSimulation.java
package performance;

import com.intuit.karate.gatling.PreDef.*;
import io.gatling.core.Predef.*;
import scala.concurrent.duration.DurationInt;

public class {domain.replace(' ', '')}LoadSimulation extends Simulation {{

  // Define protocol
  var protocol = karateProtocol();

  // Define scenarios
  var listAccounts = scenario("List Accounts")
    .exec(karateFeature("classpath:{domain.lower().replace(' ', '')}/accounts/accounts.feature@smoke"));

  var createTransfer = scenario("Create Transfer")
    .exec(karateFeature("classpath:{domain.lower().replace(' ', '')}/transfers/transfers.feature@smoke"));

  // Setup load profile
  setUp(
    listAccounts.inject(
      rampUsers(50).during(30) // 50 users over 30 seconds
    ),
    createTransfer.inject(
      constantUsersPerSec(10).during(60) // 10 users/sec for 60 seconds
    )
  ).protocols(protocol)
   .assertions(
     global().responseTime().percentile(95).lt(1500), // P95 < 1.5s
     global().successfulRequests().percent().gt(95)    // 95% success rate
   );
}}
```

#### 2. Run Gatling Tests

```bash
# Run specific simulation
mvn gatling:test -Dgatling.simulationClass=performance.{domain.replace(' ', '')}LoadSimulation

# Run all Gatling simulations
mvn clean gatling:test
```

#### 3. View Reports

Gatling generates detailed HTML reports in `target/gatling/` with:
- Response time percentiles (P50, P95, P99)
- Throughput (requests/second)
- Error rates
- Timeline charts

## Running Current Tests

### Sequential Load Tests (CI/CD friendly)

```bash
# Run all performance tests
mvn test -Dkarate.env=dev -Dtest=**/*Test.java -Dkarate.options="--tags @performance"

# Run specific performance test
mvn test -Dkarate.options="--tags @load"
mvn test -Dkarate.options="--tags @stress"
mvn test -Dkarate.options="--tags @endurance"
```

### Using Maven Surefire Parallel Execution

For moderate parallelism without Gatling:

```bash
# Run tests with 5 parallel threads
mvn test -Dkarate.options="--tags @performance" \\
         -DforkCount=5 \\
         -DreuseForks=false
```

## Performance Metrics Thresholds

| Test Type | Metric | Threshold |
|-----------|--------|-----------|
| Load Test | Average Response Time | < 1500ms |
| Load Test | Max Response Time | < 3000ms |
| Load Test | Success Rate | >= 95% |
| Stress Test | Server Error Rate (5xx) | < 10% |
| Stress Test | Average Response Time | < 3000ms |
| Endurance Test | Failure Rate | < 1% |

## Best Practices

1. **CI/CD**: Use sequential tests (@load, @stress) for quick feedback
2. **Pre-Production**: Use Gatling simulations for realistic load testing
3. **Monitoring**: Always monitor server resources (CPU, memory, connections) during tests
4. **Baseline**: Establish performance baselines before making changes
5. **Incremental Load**: Start with low load and gradually increase

## References

- [Karate Performance Testing](https://github.com/karatelabs/karate#performance-testing)
- [Karate Gatling Integration](https://github.com/karatelabs/karate/tree/master/karate-gatling)
- [Gatling Documentation](https://gatling.io/docs/current/)
"""
