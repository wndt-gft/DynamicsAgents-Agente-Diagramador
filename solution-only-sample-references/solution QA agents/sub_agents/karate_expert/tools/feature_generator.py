"""Professional Karate Feature Generator - IMPROVED with validator compliance."""

from typing import Dict, Any, List
import json


def generate_karate_features(
    api_description: str,
    endpoints: List[Dict[str, Any]],
    test_scenarios: List[str],
    domain: str,
    complexity: str,
    custom_config: Dict[str, Any] = None
) -> Dict[str, str]:
    """Generate professional Karate features following best practices."""

    config = custom_config or {}

    # Generate separate feature files following best practices
    features = {
        "auth_feature": _generate_auth_feature(domain, config),
        "common_utils_feature": _generate_common_utils(domain, config),
        "main_api_feature": _generate_main_api_feature(
            api_description, endpoints, test_scenarios, domain, complexity, config
        ),
        "payments_bills_feature": _generate_payments_bills_feature(domain, [], config),
        "statements_complete_feature": _generate_statements_complete_feature(domain, [], config),
        "security_feature": _generate_security_tests(domain, config),
        "e2e_feature": _generate_e2e_tests(domain, endpoints, config)
    }

    return features


def _generate_auth_feature(domain: str, config: Dict[str, Any]) -> str:
    """Generate professional authentication feature - CORRECTED."""
    
    domain_safe = domain.replace(' ', '_').lower()

    return f"""Feature: {domain} Authentication

Background:
  * url baseUrl
  # Variables come from karate-config.js
  * def credentials = {{ username: username, password: password }}

@smoke
Scenario: Login com credenciais válidas
  Given path '/auth/login'
  And request credentials
  When method POST
  Then status 200
  And match response == 
  '''
  {{
    access_token: '#string',
    token_type: 'Bearer',
    expires_in: '#number',
    refresh_token: '#string'
  }}
  '''
  # Validar formato JWT (3 partes separadas por ponto)
  And match response.access_token == '#regex ^[a-zA-Z0-9-_]+\\.[a-zA-Z0-9-_]+\\.[a-zA-Z0-9-_]+$'
  And assert response.expires_in > 0
  And match responseTime < 2000

@negative
Scenario: Login com credenciais inválidas
  Given path '/auth/login'
  And request {{ username: 'invalid@example.com', password: 'wrong' }}
  When method POST
  Then status 401
  And match response.error == '#string'

@negative
Scenario: Login sem username
  Given path '/auth/login'
  And request {{ password: 'test123' }}
  When method POST
  Then status 400
  And match response.error contains 'username'

@negative
Scenario: Login sem password
  Given path '/auth/login'
  And request {{ username: 'test@example.com' }}
  When method POST
  Then status 400
  And match response.error contains 'password'

@negative
Scenario: Login com body vazio
  Given path '/auth/login'
  And request {{}}
  When method POST
  Then status 400
  And match response.error == '#string'
"""


def _generate_common_utils(domain: str, config: Dict[str, Any]) -> str:
    """Generate reusable utilities feature - CORRECTED."""
    
    domain_safe = domain.replace(' ', '_').lower()

    return f"""Feature: {domain} Common Utilities

@ignore
Scenario: Get Auth Token
  Given url baseUrl
  And path '/auth/login'
  # Variables come from karate-config.js
  And request {{ username: username, password: password }}
  When method POST
  Then status 200
  * def authToken = response.access_token
  * def tokenType = response.token_type
  * def expiresIn = response.expires_in

@ignore
Scenario: Helper Functions
  * def generateUUID = function(){{ return java.util.UUID.randomUUID().toString() }}
  * def generateTimestamp = function(){{ return new java.util.Date().getTime() }}
  * def generateRandomAmount = function(min, max){{ return Math.floor(Math.random() * (max - min + 1) + min) }}
  * def formatCurrency = function(amount){{ return 'R$ ' + amount.toFixed(2).replace('.', ',') }}
  * def sleep = function(ms){{ java.lang.Thread.sleep(ms) }}
  
@ignore  
Scenario: Validate CPF
  * def validateCPF = 
  \"\"\"
  function(cpf) {{
    var cleaned = cpf.replace(/[^\\d]/g, '');
    if (cleaned.length !== 11) return false;
    
    var sum = 0;
    for (var i = 0; i < 9; i++) {{
      sum += parseInt(cleaned.charAt(i)) * (10 - i);
    }}
    var digit1 = 11 - (sum % 11);
    if (digit1 >= 10) digit1 = 0;
    
    sum = 0;
    for (var i = 0; i < 10; i++) {{
      sum += parseInt(cleaned.charAt(i)) * (11 - i);
    }}
    var digit2 = 11 - (sum % 11);
    if (digit2 >= 10) digit2 = 0;
    
    return digit1 == parseInt(cleaned.charAt(9)) && digit2 == parseInt(cleaned.charAt(10));
  }}
  \"\"\"
"""


