"""Tests for smart Newman collection builder handling structured scenarios."""

from __future__ import annotations

import importlib
import json
import sys
import types
from typing import Callable, Dict

import pytest


def _ensure_jsonschema_stub() -> None:
    if "jsonschema" in sys.modules:
        return

    class _Draft7Validator:
        def __init__(self, _schema: Dict[str, object]):
            self.schema = _schema

        def iter_errors(self, _instance: Dict[str, object]):  # pragma: no cover - simple stub
            return []

    module = types.ModuleType("jsonschema")
    module.Draft7Validator = _Draft7Validator
    sys.modules["jsonschema"] = module


@pytest.fixture()
def smart_builder() -> Callable[..., Dict[str, object]]:
    _ensure_jsonschema_stub()
    module = importlib.import_module(
        "app.sub_agents.newman_expert.tools.smart_collection_builder"
    )
    return module.build_smart_newman_collection


@pytest.fixture()
def ecommerce_openapi_spec() -> str:
    """Provide a minimal OpenAPI definition for the e-commerce API."""

    return """
openapi: 3.0.0
info:
  title: E-commerce API
  version: 1.0.0
servers:
  - url: https://api.example.com
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
paths:
  /api/products:
    get:
      summary: Lista todos os produtos
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: string
                    name:
                      type: string
                    price:
                      type: number
    post:
      summary: Cria um novo produto
      security:
        - BearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
                price:
                  type: number
                description:
                  type: string
      responses:
        '201':
          description: Created
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: string
  /api/products/{id}:
    get:
      summary: Busca produto por ID
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: string
                  description:
                    type: string
                  price:
                    type: number
                  category:
                    type: string
                  stock:
                    type: integer
        '404':
          description: Not Found
    put:
      summary: Atualiza um produto existente
      security:
        - BearerAuth: []
      responses:
        '200':
          description: OK
    delete:
      summary: Remove um produto
      security:
        - BearerAuth: []
      responses:
        '204':
          description: No Content
  /api/orders:
    post:
      summary: Cria um novo pedido
      security:
        - BearerAuth: []
      responses:
        '201':
          description: Created
"""


@pytest.fixture()
def structured_test_suite() -> Dict[str, object]:
    """Return Zephyr-like structured scenarios mirroring user requirements."""

    return {
        "test_cases": [
            {
                "key": "TC-1",
                "name": "Teste de Listagem de Produtos",
                "folder": "/Products",
                "request": {"method": "GET", "path": "/api/products"},
                "tests": {
                    "status_code": 200,
                    "response_time": 2000,
                    "body_checks": [
                        "pm.test('Response should be an array', () => { const response = pm.response.json(); pm.expect(response).to.be.an('array'); });",
                        "pm.test('Each product has required keys', () => { const response = pm.response.json(); if (response.length > 0) { pm.expect(response[0]).to.have.all.keys('id', 'name', 'price'); } });",
                    ],
                },
            },
            {
                "key": "TC-2",
                "name": "Tentar criar produto sem autenticação",
                "folder": "/Products",
                "request": {
                    "method": "POST",
                    "path": "/api/products",
                    "body": {"name": "Produto não autorizado", "price": 100},
                    "auth": "none",
                },
                "tests": {"status_code": 401},
            },
            {
                "key": "TC-3",
                "name": "Criar produto com dados válidos",
                "folder": "/Products",
                "request": {
                    "method": "POST",
                    "path": "/api/products",
                    "body": {
                        "name": "Notebook Dell",
                        "description": "Notebook Dell Inspiron 15",
                        "price": 3500.00,
                        "category": "electronics",
                        "stock": 10,
                    },
                },
                "tests": {
                    "status_code": 201,
                    "header_checks": [
                        "pm.test('Location header is present', () => { pm.response.to.have.header('Location'); });"
                    ],
                    "body_checks": [
                        "const responseData = pm.response.json();",
                        "pm.test('Response contains created product data', () => { pm.expect(responseData.name).to.eql('Notebook Dell'); });",
                        "pm.test('Response has a generated id', () => { pm.expect(responseData.id).to.not.be.empty; });",
                    ],
                    "chaining": "const responseData = pm.response.json(); pm.collectionVariables.set('product_id', responseData.id);",
                },
            },
            {
                "key": "TC-4",
                "name": "Buscar produto existente por ID",
                "folder": "/Products",
                "request": {
                    "method": "GET",
                    "path": "/api/products/{{product_id}}",
                },
                "tests": {
                    "status_code": 200,
                    "body_checks": [
                        "pm.test('Response contains all required fields', () => { const responseData = pm.response.json(); pm.expect(responseData).to.have.all.keys('id', 'name', 'description', 'price', 'category', 'stock'); });",
                    ],
                },
            },
            {
                "key": "TC-5",
                "name": "Buscar produto inexistente",
                "folder": "/Products",
                "request": {
                    "method": "GET",
                    "path": "/api/products/invalid-id-999",
                },
                "tests": {"status_code": 404},
            },
        ]
    }


def _extract_request(collection: Dict[str, object], folder_name: str, request_name: str) -> Dict[str, object]:
    folders = {folder["name"]: folder for folder in collection["item"]}
    folder = folders[folder_name]
    requests = {item["name"]: item for item in folder["item"]}
    return requests[request_name]


def _join_test_script(request: Dict[str, object]) -> str:
    for event in request.get("event", []):
        if event.get("listen") == "test":
            return "\n".join(event.get("script", {}).get("exec", []))
    return ""


def test_structured_scenarios_generate_precise_scripts(
    smart_builder: Callable[..., Dict[str, object]],
    ecommerce_openapi_spec: str,
    structured_test_suite: Dict[str, object],
) -> None:
    collection = smart_builder(
        openapi_spec=ecommerce_openapi_spec,
        zephyr_scenarios=json.dumps(structured_test_suite),
        domain="ecommerce",
    )

    unauth_request = _extract_request(collection, "Products", "TC-2: Tentar criar produto sem autenticação")
    assert unauth_request["request"]["auth"]["type"] == "noauth"
    unauth_script = _join_test_script(unauth_request)
    assert "pm.response.to.have.status(401)" in unauth_script
    assert "pm.response.to.be.success" not in unauth_script

    create_request = _extract_request(collection, "Products", "TC-3: Criar produto com dados válidos")
    create_script = _join_test_script(create_request)
    assert "pm.response.to.have.status(201)" in create_script
    assert "pm.collectionVariables.set('product_id'" in create_script
    assert "pm.expect(pm.response.headers.get('Content-Type')).to.include('application/json');" in create_script

    list_request = _extract_request(collection, "Products", "TC-1: Teste de Listagem de Produtos")
    list_script = _join_test_script(list_request)
    assert "pm.expect(pm.response.responseTime).to.be.below(2000)" in list_script
    assert "pm.response.to.be.json" in list_script

    get_request = _extract_request(collection, "Products", "TC-4: Buscar produto existente por ID")
    assert get_request["request"]["url"]["raw"] == "{{base_url}}/api/products/{{product_id}}"

    negative_request = _extract_request(collection, "Products", "TC-5: Buscar produto inexistente")
    negative_script = _join_test_script(negative_request)
    assert "pm.response.to.have.status(404)" in negative_script
    assert "pm.response.to.be.success" not in negative_script
