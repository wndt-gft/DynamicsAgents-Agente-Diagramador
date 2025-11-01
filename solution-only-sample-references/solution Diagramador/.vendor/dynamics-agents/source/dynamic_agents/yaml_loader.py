"""Minimal YAML utilities with graceful fallback when PyYAML is unavailable."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Tuple

try:  # pragma: no cover - exercised when PyYAML is installed
    import yaml as _pyyaml  # type: ignore[import-untyped]
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal environments
    _pyyaml = None


def safe_dump(data: Any, *, sort_keys: bool = False) -> str:
    """Serialize ``data`` to YAML (or JSON as a fallback)."""

    if _pyyaml is not None:
        return _pyyaml.safe_dump(data, sort_keys=sort_keys)  # type: ignore[no-any-return]
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=sort_keys)


def safe_load(text: str) -> Any:
    """Parse ``text`` into Python data structures.

    The loader tries PyYAML first. When PyYAML is not installed we fall back to a
    tiny indentation-based parser that supports the subset of YAML used by the
    project (mappings, sequences, scalars and folded plain text blocks).
    """

    if _pyyaml is not None:
        return _pyyaml.safe_load(text)
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    parser = _MiniYamlParser(text)
    return parser.parse()


_SCALAR_TRUE = {"true", "True", "yes", "Yes", "on", "On"}
_SCALAR_FALSE = {"false", "False", "no", "No", "off", "Off"}
_SCALAR_NULL = {"null", "Null", "NULL", "~", ""}


@dataclass
class _Token:
    indent: int
    content: str


class _MiniYamlParser:
    """Very small YAML parser sufficient for the engine test fixtures."""

    def __init__(self, text: str):
        self.tokens: List[_Token] = self._tokenize(text)
        self.index = 0

    @staticmethod
    def _strip_inline_comment(content: str) -> str:
        in_single = False
        in_double = False
        escape = False
        for idx, char in enumerate(content):
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == "'" and not in_double:
                in_single = not in_single
            elif char == '"' and not in_single:
                in_double = not in_double
            elif char == "#" and not in_single and not in_double:
                return content[:idx].rstrip()
        return content.strip()

    def _tokenize(self, text: str) -> List[_Token]:
        tokens: List[_Token] = []
        for raw_line in text.splitlines():
            if not raw_line.strip():
                continue
            indent = len(raw_line) - len(raw_line.lstrip(" "))
            content = raw_line.lstrip(" ")
            if not content or content.startswith("#"):
                continue
            stripped = self._strip_inline_comment(content)
            if not stripped:
                continue
            tokens.append(_Token(indent=indent, content=stripped))
        return tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> Any:
        if not self.tokens:
            return None
        value, _ = self._parse_block(indent=self.tokens[0].indent)
        return value

    # ------------------------------------------------------------------
    # Recursive descent helpers
    # ------------------------------------------------------------------

    def _peek(self) -> Optional[_Token]:
        if self.index >= len(self.tokens):
            return None
        return self.tokens[self.index]

    def _advance(self) -> Optional[_Token]:
        token = self._peek()
        if token is not None:
            self.index += 1
        return token

    def _parse_block(self, indent: int) -> Tuple[Any, int]:
        token = self._peek()
        if token is None:
            return None, indent
        if token.indent < indent:
            return None, indent
        if token.content.startswith("- "):
            return self._parse_sequence(token.indent)
        if self._looks_like_mapping_key(token):
            return self._parse_mapping(token.indent)
        return self._parse_plain_text_block(token.indent)

    def _parse_sequence(self, indent: int) -> Tuple[List[Any], int]:
        items: List[Any] = []
        while True:
            token = self._peek()
            if token is None or token.indent != indent or not token.content.startswith("- "):
                break
            item_token = self._advance()
            assert item_token is not None
            content = item_token.content[2:].lstrip()
            if not content:
                value, _ = self._parse_block(indent + 2)
                items.append(value)
                continue
            if self._looks_like_mapping_key_str(content):
                key, remainder = self._split_key_value(content)
                mapping: dict[str, Any] = {}
                if remainder is None:
                    value, _ = self._parse_block(indent + 2)
                else:
                    value = self._parse_scalar(remainder, treat_plain=False)
                mapping[key] = value
                self._merge_following_mapping_entries(mapping, indent + 2)
                items.append(mapping)
            else:
                items.append(self._parse_scalar(content, treat_plain=False))
                self._consume_child_blocks(indent)
        return items, indent

    def _consume_child_blocks(self, parent_indent: int) -> None:
        token = self._peek()
        while token is not None and token.indent > parent_indent:
            # Consume nested plain blocks so subsequent top-level items continue correctly.
            self._parse_block(token.indent)
            token = self._peek()

    def _merge_following_mapping_entries(self, mapping: dict[str, Any], indent: int) -> None:
        while True:
            token = self._peek()
            if token is None or token.indent != indent or token.content.startswith("- "):
                return
            key, remainder = self._split_key_value(token.content)
            self._advance()
            if remainder is None:
                value, _ = self._parse_block(indent + 2)
            else:
                value = self._parse_scalar(remainder, treat_plain=False)
                # Consume nested structures for inline scalars if present.
                next_token = self._peek()
                if next_token is not None and next_token.indent > indent:
                    nested, _ = self._parse_block(next_token.indent)
                    if isinstance(value, dict) and isinstance(nested, dict):
                        value.update(nested)
                    else:
                        value = nested
            mapping[key] = value

    def _parse_mapping(self, indent: int) -> Tuple[dict, int]:
        mapping: dict[str, Any] = {}
        while True:
            token = self._peek()
            if token is None or token.indent != indent or token.content.startswith("- "):
                break
            key, remainder = self._split_key_value(token.content)
            self._advance()
            if remainder is None:
                value, _ = self._parse_block(indent + 2)
            else:
                value = self._parse_scalar(remainder, treat_plain=False)
                next_token = self._peek()
                if next_token is not None and next_token.indent > indent:
                    nested, _ = self._parse_block(next_token.indent)
                    if isinstance(value, dict) and isinstance(nested, dict):
                        value.update(nested)
                    else:
                        value = nested
            mapping[key] = value
        return mapping, indent

    def _parse_plain_text_block(self, indent: int) -> Tuple[str, int]:
        lines: List[str] = []
        while True:
            token = self._peek()
            if token is None or token.indent < indent:
                break
            if token.content.startswith("- ") or self._looks_like_mapping_key(token):
                break
            token = self._advance()
            assert token is not None
            lines.append(token.content)
        joined = "\n".join(line.rstrip() for line in lines).rstrip()
        return joined, indent

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_mapping_key(token: _Token) -> bool:
        return _MiniYamlParser._looks_like_mapping_key_str(token.content)

    @staticmethod
    def _looks_like_mapping_key_str(content: str) -> bool:
        if ":" not in content:
            return False
        key, _ = _MiniYamlParser._split_key_value(content)
        return bool(key)

    @staticmethod
    def _split_key_value(content: str) -> Tuple[str, Optional[str]]:
        key_buffer: List[str] = []
        in_single = False
        in_double = False
        escape = False
        for idx, char in enumerate(content):
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == "'" and not in_double:
                in_single = not in_single
            elif char == '"' and not in_single:
                in_double = not in_double
            elif char == ":" and not in_single and not in_double:
                key = "".join(key_buffer).strip()
                remainder = content[idx + 1 :].strip()
                if not remainder:
                    remainder = None
                return key, remainder
            key_buffer.append(char)
        return content.strip(), None

    @staticmethod
    def _parse_scalar(value: str, *, treat_plain: bool) -> Any:
        if treat_plain:
            return value
        if value.startswith("'") and value.endswith("'"):
            return value[1:-1]
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        if value in _SCALAR_NULL:
            return None
        if value in _SCALAR_TRUE:
            return True
        if value in _SCALAR_FALSE:
            return False
        if re.fullmatch(r"-?\d+", value):
            try:
                return int(value)
            except ValueError:
                pass
        if re.fullmatch(r"-?\d+\.\d*", value):
            try:
                return float(value)
            except ValueError:
                pass
        if value.startswith("[") and value.endswith("]"):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        if value.startswith("{") and value.endswith("}"):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
