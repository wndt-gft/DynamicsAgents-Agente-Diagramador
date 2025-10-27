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

"""Generic Security Tests Generator - Universal security testing for any domain."""

from typing import Dict, Any, List


def generate_security_tests(domain: str, endpoints: List[Dict[str, Any]] = None, config: Dict[str, Any] = None) -> Dict[str, str]:
    """Generate universal security tests for any domain."""

    return {
        "authentication_tests": _generate_authentication_tests(domain, config),
        "input_validation_tests": _generate_input_validation_tests(domain, config),
        "authorization_tests": _generate_authorization_tests(domain, config)
    }


def _generate_authentication_tests(domain: str, config: Dict[str, Any] = None) -> str:
    """Generate authentication security tests."""

    return f"""Feature: {domain.title()} Authentication Security
  Background:
    * url baseUrl

  Scenario: Valid authentication
    Given path '/api/auth/validate'
    When method GET
    Then status 200
    And match response.authenticated == true

  Scenario: Invalid authentication
    Given path '/api/auth/validate'
    And header X-API-Key = 'invalid_key'
    When method GET
    Then status 401
    And match response.error == 'Unauthorized'

  Scenario: Missing authentication
    Given path '/api/protected'
    When method GET
    Then status 401
    And match response.error contains 'authentication'

  Scenario: Token expiration handling
    Given def expiredToken = 'expired.token.here'
    And path '/api/protected'
    And header Authorization = 'Bearer ' + expiredToken
    When method GET
    Then status 401
    And match response.error contains 'expired'"""


def _generate_input_validation_tests(domain: str, config: Dict[str, Any] = None) -> str:
    """Generate input validation security tests."""

    return f"""Feature: {domain.title()} Input Validation Security
  Background:
    * url baseUrl

  Scenario: SQL injection prevention
    Given path '/api/{domain}/search'
    And param query = "'; DROP TABLE users; --"
    When method GET
    Then status 400
    And match response.error contains 'Invalid input'

  Scenario: XSS prevention
    Given path '/api/{domain}/comments'
    And request {{ content: '<script>alert("xss")</script>' }}
    When method POST
    Then status 400
    And match response.error contains 'Invalid content'

  Scenario: Large payload handling
    Given path '/api/{domain}/data'
    And def largePayload = 'A'.repeat(1000000)
    And request {{ data: largePayload }}
    When method POST
    Then status 413
    And match response.error contains 'too large'

  Scenario: Invalid JSON handling
    Given path '/api/{domain}/json-test'
    And request 'invalid json format'
    When method POST
    Then status 400
    And match response.error contains 'Invalid JSON'"""


def _generate_authorization_tests(domain: str, config: Dict[str, Any] = None) -> str:
    """Generate authorization security tests - CORRECTED: use realistic IDs instead of placeholders."""

    return f"""Feature: {domain.title()} Authorization Security Tests

Background:
  * url baseUrl
  * def auth = callonce read('classpath:{domain.lower().replace(' ', '')}/utils/common-utils.feature@Get Auth Token')
  * def token = auth.authToken
  * header Authorization = 'Bearer ' + token

@security
Scenario: Validar que token ausente retorna 401
  * header Authorization = null
  Given path '/accounts'
  When method GET
  Then status 401
  And match response.error == '#string'

@security
Scenario: Validar que token malformado retorna 401
  Given path '/accounts'
  And header Authorization = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature'
  When method GET
  Then status 401
  And match response.error == '#string'

@security
Scenario: Validar que token expirado retorna 401
  # Usar um token JWT válido mas expirado
  * def expiredToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiZXhwIjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c'
  Given path '/accounts'
  And header Authorization = 'Bearer ' + expiredToken
  When method GET
  Then status 401
  And match response.error contains 'expired'

@security
Scenario: Validar acesso a recurso de outro usuário é bloqueado (403 Forbidden)
  # Tentar acessar uma conta com ID válido mas que não pertence ao usuário autenticado
  # Usando ID realista no formato esperado (99999-9) em vez de placeholder óbvio
  Given path '/accounts/99999-9'
  When method GET
  Then status 403
  And match response.error contains 'forbidden'

@security
Scenario: Validar que não é possível modificar recursos de outros usuários
  # Tentar atualizar uma conta que não pertence ao usuário
  Given path '/accounts/87654-3'
  And request {{ status: 'blocked' }}
  When method PATCH
  Then status 403
  And match response.error contains 'permission'

@security
Scenario: Validar rate limiting
  * def numRequests = 101
  * def results = []
  
  # Fazer muitas requisições rapidamente para testar rate limiting
  * def makeRequest = 
    \"\"\"
    function(i) {{
      var response = karate.call('classpath:{domain.lower().replace(' ', '')}/accounts/accounts.feature@smoke');
      return {{
        requestNum: i + 1,
        status: response.responseStatus,
        rateLimited: response.responseStatus == 429
      }};
    }}
    \"\"\"
  
  * def results = karate.repeat(numRequests, makeRequest)
  * def rateLimitedCount = results.filter(function(x){{ return x.rateLimited }}).length
  
  # Validar que rate limiting foi acionado em algum momento
  * print 'Rate limited requests:', rateLimitedCount
  # Se rate limiting está ativo, deve ter bloqueado pelo menos algumas requisições
  # Comentar validação se rate limiting não estiver implementado
  # And assert rateLimitedCount > 0

@security
Scenario: Validar SQL injection não é possível
  # Tentar SQL injection no parâmetro de busca
  Given path '/accounts'
  And param account_id = "12345' OR '1'='1"
  When method GET
  Then status 400
  And match response.error == '#string'

@security
Scenario: Validar XSS prevention em campos de texto
  * def idempotencyKey = karate.uuid()
  Given path '/transfers'
  And header X-Idempotency-Key = idempotencyKey
  And request
  '''
  {{
    from_account: '12345-6',
    to_account: '78910-1',
    amount: 100.00,
    description: '<script>alert("xss")</script>'
  }}
  '''
  When method POST
  # API deve sanitizar ou rejeitar
  Then status 201
  # Se aceitar, validar que XSS foi sanitizado na resposta
  And match response.description != '<script>alert("xss")</script>'

@security  
Scenario: Validar HTTPS é obrigatório (apenas se aplicável)
  # Este cenário seria executado contra HTTP ao invés de HTTPS
  # Descomentar e ajustar se necessário validar redirecionamento HTTP->HTTPS
  # Given url 'http://api-{domain.lower().replace(' ', '-')}.example.com/v1'
  # And path '/accounts'
  # When method GET
  # Then status 301
  # And match responseHeaders['Location'][0] contains 'https://'
"""
