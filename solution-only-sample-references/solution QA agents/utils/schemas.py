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

"""
Structured Output Schemas for QA Automation Agent.

This module defines Pydantic models that enforce structured, validated outputs
from the AI agents, significantly reducing hallucinations and improving code quality.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Dict, Any, Optional, Literal
from enum import Enum
from datetime import datetime


class TestFramework(str, Enum):
    """Supported test automation frameworks."""
    CYPRESS = "cypress"
    KARATE = "karate"
    NEWMAN = "newman"
    PLAYWRIGHT = "playwright"


class HTTPMethod(str, Enum):
    """Valid HTTP methods."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class TestComplexity(str, Enum):
    """Test complexity levels."""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    ENTERPRISE = "enterprise"


class TestFile(BaseModel):
    """Represents a generated test file with validation."""
    
    filename: str = Field(
        ..., 
        description="File name with extension (e.g., login.spec.js, api-tests.feature)",
        min_length=1,
        max_length=255
    )
    path: str = Field(
        ..., 
        description="Relative path from project root (e.g., cypress/e2e/auth/)",
        pattern=r'^[a-zA-Z0-9_\-/\.]+$'
    )
    content: str = Field(
        ..., 
        description="Complete file content - MUST be valid, executable code",
        min_length=10
    )
    language: Literal["javascript", "typescript", "java", "gherkin", "json", "yaml"] = Field(
        ...,
        description="Programming language of the file"
    )
    line_count: int = Field(
        default=0,
        description="Number of lines in the file",
        ge=0
    )
    
    @field_validator('filename')
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate file extension matches test framework conventions."""
        valid_extensions = {
            '.feature',      # Karate/Gherkin
            '.js',           # Cypress/Playwright/Newman
            '.ts',           # TypeScript tests
            '.spec.js',      # Spec files
            '.spec.ts',      # TypeScript spec files
            '.test.js',      # Test files
            '.test.ts',      # TypeScript test files
            '.json',         # Newman collections
            '.yaml',         # Config files
            '.yml',          # Config files
            '.java',         # Karate Java runners
            '.xml',          # Maven/config files
        }
        
        if not any(v.endswith(ext) for ext in valid_extensions):
            raise ValueError(
                f"Invalid file extension. Must end with one of: {', '.join(valid_extensions)}"
            )
        
        # Check for suspicious patterns
        if '..' in v or v.startswith('/'):
            raise ValueError("Filename contains invalid path characters")
            
        return v
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate content is not placeholder text."""
        placeholder_patterns = [
            'TODO',
            'FIXME',
            'placeholder',
            'test@test.com',
            'example.com',
            'your-api-key-here',
            'replace-this',
        ]
        
        content_lower = v.lower()
        found_placeholders = [p for p in placeholder_patterns if p.lower() in content_lower]
        
        if found_placeholders:
            raise ValueError(
                f"Content contains placeholder text: {', '.join(found_placeholders)}. "
                "Generate real, production-ready code."
            )
        
        return v
    
    @model_validator(mode='after')
    def calculate_line_count(self):
        """Calculate line count from content."""
        if self.content:
            self.line_count = len(self.content.splitlines())
        return self


class TestEndpoint(BaseModel):
    """Represents an API endpoint that is tested."""
    
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"] = Field(
        ...,
        description="HTTP method"
    )
    path: str = Field(
        ..., 
        description="Endpoint path - MUST start with /",
        pattern=r'^/[a-zA-Z0-9_\-/{}]*$'
    )
    description: str = Field(
        ..., 
        description="Clear description of what this endpoint does",
        min_length=5,
        max_length=500
    )
    test_scenarios: List[str] = Field(
        ..., 
        description="List of test scenarios covering this endpoint",
        min_length=2  # Must have at least positive and negative scenarios
    )
    status_codes_tested: List[int] = Field(
        default_factory=list,
        description="HTTP status codes tested (e.g., 200, 400, 401, 404)"
    )
    
    @field_validator('test_scenarios')
    @classmethod
    def validate_scenarios(cls, v: List[str]) -> List[str]:
        """Ensure both positive and negative scenarios are present."""
        scenarios_text = ' '.join(v).lower()
        
        # Check for positive scenarios
        positive_keywords = ['success', 'valid', 'correct', '200', 'ok', 'pass']
        has_positive = any(keyword in scenarios_text for keyword in positive_keywords)
        
        # Check for negative scenarios
        negative_keywords = ['fail', 'error', 'invalid', '400', '401', '403', '404', '500']
        has_negative = any(keyword in scenarios_text for keyword in negative_keywords)
        
        if not has_positive or not has_negative:
            raise ValueError(
                "Test scenarios MUST include both positive (success) and negative (error) cases. "
                f"Has positive: {has_positive}, Has negative: {has_negative}"
            )
        
        return v
    
    @field_validator('status_codes_tested')
    @classmethod
    def validate_status_codes(cls, v: List[int]) -> List[int]:
        """Validate status codes are realistic."""
        valid_codes = {200, 201, 202, 204, 400, 401, 403, 404, 422, 500, 502, 503}
        
        for code in v:
            if code not in valid_codes:
                raise ValueError(f"Invalid HTTP status code: {code}")
        
        return v


class SyntaxValidation(BaseModel):
    """Result of syntax validation for generated code."""
    
    is_valid: bool = Field(
        ..., 
        description="Whether the code passes syntax validation"
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Critical syntax errors that prevent execution"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-critical issues that should be addressed"
    )
    framework: Literal["cypress", "karate", "newman", "playwright"] = Field(
        ...,
        description="Framework being validated (cypress, karate, newman, or playwright)"
    )
    validated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Timestamp of validation"
    )
    
    @property
    def has_critical_errors(self) -> bool:
        """Check if there are critical errors."""
        return len(self.errors) > 0


class QualityMetrics(BaseModel):
    """Quality metrics for generated test code."""
    
    coverage_score: int = Field(
        ..., 
        description="Endpoint coverage score (0-100)",
        ge=0, 
        le=100
    )
    syntax_score: int = Field(
        ..., 
        description="Syntax correctness score (0-100)",
        ge=0, 
        le=100
    )
    best_practices_score: int = Field(
        ..., 
        description="Adherence to framework best practices (0-100)",
        ge=0, 
        le=100
    )
    security_score: int = Field(
        default=100,
        description="Security issues check (0-100, 100=no issues)",
        ge=0, 
        le=100
    )
    overall_score: int = Field(
        ..., 
        description="Overall quality score (0-100)",
        ge=0, 
        le=100
    )
    
    issues_found: List[str] = Field(
        default_factory=list,
        description="Specific quality issues detected"
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Recommendations to improve quality"
    )
    hallucinations_detected: List[str] = Field(
        default_factory=list,
        description="Detected hallucinations (invented endpoints, fake methods, etc.)"
    )
    
    @model_validator(mode='after')
    def validate_scores_consistency(self):
        """Ensure overall score is consistent with component scores."""
        component_avg = (
            self.coverage_score + 
            self.syntax_score + 
            self.best_practices_score + 
            self.security_score
        ) / 4
        
        # Overall score should be close to component average
        if abs(self.overall_score - component_avg) > 10:
            self.overall_score = int(component_avg)
        
        return self
    
    @property
    def is_production_ready(self) -> bool:
        """Determine if code meets production quality standards."""
        return (
            self.overall_score >= 80
            and self.syntax_score >= 90
            and self.security_score >= 95
            and len(self.hallucinations_detected) == 0
        )


class TestSuiteMetadata(BaseModel):
    """Metadata about the test suite generation."""
    
    domain: str = Field(
        ..., 
        description="Business domain (e.g., banking, ecommerce, healthcare)"
    )
    complexity: Literal["simple", "medium", "complex", "enterprise"] = Field(
        default="medium",
        description="Complexity level of the test suite"
    )
    generation_timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="When the tests were generated"
    )
    model_used: str = Field(
        default="gemini-2.5-pro",
        description="AI model that generated the tests"
    )
    total_endpoints: int = Field(
        default=0,
        description="Total number of endpoints in specification",
        ge=0
    )
    endpoints_covered: int = Field(
        default=0,
        description="Number of endpoints with generated tests",
        ge=0
    )
    estimated_execution_time: Optional[int] = Field(
        default=None,
        description="Estimated test execution time in seconds"
    )
    
    @property
    def coverage_percentage(self) -> float:
        """Calculate endpoint coverage percentage."""
        if self.total_endpoints == 0:
            return 0.0
        return round((self.endpoints_covered / self.total_endpoints) * 100, 2)