def _generate_main_api_feature(
    api_description: str,
    endpoints: List[Dict[str, Any]],
    test_scenarios: List[str],
    domain: str,
    complexity: str,
    config: Dict[str, Any]
) -> str:
    """Generate main API tests - IMPROVED with complete coverage."""

    # Extract endpoint groups
    auth_endpoints = [e for e in endpoints if 'auth' in e.get('path', '').lower()]
    account_endpoints = [e for e in endpoints if 'account' in e.get('path', '').lower()]
    transfer_endpoints = [e for e in endpoints if 'transfer' in e.get('path', '').lower()]
    payment_endpoints = [e for e in endpoints if 'payment' in e.get('path', '').lower() or 'bill' in e.get('path', '').lower()]
    statement_endpoints = [e for e in endpoints if 'statement' in e.get('path', '').lower()]

    features = {}

    # Generate accounts feature
    features['accounts_feature'] = _generate_accounts_feature(domain, account_endpoints or [], config)

    # Generate transfers feature
    features['transfers_feature'] = _generate_transfers_feature(domain, transfer_endpoints or [], config)

    # Generate payments feature
    features['payments_bills_feature'] = _generate_payments_bills_feature(domain, payment_endpoints or [], config)

    # Generate statements feature
    features['statements_feature'] = _generate_statements_complete_feature(domain, statement_endpoints or [], config)

    # Generate generic feature for other endpoints
    other_endpoints = [e for e in endpoints
                      if e not in auth_endpoints + account_endpoints + transfer_endpoints + payment_endpoints + statement_endpoints]
    if other_endpoints:
        features['api_feature'] = _generate_generic_api_feature(
            api_description, other_endpoints, test_scenarios, domain, config
        )

    # Return combined features as string
    return "\n\n# ==========================================\n\n".join(
        [f"# File: {name}\n{content}" for name, content in features.items()]
    )


