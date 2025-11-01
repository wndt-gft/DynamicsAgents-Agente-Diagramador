# Copyright 2025 Google LLC
# Licensed under the Apache License, Version 2.0

"""Zephyr Scale Test Scenarios Parser."""

import json
import re
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

class TestPriority(Enum):
    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"
    CRITICAL = "Critical"

class TestStatus(Enum):
    DRAFT = "Draft"
    APPROVED = "Approved"
    DEPRECATED = "Deprecated"

@dataclass
class TestStep:
    step: int
    action: str
    expected_result: str
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"step": self.step, "action": self.action, "expected_result": self.expected_result}
        if self.data:
            result["data"] = self.data
        return result

@dataclass
class TestCase:
    id: str
    key: str
    name: str
    objective: str
    priority: TestPriority
    status: TestStatus
    folder: str
    labels: List[str]
    preconditions: List[str]
    test_steps: List[TestStep]
    expected_results: List[str]
    custom_fields: Dict[str, Any] = None

    def __post_init__(self):
        if self.custom_fields is None:
            self.custom_fields = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "key": self.key, "name": self.name, "objective": self.objective,
            "priority": self.priority.value, "status": self.status.value, "folder": self.folder,
            "labels": self.labels, "preconditions": self.preconditions,
            "test_steps": [step.to_dict() for step in self.test_steps],
            "expected_results": self.expected_results, "custom_fields": self.custom_fields
        }

    def get_api_operations(self) -> List[Dict[str, str]]:
        operations = []
        pattern = r'(GET|POST|PUT|DELETE|PATCH)\s+(/[\w\-/{}]*)'
        for step in self.test_steps:
            matches = re.finditer(pattern, step.action, re.IGNORECASE)
            for match in matches:
                operations.append({
                    "method": match.group(1).upper(), "path": match.group(2),
                    "step": step.step, "description": step.action
                })
        return operations

    def has_label(self, label: str) -> bool:
        return label.lower() in [l.lower() for l in self.labels]

@dataclass
class ZephyrExport:
    metadata: Dict[str, Any]
    test_cases: List[TestCase]

    def filter_by_label(self, label: str) -> List[TestCase]:
        return [tc for tc in self.test_cases if tc.has_label(label)]

    def filter_by_priority(self, priority: TestPriority) -> List[TestCase]:
        return [tc for tc in self.test_cases if tc.priority == priority]

    def filter_by_folder(self, folder: str) -> List[TestCase]:
        return [tc for tc in self.test_cases if folder.lower() in tc.folder.lower()]

    def get_all_labels(self) -> List[str]:
        labels = set()
        for tc in self.test_cases:
            labels.update(tc.labels)
        return sorted(list(labels))

