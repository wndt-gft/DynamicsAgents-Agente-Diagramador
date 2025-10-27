"""Newman Authentication Generator - Generates authentication collections for different auth types."""

import json
from typing import Dict, Any, List


def generate_authentication_collections(
    auth_types: List[str],
    domain: str,
    config: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Generate authentication collections for different auth types."""

    auth_collections = {}

    for auth_type in auth_types:
        if auth_type == "oauth2":
            auth_collections["oauth2"] = generate_oauth2_collection(domain, config)
        elif auth_type == "api_key":
            auth_collections["api_key"] = generate_api_key_collection(domain, config)
        elif auth_type == "bearer":
            auth_collections["bearer"] = generate_bearer_collection(domain, config)
        elif auth_type == "jwt":
            auth_collections["jwt"] = generate_jwt_collection(domain, config)

    return auth_collections


def generate_oauth2_collection(domain: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate OAuth2 authentication collection."""

    return {
        "info": {
            "name": f"{domain.title()} OAuth2 Authentication",
            "description": f"OAuth2 authentication flows for {domain} API"
        },
        "item": [
            {
                "name": "Get OAuth2 Token",
                "request": {
                    "method": "POST",
                    "header": [
                        {
                            "key": "Content-Type",
                            "value": "application/x-www-form-urlencoded"
                        }
                    ],
                    "body": {
                        "mode": "urlencoded",
                        "urlencoded": [
                            {
                                "key": "grant_type",
                                "value": "client_credentials"
                            },
                            {
                                "key": "client_id",
                                "value": "{{{{client_id}}}}"
                            },
                            {
                                "key": "client_secret",
                                "value": "{{{{client_secret}}}}"
                            },
                            {
                                "key": "scope",
                                "value": "{{{{oauth_scope}}}}"
                            }
                        ]
                    },
                    "url": {
                        "raw": "{{{{auth_url}}}}/oauth/token",
                        "host": ["{{{{auth_url}}}}"],
                        "path": ["oauth", "token"]
                    }
                },
                "event": [
                    {
                        "listen": "test",
                        "script": {
                            "type": "text/javascript",
                            "exec": [
                                "pm.test('OAuth2 token received', function () {",
                                "    pm.response.to.have.status(200);",
                                "    const responseJson = pm.response.json();",
                                "    pm.expect(responseJson).to.have.property('access_token');",
                                "    pm.globals.set('oauth_token', responseJson.access_token);",
                                "});"
                            ]
                        }
                    }
                ]
            }
        ]
    }


def generate_api_key_collection(domain: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate API Key authentication collection."""

    return {
        "info": {
            "name": f"{domain.title()} API Key Authentication",
            "description": f"API Key authentication tests for {domain} API"
        },
        "item": [
            {
                "name": "Test API Key Authentication",
                "request": {
                    "method": "GET",
                    "header": [
                        {
                            "key": "X-API-Key",
                            "value": "{{{{api_key}}}}"
                        }
                    ],
                    "url": {
                        "raw": "{{{{base_url}}}}/api/auth/validate",
                        "host": ["{{{{base_url}}}}"],
                        "path": ["api", "auth", "validate"]
                    }
                },
                "event": [
                    {
                        "listen": "test",
                        "script": {
                            "type": "text/javascript",
                            "exec": [
                                "pm.test('API Key authentication successful', function () {",
                                "    pm.response.to.have.status(200);",
                                "    const responseJson = pm.response.json();",
                                "    pm.expect(responseJson.authenticated).to.be.true;",
                                "});"
                            ]
                        }
                    }
                ]
            }
        ]
    }


def generate_bearer_collection(domain: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate Bearer token authentication collection."""

    return {
        "info": {
            "name": f"{domain.title()} Bearer Token Authentication",
            "description": f"Bearer token authentication tests for {domain} API"
        },
        "item": [
            {
                "name": "Test Bearer Token Authentication",
                "request": {
                    "auth": {
                        "type": "bearer",
                        "bearer": [
                            {
                                "key": "token",
                                "value": "{{{{auth_token}}}}"
                            }
                        ]
                    },
                    "method": "GET",
                    "url": {
                        "raw": "{{{{base_url}}}}/api/auth/profile",
                        "host": ["{{{{base_url}}}}"],
                        "path": ["api", "auth", "profile"]
                    }
                },
                "event": [
                    {
                        "listen": "test",
                        "script": {
                            "type": "text/javascript",
                            "exec": [
                                "pm.test('Bearer token authentication successful', function () {",
                                "    pm.response.to.have.status(200);",
                                "    const responseJson = pm.response.json();",
                                "    pm.expect(responseJson).to.have.property('user');",
                                "});"
                            ]
                        }
                    }
                ]
            }
        ]
    }


def generate_jwt_collection(domain: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate JWT authentication collection."""

    return {
        "info": {
            "name": f"{domain.title()} JWT Authentication",
            "description": f"JWT authentication tests for {domain} API"
        },
        "item": [
            {
                "name": "Generate JWT Token",
                "request": {
                    "method": "POST",
                    "header": [
                        {
                            "key": "Content-Type",
                            "value": "application/json"
                        }
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": json.dumps({
                            "username": "{{{{username}}}}",
                            "password": "{{{{password}}}}"
                        }, indent=2)
                    },
                    "url": {
                        "raw": "{{{{base_url}}}}/api/auth/login",
                        "host": ["{{{{base_url}}}}"],
                        "path": ["api", "auth", "login"]
                    }
                },
                "event": [
                    {
                        "listen": "test",
                        "script": {
                            "type": "text/javascript",
                            "exec": [
                                "pm.test('JWT token received', function () {",
                                "    pm.response.to.have.status(200);",
                                "    const responseJson = pm.response.json();",
                                "    pm.expect(responseJson).to.have.property('token');",
                                "    pm.globals.set('jwt_token', responseJson.token);",
                                "});"
                            ]
                        }
                    }
                ]
            }
        ]
    }