def _generate_accounts_feature(domain: str, endpoints: List[Dict[str, Any]], config: Dict[str, Any]) -> str:
    """Generate accounts API feature - CORRECTED with flexible validation."""
    
    domain_safe = domain.replace(' ', '_').lower()

    return f"""Feature: {domain} Accounts API

Background:
  * url baseUrl
  * def authResult = callonce read('classpath:{domain_safe}/utils/common-utils.feature@Get Auth Token')
  * def token = authResult.authToken
  * header Authorization = 'Bearer ' + token

@smoke
Scenario: Listar todas as contas do usuário
  Given path '/accounts'
  When method GET
  Then status 200
  And match response.accounts == '#[]'
  And match each response.accounts ==
  '''
  {{
    account_id: '#string',
    account_type: '#regex (checking|savings)',
    balance: '#number',
    currency: '#regex (BRL|USD|EUR)',
    status: '#regex (active|inactive|suspended|blocked)'
  }}
  '''
  And match responseTime < 3000

@regression
Scenario: Buscar detalhes de uma conta específica
  Given path '/accounts/12345-6'
  When method GET
  Then status 200
  And match response ==
  '''
  {{
    account_id: '#string',
    account_type: '#string',
    balance: '#number',
    currency: '#string',
    status: '#regex (active|inactive|suspended|blocked)',
    owner: {{
      name: '#string',
      cpf: '#string'
    }},
    created_at: '#string'
  }}
  '''
  # Validações específicas com regex
  And match response.owner.cpf == '#regex \\\\d{{3}}\\\\.\\\\d{{3}}\\\\.\\\\d{{3}}-\\\\d{{2}}'
  And match response.created_at == '#regex \\\\d{{4}}-\\\\d{{2}}-\\\\d{{2}}T\\\\d{{2}}:\\\\d{{2}}:\\\\d{{2}}Z'
  And assert response.balance >= 0

@negative
Scenario: Buscar conta inexistente
  Given path '/accounts/99999-9'
  When method GET
  Then status 404
  And match response.error == '#string'

@negative
Scenario: Buscar conta sem autenticação
  * header Authorization = null
  Given path '/accounts/12345-6'
  When method GET
  Then status 401

@negative
Scenario: Buscar conta de outro usuário
  Given path '/accounts/87654-3'
  When method GET
  Then status 403
  And match response.error contains 'forbidden'

@smoke @transactions
Scenario: Listar transações com paginação
  Given path '/accounts/12345-6/transactions'
  And params {{ page: 1, limit: 10 }}
  When method GET
  Then status 200
  And match response.transactions == '#[]'
  And match response.pagination ==
  '''
  {{
    current_page: '#number',
    total_pages: '#number',
    total_items: '#number',
    per_page: '#number'
  }}
  '''
  And match each response.transactions ==
  '''
  {{
    transaction_id: '#string',
    type: '#regex (credit|debit)',
    amount: '#number',
    description: '#string',
    date: '#string',
    balance_after: '#number'
  }}
  '''
  # Validar formato ISO-8601 nas datas
  And match each response.transactions contains {{ date: '#? karate.match(_, "#regex \\\\d{{4}}-\\\\d{{2}}-\\\\d{{2}}T\\\\d{{2}}:\\\\d{{2}}:\\\\d{{2}}Z").pass' }}
  # Validar ordenação decrescente por data
  * def dates = karate.map(response.transactions, function(x){{ return new Date(x.date).getTime() }})
  * def isSortedDesc = true
  * eval for(var i=0; i<dates.length-1; i++) if(dates[i] < dates[i+1]) isSortedDesc = false
  And assert isSortedDesc == true

@negative @transactions
Scenario: Listar transações com página inválida
  Given path '/accounts/12345-6/transactions'
  And params {{ page: -1, limit: 10 }}
  When method GET
  Then status 400
  And match response.error contains 'page'

@negative @transactions
Scenario: Listar transações sem autenticação
  * header Authorization = null
  Given path '/accounts/12345-6/transactions'
  And params {{ page: 1, limit: 10 }}
  When method GET
  Then status 401
"""


def _generate_transfers_feature(domain: str, endpoints: List[Dict[str, Any]], config: Dict[str, Any]) -> str:
    """Generate transfers API feature - CORRECTED."""
    
    domain_safe = domain.replace(' ', '_').lower()

    return f"""Feature: {domain} Transfers API

Background:
  * url baseUrl
  * def authResult = callonce read('classpath:{domain_safe}/utils/common-utils.feature@Get Auth Token')
  * def token = authResult.authToken
  * header Authorization = 'Bearer ' + token

@smoke
Scenario: Realizar transferência simples
  * def idempotencyKey = karate.uuid()
  Given path '/transfers'
  And header X-Idempotency-Key = idempotencyKey
  And request
  '''
  {{
    from_account: '12345-6',
    to_account: '78910-1',
    amount: 100.00,
    description: 'Teste de transferência'
  }}
  '''
  When method POST
  Then status 201
  And match response ==
  '''
  {{
    transfer_id: '#string',
    status: '#regex (completed|pending|processing)',
    amount: 100.00,
    from_account: '12345-6',
    to_account: '78910-1'
  }}
  '''
  And match responseTime < 3000

@regression
Scenario: Consultar status de transferência existente
  # Criar transferência
  * def idempotencyKey = karate.uuid()
  Given path '/transfers'
  And header X-Idempotency-Key = idempotencyKey
  And request {{ from_account: '12345-6', to_account: '78910-1', amount: 50.00 }}
  When method POST
  Then status 201
  * def transferId = response.transfer_id
  
  # Consultar status
  Given path '/transfers/', transferId
  When method GET
  Then status 200
  And match response ==
  '''
  {{
    transfer_id: '#string',
    status: '#regex (pending|processing|completed|failed|cancelled)',
    from_account: '12345-6',
    to_account: '78910-1',
    amount: 50.00,
    fee: '#number',
    created_at: '#string',
    completed_at: '##string'
  }}
  '''

@negative
Scenario: Consultar transferência inexistente
  Given path '/transfers/99999-9999-9999'
  When method GET
  Then status 404
  And match response.error == '#string'

@negative
Scenario: Transferência sem autenticação
  * header Authorization = null
  Given path '/transfers'
  And request {{ from_account: '12345-6', to_account: '78910-1', amount: 100.00 }}
  When method POST
  Then status 401

@negative
Scenario: Transferência com valor negativo
  * def idempotencyKey = karate.uuid()
  Given path '/transfers'
  And header X-Idempotency-Key = idempotencyKey
  And request {{ from_account: '12345-6', to_account: '78910-1', amount: -100.00 }}
  When method POST
  Then status 400
  And match response.error contains 'amount'

@negative
Scenario: Transferência com conta destino inválida
  * def idempotencyKey = karate.uuid()
  Given path '/transfers'
  And header X-Idempotency-Key = idempotencyKey
  And request {{ from_account: '12345-6', to_account: 'invalid', amount: 100.00 }}
  When method POST
  Then status 404
  And match response.error == '#string'

@regression
Scenario: Validar idempotência
  * def idempotencyKey = karate.uuid()
  * def transferRequest = {{ from_account: '12345-6', to_account: '78910-1', amount: 50.00 }}
  
  # Primeira requisição
  Given path '/transfers'
  And header X-Idempotency-Key = idempotencyKey
  And request transferRequest
  When method POST
  Then status 201
  * def firstTransferId = response.transfer_id
  
  # Segunda requisição com mesma chave
  Given path '/transfers'
  And header X-Idempotency-Key = idempotencyKey
  And request transferRequest
  When method POST
  Then status 200
  And match response.transfer_id == firstTransferId
"""


