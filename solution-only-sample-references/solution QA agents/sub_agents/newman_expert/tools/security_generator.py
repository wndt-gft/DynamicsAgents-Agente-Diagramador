"""Newman Security Test Generator - Generates security test configurations."""

import json
from typing import Dict, Any, List


def generate_security_tests(domain: str, endpoints: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate security test configurations."""

    return {
        "info": {
            "name": f"{domain.title()} Security Tests",
            "description": f"Security testing collection for {domain} API"
        },
        "item": [
            {
                "name": "Authentication Tests",
                "item": [
                    {
                        "name": "Test without authentication",
                        "request": {
                            "method": "GET",
                            "header": [],
                            "url": {
                                "raw": f"{{\u007b\u007bbase_url\u007d\u007d}}/api/{domain}/protected",
                                "host": ["{{\u007b\u007bbase_url\u007d\u007d}}"],
                                "path": ["api", domain, "protected"]
                            }
                        },
                        "event": [
                            {
                                "listen": "test",
                                "script": {
                                    "type": "text/javascript",
                                    "exec": [
                                        "pm.test('Unauthenticated request rejected', function () {",
                                        "    pm.response.to.have.status(401);",
                                        "});"
                                    ]
                                }
                            }
                        ]
                    },
                    {
                        "name": "Test with invalid token",
                        "request": {
                            "auth": {
                                "type": "bearer",
                                "bearer": [
                                    {
                                        "key": "token",
                                        "value": "invalid_token_123"
                                    }
                                ]
                            },
                            "method": "GET",
                            "url": {
                                "raw": f"{{{{base_url}}}}/api/{domain}/protected",
                                "host": ["{{base_url}}"],
                                "path": ["api", domain, "protected"]
                            }
                        },
                        "event": [
                            {
                                "listen": "test",
                                "script": {
                                    "type": "text/javascript",
                                    "exec": [
                                        "pm.test('Invalid token rejected', function () {",
                                        "    pm.response.to.have.status(401);",
                                        "});"
                                    ]
                                }
                            }
                        ]
                    }
                ]
            },
            {
                "name": "Input Validation Tests",
                "item": [
                    {
                        "name": "SQL Injection Test",
                        "request": {
                            "method": "GET",
                            "url": {
                                "raw": f"{{{{base_url}}}}/api/{domain}/search?q=' OR '1'='1",
                                "host": ["{{base_url}}"],
                                "path": ["api", domain, "search"],
                                "query": [
                                    {
                                        "key": "q",
                                        "value": "' OR '1'='1"
                                    }
                                ]
                            }
                        },
                        "event": [
                            {
                                "listen": "test",
                                "script": {
                                    "type": "text/javascript",
                                    "exec": [
                                        "pm.test('SQL injection prevented', function () {",
                                        "    pm.response.to.have.status(400);",
                                        "});"
                                    ]
                                }
                            }
                        ]
                    },
                    {
                        "name": "XSS Test",
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
                                    "content": "<script>alert('xss')</script>"
                                })
                            },
                            "url": {
                                "raw": f"{{{{base_url}}}}/api/{domain}/comments",
                                "host": ["{{base_url}}"],
                                "path": ["api", domain, "comments"]
                            }
                        },
                        "event": [
                            {
                                "listen": "test",
                                "script": {
                                    "type": "text/javascript",
                                    "exec": [
                                        "pm.test('XSS attack prevented', function () {",
                                        "    pm.response.to.have.status(400);",
                                        "});"
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }
