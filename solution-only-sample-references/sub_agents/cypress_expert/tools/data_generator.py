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

"""Test Data Generator - Domain-agnostic expert tool."""

from typing import Dict, Any, List
import json


def generate_test_data(domain: str, complexity: str) -> Dict[str, str]:
    """Generate comprehensive test data for any domain."""

    # Basic domain analysis without domain_config dependency
    domain_analysis = {"type": "general", "complexity": complexity}

    fixtures = _generate_fixtures(domain, domain_analysis)
    mock_data = _generate_mock_data(domain, domain_analysis)
    test_scenarios = _generate_test_scenarios(domain, complexity, domain_analysis)

    return {
        "fixtures": fixtures,
        "mock_data": mock_data,
        "test_scenarios": test_scenarios
    }


def _generate_fixtures(domain: str, analysis: Dict[str, Any]) -> str:
    """Generate fixture data based on domain patterns."""

    base_data = {
        "users": _generate_user_data(analysis),
        "settings": _generate_settings_data(domain, analysis)
    }

    # Add domain-specific data based on analysis
    if analysis.get("payment_integration"):
        base_data.update(_generate_commerce_data(domain))

    if analysis.get("security_level") == "high":
        base_data.update(_generate_security_data(domain))

    if analysis.get("privacy_level") == "maximum":
        base_data.update(_generate_privacy_data(domain))

    return f"""// cypress/fixtures/{domain}-data.json
{json.dumps(base_data, indent=2)}"""


