# Copyright 2025 Google LLC
# Licensed under the Apache License, Version 2.0

"""OpenAPI Parser - Suporta Bitbucket, arquivos locais e URLs."""

import yaml
import json
import requests
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from pathlib import Path

@dataclass
class APIEndpoint:
    """Endpoint da API."""
    path: str
    method: str
    operation_id: Optional[str]
    summary: Optional[str]
    description: Optional[str]
    tags: List[str]
    parameters: List[Dict[str, Any]]
    request_body: Optional[Dict[str, Any]]
    responses: Dict[str, Dict[str, Any]]
    security: List[Dict[str, List[str]]]
    examples: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path, "method": self.method, "operation_id": self.operation_id,
            "summary": self.summary, "description": self.description, "tags": self.tags,
            "parameters": self.parameters, "request_body": self.request_body,
            "responses": self.responses, "security": self.security, "examples": self.examples
        }

@dataclass
class OpenAPISpec:
    """Especificação OpenAPI completa."""
    version: str
    info: Dict[str, Any]
    servers: List[Dict[str, str]]
    endpoints: List[APIEndpoint]
    components: Dict[str, Any]
    security_schemes: Dict[str, Any]

    def get_base_url(self, environment: str = "production") -> str:
        env_map = {"production": ["production", "prod"], "staging": ["staging", "stg"],
                   "development": ["development", "dev"]}
        for server in self.servers:
            desc = server.get("description", "").lower()
            for env_key in env_map.get(environment, []):
                if env_key in desc:
                    return server["url"]
        return self.servers[0]["url"] if self.servers else ""

    def get_endpoints_by_tag(self, tag: str) -> List[APIEndpoint]:
        return [ep for ep in self.endpoints if tag in ep.tags]

    def find_endpoint(self, path: str, method: str) -> Optional[APIEndpoint]:
        method = method.upper()
        for endpoint in self.endpoints:
            if endpoint.path == path and endpoint.method == method:
                return endpoint
        return None

class OpenAPIParser:
    """Parser profissional de OpenAPI 3.x."""

    def __init__(self, bitbucket_token: Optional[str] = None):
        self.bitbucket_token = bitbucket_token

    def parse_from_file(self, file_path: Union[str, Path]) -> OpenAPISpec:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"OpenAPI file not found: {file_path}")
        content = file_path.read_text(encoding="utf-8")
        if file_path.suffix in [".yaml", ".yml"]:
            return self.parse_from_yaml(content)
        return self.parse_from_json(content)

    def parse_from_yaml(self, yaml_content: str) -> OpenAPISpec:
        spec_dict = yaml.safe_load(yaml_content)
        return self._parse_spec_dict(spec_dict)

    def parse_from_json(self, json_content: str) -> OpenAPISpec:
        spec_dict = json.loads(json_content)
        return self._parse_spec_dict(spec_dict)

    def parse_from_bitbucket(self, workspace: str, repo_slug: str, file_path: str, branch: str = "main") -> OpenAPISpec:
        if not self.bitbucket_token:
            raise ValueError("Bitbucket token required")
        url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/src/{branch}/{file_path}"
        headers = {"Authorization": f"Bearer {self.bitbucket_token}", "Accept": "application/json"}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return self.parse_from_yaml(response.text) if file_path.endswith((".yaml", ".yml")) else self.parse_from_json(response.text)

    def parse_from_url(self, url: str) -> OpenAPISpec:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        try:
            return self.parse_from_yaml(response.text)
        except:
            return self.parse_from_json(response.text)

    def _parse_spec_dict(self, spec: Dict[str, Any]) -> OpenAPISpec:
        version = spec.get("openapi", "")
        if not version.startswith("3."):
            raise ValueError(f"Unsupported OpenAPI version: {version}")
        info = spec.get("info", {})
        servers = spec.get("servers", [])
        components = spec.get("components", {})
        security_schemes = components.get("securitySchemes", {})
        endpoints = self._parse_paths(spec.get("paths", {}), components)
        return OpenAPISpec(version, info, servers, endpoints, components, security_schemes)

    def _parse_paths(self, paths: Dict[str, Any], components: Dict[str, Any]) -> List[APIEndpoint]:
        endpoints = []
        http_methods = ["get", "post", "put", "delete", "patch", "head", "options"]
        for path, path_item in paths.items():
            path_params = path_item.get("parameters", [])
            for method in http_methods:
                if method not in path_item:
                    continue
                operation = path_item[method]
                examples = self._extract_examples(operation, components)
                endpoint = APIEndpoint(
                    path=path, method=method.upper(), operation_id=operation.get("operationId"),
                    summary=operation.get("summary"), description=operation.get("description"),
                    tags=operation.get("tags", []), parameters=path_params + operation.get("parameters", []),
                    request_body=operation.get("requestBody"), responses=operation.get("responses", {}),
                    security=operation.get("security", []), examples=examples
                )
                endpoints.append(endpoint)
        return endpoints

    def _extract_examples(self, operation: Dict[str, Any], components: Dict[str, Any]) -> Dict[str, Any]:
        examples = {"request": {}, "response": {}}
        request_body = operation.get("requestBody", {})
        if request_body:
            content = request_body.get("content", {})
            for media_type, media_obj in content.items():
                if "examples" in media_obj:
                    examples["request"][media_type] = media_obj["examples"]
                elif "example" in media_obj:
                    examples["request"][media_type] = {"default": {"value": media_obj["example"]}}
        responses = operation.get("responses", {})
        for status_code, response_obj in responses.items():
            content = response_obj.get("content", {})
            for media_type, media_obj in content.items():
                key = f"{status_code}_{media_type}"
                if "examples" in media_obj:
                    examples["response"][key] = media_obj["examples"]
                elif "example" in media_obj:
                    examples["response"][key] = {"default": {"value": media_obj["example"]}}
        return examples

def load_openapi_spec(source: str, source_type: str = "auto", bitbucket_token: Optional[str] = None, **kwargs) -> OpenAPISpec:
    """Carrega OpenAPI de várias fontes."""
    parser = OpenAPIParser(bitbucket_token=bitbucket_token)
    if source_type == "auto":
        if source.startswith(("http://", "https://")):
            source_type = "url"
        elif Path(source).exists():
            source_type = "file"
        else:
            raise ValueError(f"Cannot auto-detect source type for: {source}")
    if source_type == "file":
        return parser.parse_from_file(source)
    elif source_type == "url":
        return parser.parse_from_url(source)
    elif source_type == "bitbucket":
        return parser.parse_from_bitbucket(
            workspace=kwargs.get("workspace"), repo_slug=kwargs.get("repo_slug"),
            file_path=source, branch=kwargs.get("branch", "main")
        )
    else:
        raise ValueError(f"Unsupported source type: {source_type}")