def _generate_generic_api_feature(
    api_description: str,
    endpoints: List[Dict[str, Any]],
    test_scenarios: List[str],
    domain: str,
    config: Dict[str, Any]
) -> str:
    """Generate generic API feature with complete negative scenarios."""
    
    domain_safe = domain.replace(' ', '_').lower()

    scenario_tests = []

    for i, scenario in enumerate(test_scenarios[:3]):
        # Positive scenario
        scenario_tests.append(f"""
@smoke
Scenario: {scenario} - Success
  Given path '/api/resource'
  When method GET
  Then status 200
  And match response == '#object'
  And match responseTime < 5000
""")
        
        # Negative scenarios
        scenario_tests.append(f"""
@negative
Scenario: {scenario} - Not found
  Given path '/api/resource/99999-9'
  When method GET
  Then status 404
  And match response.error == '#string'

@negative
Scenario: {scenario} - Unauthorized
  * header Authorization = null
  Given path '/api/resource'
  When method GET
  Then status 401
""")

    return f"""Feature: {api_description}

Background:
  * url baseUrl
  * def authResult = callonce read('classpath:{domain_safe}/utils/common-utils.feature@Get Auth Token')
  * def token = authResult.authToken
  * header Authorization = 'Bearer ' + token

{"".join(scenario_tests)}
"""


def _generate_security_tests(domain: str, config: Dict[str, Any]) -> str:
    """Generate professional security tests with realistic IDs."""
    
    domain_safe = domain.replace(' ', '_').lower()

    return f"""Feature: {domain} Security Tests

Background:
  * url baseUrl

@security
Scenario: Token ausente retorna 401
  Given path '/accounts'
  When method GET
  Then status 401
  And match response.error == '#string'

@security
Scenario: Token malformado retorna 401
  Given path '/accounts'
  And header Authorization = 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature'
  When method GET
  Then status 401

@security
Scenario: Token expirado retorna 401
  * def expiredToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiZXhwIjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c'
  Given path '/accounts'
  And header Authorization = 'Bearer ' + expiredToken
  When method GET
  Then status 401
  And match response.error contains 'expired'

@security
Scenario: Acesso a recurso de outro usuário bloqueado
  * def authResult = callonce read('classpath:{domain_safe}/utils/common-utils.feature@Get Auth Token')
  * def token = authResult.authToken
  * header Authorization = 'Bearer ' + token
  
  # Usar ID realista (não placeholder óbvio)
  Given path '/accounts/99999-9'
  When method GET
  Then status 403
  And match response.error contains 'forbidden'

@security
Scenario: SQL Injection não é possível
  * def authResult = callonce read('classpath:{domain_safe}/utils/common-utils.feature@Get Auth Token')
  * def token = authResult.authToken
  * header Authorization = 'Bearer ' + token
  
  Given path '/accounts'
  And param search = "'; DROP TABLE accounts; --"
  When method GET
  Then status 400
  And match response.error == '#string'

@security
Scenario: XSS prevention em campos de texto
  * def authResult = callonce read('classpath:{domain_safe}/utils/common-utils.feature@Get Auth Token')
  * def token = authResult.authToken
  * header Authorization = 'Bearer ' + token
  
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
  Then status 201
  # Validar que XSS foi sanitizado
  And match response.description != '<script>alert("xss")</script>'
"""