class TestSuiteOutput(BaseModel):
    """
    Complete structured output from QA Automation Agent.
    
    This model enforces:
    - Valid, executable code
    - Complete endpoint coverage
    - Quality validation
    - Anti-hallucination measures
    """
    
    framework: Literal["cypress", "karate", "newman", "playwright"] = Field(
        ...,
        description="Testing framework used (cypress, karate, newman, or playwright)"
    )
    
    # Generated files (VALIDATED)
    test_files: List[TestFile] = Field(
        ..., 
        description="Generated test files - must be valid, executable code",
        min_length=1
    )
    config_files: List[TestFile] = Field(
        default_factory=list,
        description="Configuration files (package.json, pom.xml, etc.)"
    )
    
    # Endpoints coverage (VALIDATED)
    endpoints_covered: List[TestEndpoint] = Field(
        ..., 
        description="API endpoints covered by tests",
        min_length=1
    )
    
    # Validation results
    syntax_validation: SyntaxValidation = Field(
        ..., 
        description="Syntax validation results"
    )
    quality_metrics: QualityMetrics = Field(
        ..., 
        description="Quality metrics and scores"
    )
    
    # Metadata
    metadata: TestSuiteMetadata = Field(
        ..., 
        description="Generation metadata"
    )
    
    # Execution instructions
    execution_instructions: str = Field(
        ..., 
        description="Clear instructions on how to execute the tests",
        min_length=50
    )
    
    @field_validator('test_files')
    @classmethod
    def validate_unique_filenames(cls, v: List[TestFile]) -> List[TestFile]:
        """Ensure all filenames are unique."""
        filenames = [f.filename for f in v]
        
        if len(filenames) != len(set(filenames)):
            duplicates = [f for f in filenames if filenames.count(f) > 1]
            raise ValueError(f"Duplicate filenames detected: {set(duplicates)}")
        
        return v
    
    @model_validator(mode='after')
    def validate_consistency(self):
        """Validate consistency across all fields."""
        # Update metadata
        self.metadata.endpoints_covered = len(self.endpoints_covered)
        
        # Ensure syntax validation matches framework
        if self.syntax_validation.framework != self.framework:
            raise ValueError(
                f"Framework mismatch: {self.framework} != {self.syntax_validation.framework}"
            )
        
        # Check for hallucinations in quality metrics
        if self.quality_metrics.hallucinations_detected:
            self.syntax_validation.errors.append(
                f"Hallucinations detected: {', '.join(self.quality_metrics.hallucinations_detected[:3])}"
            )
            self.syntax_validation.is_valid = False
        
        return self
    
    @property
    def is_production_ready(self) -> bool:
        """Determine if the test suite is ready for production use."""
        return (
            self.syntax_validation.is_valid
            and self.quality_metrics.is_production_ready
            and len(self.test_files) > 0
            and len(self.endpoints_covered) > 0
        )
    
    @property
    def total_lines_of_code(self) -> int:
        """Calculate total lines of code generated."""
        return sum(f.line_count for f in self.test_files + self.config_files)


class ValidationRequest(BaseModel):
    """Request to validate generated test code."""
    
    framework: Literal["cypress", "karate", "newman", "playwright"]
    code_content: str = Field(..., min_length=10)
    expected_endpoints: List[str] = Field(..., min_length=1)
    domain: str


class ValidationResponse(BaseModel):
    """Response from code validation."""
    
    is_valid: bool
    syntax_validation: SyntaxValidation
    quality_metrics: QualityMetrics
    can_proceed: bool = Field(
        ...,
        description="Whether code quality is sufficient to proceed"
    )