def _generate_user_data(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Generate user data based on domain requirements."""
    users = {
        "valid": {
            "email": "test.user@example.com",
            "username": "testuser",
            "password": "SecurePass123!",
            "firstName": "Test",
            "lastName": "User"
        },
        "invalid": {
            "email": "invalid-email",
            "username": "",
            "password": "weak"
        }
    }

    # Add security-specific user data
    if analysis.get("security_level") == "high":
        users["valid"].update({
            "mfaToken": "123456",
            "securityQuestions": {
                "question1": "What is your pet's name?",
                "answer1": "Fluffy"
            }
        })
        users["admin"] = {
            "email": "admin@example.com",
            "username": "admin",
            "password": "AdminPass123!",
            "role": "administrator",
            "permissions": ["read", "write", "delete", "admin"]
        }

    # Add compliance-specific user data
    if analysis.get("privacy_level") == "maximum":
        users["valid"].update({
            "consentGiven": True,
            "dataProcessingAgreement": True,
            "cookiePreferences": {
                "necessary": True,
                "analytics": False,
                "marketing": False
            }
        })

    return users


def _generate_settings_data(domain: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Generate application settings based on domain."""
    settings = {
        "application": {
            "name": f"{domain.title()} Application",
            "version": "1.0.0",
            "environment": "test"
        },
        "ui": {
            "theme": "light",
            "language": "en",
            "timezone": "UTC"
        }
    }

    # Add domain-specific settings
    if analysis.get("performance_critical"):
        settings["performance"] = {
            "cacheEnabled": True,
            "compressionEnabled": True,
            "lazyLoadingEnabled": True
        }

    if analysis.get("security_level") == "high":
        settings["security"] = {
            "sessionTimeout": 1800,
            "passwordPolicy": {
                "minLength": 8,
                "requireSpecialChars": True,
                "requireNumbers": True
            },
            "auditLogging": True
        }

    return settings


def _generate_commerce_data(domain: str) -> Dict[str, Any]:
    """Generate e-commerce specific test data."""
    return {
        "products": [
            {
                "id": "PROD001",
                "name": "Test Product 1",
                "price": 29.99,
                "currency": "USD",
                "category": "electronics",
                "inStock": True,
                "quantity": 100
            },
            {
                "id": "PROD002",
                "name": "Test Product 2",
                "price": 59.99,
                "currency": "USD",
                "category": "clothing",
                "inStock": False,
                "quantity": 0
            }
        ],
        "orders": [
            {
                "id": "ORD001",
                "customerId": "CUST001",
                "items": [
                    {
                        "productId": "PROD001",
                        "quantity": 2,
                        "price": 29.99
                    }
                ],
                "total": 59.98,
                "status": "pending",
                "createdAt": "2024-01-01T10:00:00Z"
            }
        ],
        "payments": {
            "creditCard": {
                "number": "4111111111111111",
                "expiry": "12/25",
                "cvv": "123",
                "name": "Test User"
            },
            "paypal": {
                "email": "test@paypal.com"
            }
        }
    }


def _generate_security_data(domain: str) -> Dict[str, Any]:
    """Generate security-specific test data."""
    return {
        "accounts": [
            {
                "accountNumber": "1234567890",
                "accountType": "checking",
                "balance": 1000.00,
                "currency": "USD",
                "status": "active"
            }
        ],
        "transactions": [
            {
                "id": "TXN001",
                "fromAccount": "1234567890",
                "toAccount": "0987654321",
                "amount": 100.00,
                "type": "transfer",
                "status": "completed",
                "timestamp": "2024-01-01T10:00:00Z"
            }
        ],
        "security": {
            "validTokens": [
                "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.valid.token"
            ],
            "expiredTokens": [
                "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.expired.token"
            ],
            "invalidTokens": [
                "invalid.token.format"
            ]
        }
    }


def _generate_privacy_data(domain: str) -> Dict[str, Any]:
    """Generate privacy and healthcare specific test data."""
    return {
        "patients": [
            {
                "id": "PAT001",
                "mrn": "MRN123456",
                "firstName": "John",
                "lastName": "Doe",
                "dateOfBirth": "1990-01-01",
                "consentGiven": True,
                "dataEncrypted": True
            }
        ],
        "appointments": [
            {
                "id": "APT001",
                "patientId": "PAT001",
                "providerId": "PROV001",
                "datetime": "2024-01-15T10:00:00Z",
                "type": "consultation",
                "status": "scheduled"
            }
        ],
        "privacy": {
            "consentTypes": [
                "dataProcessing",
                "marketing",
                "analytics",
                "thirdPartySharing"
            ],
            "dataCategories": [
                "personalInfo",
                "healthData",
                "behavioralData",
                "technicalData"
            ]
        }
    }


def _generate_mock_data(domain: str, analysis: Dict[str, Any]) -> str:
    """Generate mock API responses based on domain analysis."""

    mock_responses = {
        "success": {
            "status": 200,
            "data": {"message": "Success"},
            "timestamp": "2024-01-01T10:00:00Z"
        },
        "error": {
            "status": 500,
            "error": "Internal Server Error",
            "timestamp": "2024-01-01T10:00:00Z"
        },
        "notFound": {
            "status": 404,
            "error": "Resource not found",
            "timestamp": "2024-01-01T10:00:00Z"
        }
    }

    # Add domain-specific mock responses
    if analysis.get("payment_integration"):
        mock_responses["payment"] = {
            "success": {
                "status": 200,
                "transactionId": "TXN123456",
                "amount": 100.00,
                "currency": "USD",
                "status": "completed"
            },
            "failure": {
                "status": 400,
                "error": "Payment failed",
                "errorCode": "INSUFFICIENT_FUNDS"
            }
        }

    if analysis.get("security_level") == "high":
        mock_responses["auth"] = {
            "login": {
                "status": 200,
                "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.success.token",
                "refreshToken": "refresh.token.here",
                "expiresIn": 3600
            },
            "unauthorized": {
                "status": 401,
                "error": "Unauthorized",
                "message": "Invalid credentials"
            }
        }

    return f"""// cypress/fixtures/mock-{domain}.json
{json.dumps(mock_responses, indent=2)}"""


def _generate_test_scenarios(domain: str, complexity: str, analysis: Dict[str, Any]) -> str:
    """Generate test scenarios based on domain and complexity."""

    scenarios = {
        "happy_path": [
            "User can successfully navigate the main application flow",
            "All primary features work as expected",
            "Data is displayed correctly and consistently"
        ],
        "edge_cases": [
            "System handles invalid inputs gracefully",
            "Error messages are user-friendly and informative",
            "Application recovers from temporary failures"
        ],
        "performance": [
            "Page loads within acceptable time limits",
            "No memory leaks during extended usage",
            "Responsive design works across devices"
        ]
    }

    # Add domain-specific scenarios
    if analysis.get("payment_integration"):
        scenarios["commerce"] = [
            "Shopping cart functionality works correctly",
            "Checkout process completes successfully",
            "Payment processing handles all scenarios",
            "Inventory updates reflect real-time changes"
        ]

    if analysis.get("security_level") == "high":
        scenarios["security"] = [
            "Authentication and authorization work correctly",
            "Session management prevents unauthorized access",
            "Data encryption protects sensitive information",
            "Audit logging captures all critical actions"
        ]

    if analysis.get("privacy_level") == "maximum":
        scenarios["privacy"] = [
            "Data protection measures are effective",
            "Consent management works as expected",
            "Personal data can be safely managed and deleted",
            "Privacy preferences are respected throughout"
        ]

    # Add complexity-based scenarios
    if complexity in ["complex", "enterprise"]:
        scenarios["integration"] = [
            "Multiple systems integrate seamlessly",
            "Data synchronization works correctly",
            "Third-party services respond appropriately",
            "Backup and recovery procedures function"
        ]

    return f"""// Test scenarios for {domain} - {complexity} complexity
export const testScenarios = {json.dumps(scenarios, indent=2)};"""