def _generate_e2e_tests(domain: str, endpoints: List[Dict[str, Any]], config: Dict[str, Any]) -> str:
    """Generate E2E flow test with preconditions."""

    return f"""Feature: {domain} E2E Flow Tests

Background:
  * url baseUrl

@e2e @smoke
Scenario: Fluxo completo de operação com todas preconditions
  
  # Precondition 1: Autenticar
  Given path '/auth/login'
  And request {{ username: username, password: password }}
  When method POST
  Then status 200
  * def token = response.access_token
  
  # Precondition 2: Listar recursos disponíveis
  * header Authorization = 'Bearer ' + token
  Given path '/accounts'
  When method GET
  Then status 200
  * def accounts = response.accounts
  And match accounts == '#[]'
  And match accounts.length > 0
  
  # Precondition 3: Obter detalhes do primeiro recurso
  * def firstAccount = accounts[0]
  Given path '/accounts/', firstAccount.account_id
  When method GET
  Then status 200
  And match response.account_id == firstAccount.account_id
  And match response.status == '#regex (active|inactive|blocked)'
  
  # Main Action: Realizar operação
  * def idempotencyKey = karate.uuid()
  Given path '/transfers'
  And header X-Idempotency-Key = idempotencyKey
  And request {{ from_account: firstAccount.account_id, to_account: '78910-1', amount: 10.00 }}
  When method POST
  Then status 201
  And match response.transfer_id == '#string'
  And match response.status == '#regex (completed|pending|processing)'
  
  # Validation: Verificar que operação foi concluída
  * print 'E2E test completed successfully'
"""


def _generate_payments_bills_feature(domain: str, endpoints: List[Dict[str, Any]], config: Dict[str, Any]) -> str:
    """Generate payments/bills API feature - COMPLETE with all negative scenarios."""
    
    domain_safe = domain.replace(' ', '_').lower()

    return f"""Feature: {domain} Payments and Bills API

Background:
  * url baseUrl
  * def authResult = callonce read('classpath:{domain_safe}/utils/common-utils.feature@Get Auth Token')
  * def token = authResult.authToken
  * header Authorization = 'Bearer ' + token

@smoke @payments
Scenario: Pagar conta com código de barras válido (47 dígitos)
  * def validBarcode = '34191790010104351004791020150008291070026000'
  And assert validBarcode.length == 47
  
  Given path '/payments/bills'
  And request
  '''
  {{
    account_id: '12345-6',
    barcode: '#(validBarcode)',
    amount: 150.75
  }}
  '''
  When method POST
  Then status 201
  And match response ==
  '''
  {{
    payment_id: '#string',
    status: '#regex (completed|pending|processing)',
    amount: 150.75,
    barcode: '#(validBarcode)',
    receipt_url: '#string'
  }}
  '''
  And match response.receipt_url == '#regex ^https?://.+'
  And match responseTime < 3000

@negative @payments
Scenario: Código de barras inválido (menos de 47 dígitos)
  * def invalidBarcode = '00000000000000000000000'
  And assert invalidBarcode.length < 47
  
  Given path '/payments/bills'
  And request {{ account_id: '12345-6', barcode: '#(invalidBarcode)', amount: 100.00 }}
  When method POST
  Then status 400
  And match response.error contains 'barcode'
  And match response.error contains '47'

@negative @payments
Scenario: Saldo insuficiente
  Given path '/payments/bills'
  And request {{ account_id: '12345-6', barcode: '34191790010104351004791020150008291070026000', amount: 999999.99 }}
  When method POST
  Then status 422
  And match response.error contains 'saldo'

@negative @payments
Scenario: Pagamento sem autenticação
  * header Authorization = null
  Given path '/payments/bills'
  And request {{ account_id: '12345-6', barcode: '34191790010104351004791020150008291070026000', amount: 100.00 }}
  When method POST
  Then status 401

@negative @payments
Scenario: Pagamento com valor negativo
  Given path '/payments/bills'
  And request {{ account_id: '12345-6', barcode: '34191790010104351004791020150008291070026000', amount: -50.00 }}
  When method POST
  Then status 400
  And match response.error contains 'amount'

@negative @payments
Scenario: Pagamento sem account_id
  Given path '/payments/bills'
  And request {{ barcode: '34191790010104351004791020150008291070026000', amount: 100.00 }}
  When method POST
  Then status 400
  And match response.error contains 'account'
"""