class ZephyrParser:
    def parse_from_file(self, file_path: Union[str, Path]) -> ZephyrExport:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Test scenarios file not found: {file_path}")
        content = file_path.read_text(encoding="utf-8")
        return self.parse_from_json(content)

    def parse_from_json(self, json_content: str) -> ZephyrExport:
        data = json.loads(json_content)
        return self._parse_zephyr_dict(data)

    def parse_from_text(self, text_content: str) -> ZephyrExport:
        test_cases = []
        raw_cases = text_content.split("---")
        for idx, raw_case in enumerate(raw_cases):
            if not raw_case.strip():
                continue
            test_case = self._parse_text_test_case(raw_case, idx + 1)
            if test_case:
                test_cases.append(test_case)
        return ZephyrExport(metadata={"source": "Plain Text", "total_cases": len(test_cases)}, test_cases=test_cases)

    def _parse_zephyr_dict(self, data: Dict[str, Any]) -> ZephyrExport:
        metadata = data.get("metadata", {})
        test_cases_data = data.get("test_cases", [])
        test_cases = []
        for tc_data in test_cases_data:
            try:
                test_case = self._parse_test_case_dict(tc_data)
                test_cases.append(test_case)
            except Exception:
                continue
        return ZephyrExport(metadata=metadata, test_cases=test_cases)

    def _parse_test_case_dict(self, tc_data: Dict[str, Any]) -> TestCase:
        priority_str = tc_data.get("priority", "Normal")
        try:
            priority = TestPriority(priority_str)
        except ValueError:
            priority = TestPriority.NORMAL
        status_str = tc_data.get("status", "Approved")
        try:
            status = TestStatus(status_str)
        except ValueError:
            status = TestStatus.APPROVED
        steps_data = tc_data.get("test_steps", [])
        test_steps = [
            TestStep(
                step=step_data.get("step", idx + 1),
                action=step_data.get("action", ""),
                expected_result=step_data.get("expected_result", ""),
                data=step_data.get("data")
            )
            for idx, step_data in enumerate(steps_data)
        ]
        return TestCase(
            id=tc_data.get("id", ""), key=tc_data.get("key", ""), name=tc_data.get("name", ""),
            objective=tc_data.get("objective", ""), priority=priority, status=status,
            folder=tc_data.get("folder", "/"), labels=tc_data.get("labels", []),
            preconditions=tc_data.get("preconditions", []), test_steps=test_steps,
            expected_results=tc_data.get("expected_results", []),
            custom_fields=tc_data.get("custom_fields", {})
        )

    def _parse_text_test_case(self, text: str, index: int) -> Optional[TestCase]:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return None
        tc_id = f"TC-{index:03d}"
        name = ""
        priority = TestPriority.NORMAL
        labels = []
        preconditions = []
        steps = []
        section = None
        current_step = None
        for line in lines:
            if line.startswith("TEST CASE:"):
                tc_id = line.split(":", 1)[1].strip()
            elif line.startswith("NAME:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("PRIORITY:"):
                priority_str = line.split(":", 1)[1].strip()
                try:
                    priority = TestPriority(priority_str)
                except ValueError:
                    pass
            elif line.startswith("LABELS:"):
                labels_str = line.split(":", 1)[1].strip()
                labels = [l.strip() for l in labels_str.split(",")]
            elif line.upper() == "PRECONDITIONS:":
                section = "preconditions"
            elif line.upper() == "STEPS:":
                section = "steps"
            elif line.startswith("-") and section == "preconditions":
                preconditions.append(line[1:].strip())
            elif re.match(r'^\d+\.', line) and section == "steps":
                step_num = int(re.match(r'^(\d+)\.', line).group(1))
                action = line.split(".", 1)[1].strip()
                current_step = {"step": step_num, "action": action, "expected": ""}
            elif line.startswith("EXPECTED:") and current_step:
                current_step["expected"] = line.split(":", 1)[1].strip()
                steps.append(current_step)
                current_step = None
        if not name:
            return None
        test_steps = [TestStep(step=s["step"], action=s["action"], expected_result=s["expected"]) for s in steps]
        return TestCase(
            id=tc_id, key=tc_id, name=name, objective=name, priority=priority, status=TestStatus.APPROVED,
            folder="/", labels=labels, preconditions=preconditions, test_steps=test_steps, expected_results=[]
        )

def load_test_scenarios(source: Union[str, Path], format: str = "auto") -> ZephyrExport:
    parser = ZephyrParser()
    if format == "auto":
        if isinstance(source, (str, Path)):
            path = Path(source)
            if path.exists():
                format = "json" if path.suffix == ".json" else "text"
            else:
                format = "text"
    if format == "json":
        if isinstance(source, (str, Path)) and Path(source).exists():
            return parser.parse_from_file(source)
        else:
            return parser.parse_from_json(str(source))
    elif format == "text":
        if isinstance(source, (str, Path)) and Path(source).exists():
            content = Path(source).read_text(encoding="utf-8")
            return parser.parse_from_text(content)
        else:
            return parser.parse_from_text(str(source))
    else:
        raise ValueError(f"Unsupported format: {format}")