def _generate_statements_complete_feature(domain: str, endpoints: List[Dict[str, Any]], config: Dict[str, Any]) -> str:
    """Generate statements API feature - COMPLETE with all negative scenarios."""
    
    domain_safe = domain.replace(' ', '_').lower()

    return f"""Feature: {domain} Account Statements API

Background:
  * url baseUrl
  * def authResult = callonce read('classpath:{domain_safe}/utils/common-utils.feature@Get Auth Token')
  * def token = authResult.authToken
  * header Authorization = 'Bearer ' + token

@smoke @statements
Scenario: Gerar extrato de 30 dias em formato JSON
  Given path '/statements/12345-6'
  And params {{ start_date: '2024-10-01', end_date: '2024-10-31', format: 'json' }}
  When method GET
  Then status 200
  And match response ==
  '''
  {{
    account_id: '12345-6',
    period: {{ start: '2024-10-01', end: '2024-10-31' }},
    initial_balance: '#number',
    final_balance: '#number',
    total_credits: '#number',
    total_debits: '#number',
    transactions: '#[]'
  }}
  '''
  # Validar cálculos
  * def calculatedBalance = response.initial_balance + response.total_credits - response.total_debits
  And match response.final_balance == calculatedBalance
  And match responseTime < 5000

@regression @statements
Scenario: Gerar extrato de 90 dias (período máximo)
  Given path '/statements/12345-6'
  And params {{ start_date: '2024-07-01', end_date: '2024-09-30', format: 'json' }}
  When method GET
  Then status 200
  And match response.account_id == '12345-6'
  And match response.period.start == '2024-07-01'
  And match response.period.end == '2024-09-30'

@negative @statements
Scenario: Período maior que 90 dias (deve falhar)
  Given path '/statements/12345-6'
  And params {{ start_date: '2024-01-01', end_date: '2024-12-31' }}
  When method GET
  Then status 400
  And match response.error contains '90'

@smoke @statements
Scenario: Solicitar extrato em formato PDF
  Given path '/statements/12345-6'
  And params {{ start_date: '2024-10-01', end_date: '2024-10-31', format: 'pdf' }}
  When method GET
  Then status 200
  And match responseHeaders['Content-Type'][0] contains 'application/pdf'
  And match responseBytes == '#notnull'
  And assert responseBytes.length > 1000

@negative @statements
Scenario: Data inicial maior que data final
  Given path '/statements/12345-6'
  And params {{ start_date: '2024-10-31', end_date: '2024-10-01' }}
  When method GET
  Then status 400
  And match response.error contains 'data'

@negative @statements
Scenario: Conta inexistente
  Given path '/statements/99999-9'
  And params {{ start_date: '2024-10-01', end_date: '2024-10-31' }}
  When method GET
  Then status 404

@negative @statements
Scenario: Conta de outro usuário
  Given path '/statements/87654-3'
  And params {{ start_date: '2024-10-01', end_date: '2024-10-31' }}
  When method GET
  Then status 403
  And match response.error contains 'forbidden'

@negative @statements
Scenario: Sem autenticação
  * header Authorization = null
  Given path '/statements/12345-6'
  And params {{ start_date: '2024-10-01', end_date: '2024-10-31' }}
  When method GET
  Then status 401

@negative @statements
Scenario: Formato inválido
  Given path '/statements/12345-6'
  And params {{ start_date: '2024-10-01', end_date: '2024-10-31', format: 'xml' }}
  When method GET
  Then status 400
  And match response.error contains 'format'
"""