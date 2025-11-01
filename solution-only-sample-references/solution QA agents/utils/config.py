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

"""Configuration management for QA Automation Agent - Optimized for maintainability."""

import os
import logging
import json
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    """Supported model providers."""
    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class ComplexityLevel(Enum):
    """Test complexity levels."""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    ENTERPRISE = "enterprise"


class ExpertSelectionStrategy(Enum):
    """Expert selection strategies."""
    INTELLIGENT = "intelligent"
    ROUND_ROBIN = "round_robin"
    LOAD_BALANCED = "load_balanced"
    PRIORITY_BASED = "priority_based"


@dataclass
class ModelConfig:
    """Model configuration settings."""
    primary_model: str = "gemini-2.5-pro"
    fallback_model: str = "gemini-2.0-flash-exp"
    provider: ModelProvider = ModelProvider.GOOGLE
    timeout: int = 60
    max_retries: int = 3
    temperature: float = 0.1
    max_tokens: Optional[int] = None


@dataclass
class QualityConfig:
    """Quality assurance configuration."""
    min_quality_score: float = 90.0
    expert_confidence_threshold: float = 85.0
    enable_security_validation: bool = True
    enable_performance_validation: bool = True
    enable_accessibility_validation: bool = True
    compliance_standards: List[str] = field(default_factory=list)
    reporting_formats: List[str] = field(default_factory=lambda: ["json", "html"])


@dataclass
class PerformanceConfig:
    """Performance optimization settings."""
    max_parallel_experts: int = 4
    request_timeout: int = 60
    max_retries: int = 3
    timeout_multiplier: float = 1.0
    enable_caching: bool = True
    cache_ttl_seconds: int = 3600


@dataclass
class ExpertConfig:
    """Expert coordination configuration."""
    available_frameworks: List[str] = field(default_factory=lambda: ["cypress", "karate", "newman", "playwright"])
    auto_select_experts: bool = True
    allow_multi_expert: bool = True
    selection_strategy: ExpertSelectionStrategy = ExpertSelectionStrategy.INTELLIGENT
    max_concurrent_experts: int = 4


class QAConfig:
    """Centralized configuration management for QA Automation Agent."""

    # Default supported models with priorities
    SUPPORTED_MODELS = {
        "gemini-2.5-pro": {"provider": "google", "priority": 1, "enterprise": True},
        "gemini-2.0-flash-exp": {"provider": "google", "priority": 2, "enterprise": True},
        "gemini-1.5-pro": {"provider": "google", "priority": 3, "enterprise": True},
        "claude-3-5-sonnet": {"provider": "anthropic", "priority": 4, "enterprise": True},
        "gpt-4o": {"provider": "openai", "priority": 5, "enterprise": True},
        "gpt-4-turbo": {"provider": "openai", "priority": 6, "enterprise": True}
    }

    # Default framework capabilities
    FRAMEWORK_CAPABILITIES = {
        "cypress": {
            "type": "web",
            "strengths": ["ui_testing", "e2e_testing", "visual_testing"],
            "enterprise_ready": True,
            "performance_impact": "medium"
        },
        "playwright": {
            "type": "web",
            "strengths": ["cross_browser", "mobile_testing", "api_testing"],
            "enterprise_ready": True,
            "performance_impact": "low"
        },
        "karate": {
            "type": "api",
            "strengths": ["bdd_testing", "api_testing", "performance_testing"],
            "enterprise_ready": True,
            "performance_impact": "low"
        },
        "newman": {
            "type": "api",
            "strengths": ["collection_testing", "team_collaboration", "ci_cd"],
            "enterprise_ready": True,
            "performance_impact": "low"
        }
    }

    def __init__(self):
        """Initialize configuration from environment variables and defaults."""
        self.model_config = self._load_model_config()
        self.quality_config = self._load_quality_config()
        self.performance_config = self._load_performance_config()
        self.expert_config = self._load_expert_config()

        # Agent configuration
        self.agent_name = os.getenv("QA_AGENT_NAME", "qa_automation_orchestrator")
        self.default_complexity = os.getenv("QA_DEFAULT_COMPLEXITY", "medium")

        # Logging configuration
        self.log_level = os.getenv("QA_LOG_LEVEL", "INFO")
        self.enable_debug = self._get_bool_env("QA_DEBUG", False)
        self.log_tool_calls = self._get_bool_env("QA_LOG_TOOL_CALLS", True)
        self.log_file_path = os.getenv("QA_LOG_FILE", "logs/qa_automation.log")

        # Feature flags
        self.enable_ci_cd_integration = self._get_bool_env("QA_CI_CD_INTEGRATION", True)
        self.enable_metrics_collection = self._get_bool_env("QA_METRICS_COLLECTION", True)
        self.enable_auto_healing = self._get_bool_env("QA_AUTO_HEALING", False)

        # Validation and setup
        self._validate_config()
        self._setup_logging()

        logger.info(f"QA Configuration initialized successfully")
        logger.info(f"Primary model: {self.model_config.primary_model}")
        logger.info(f"Available frameworks: {self.expert_config.available_frameworks}")

    def _load_model_config(self) -> ModelConfig:
        """Load model configuration from environment variables."""
        primary_model = os.getenv("QA_MODEL", "gemini-2.5-pro")
        fallback_model = os.getenv("QA_MODEL_FALLBACK", "gemini-2.0-flash-exp")

        # Validate models
        if primary_model not in self.SUPPORTED_MODELS:
            logger.warning(f"Primary model {primary_model} not supported, using gemini-2.5-pro")
            primary_model = "gemini-2.5-pro"

        provider_name = self.SUPPORTED_MODELS[primary_model]["provider"]
        provider = ModelProvider(provider_name)

        return ModelConfig(
            primary_model=primary_model,
            fallback_model=fallback_model,
            provider=provider,
            timeout=int(os.getenv("QA_MODEL_TIMEOUT", "60")),
            max_retries=int(os.getenv("QA_MODEL_MAX_RETRIES", "3")),
            temperature=float(os.getenv("QA_MODEL_TEMPERATURE", "0.1")),
            max_tokens=self._get_optional_int_env("QA_MODEL_MAX_TOKENS")
        )

    def _load_quality_config(self) -> QualityConfig:
        """Load quality configuration from environment variables."""
        return QualityConfig(
            min_quality_score=float(os.getenv("QA_MIN_QUALITY_SCORE", "90.0")),
            expert_confidence_threshold=float(os.getenv("QA_EXPERT_CONFIDENCE_THRESHOLD", "85.0")),
            enable_security_validation=self._get_bool_env("QA_SECURITY_VALIDATION", True),
            enable_performance_validation=self._get_bool_env("QA_PERFORMANCE_VALIDATION", True),
            enable_accessibility_validation=self._get_bool_env("QA_ACCESSIBILITY_VALIDATION", True),
            compliance_standards=self._parse_list_env("QA_COMPLIANCE_STANDARDS", []),
            reporting_formats=self._parse_list_env("QA_REPORTING_FORMATS", ["json", "html"])
        )

    def _load_performance_config(self) -> PerformanceConfig:
        """Load performance configuration from environment variables."""
        return PerformanceConfig(
            max_parallel_experts=int(os.getenv("QA_MAX_PARALLEL_EXPERTS", "4")),
            request_timeout=int(os.getenv("QA_REQUEST_TIMEOUT", "60")),
            max_retries=int(os.getenv("QA_MAX_RETRIES", "3")),
            timeout_multiplier=float(os.getenv("QA_TIMEOUT_MULTIPLIER", "1.0")),
            enable_caching=self._get_bool_env("QA_ENABLE_CACHING", True),
            cache_ttl_seconds=int(os.getenv("QA_CACHE_TTL_SECONDS", "3600"))
        )

    def _load_expert_config(self) -> ExpertConfig:
        """Load expert configuration from environment variables."""
        return ExpertConfig(
            available_frameworks=self._parse_list_env("QA_AVAILABLE_FRAMEWORKS",
                ["cypress", "karate", "newman", "playwright"]),
            auto_select_experts=self._get_bool_env("QA_AUTO_SELECT_EXPERTS", True),
            allow_multi_expert=self._get_bool_env("QA_ALLOW_MULTI_EXPERT", True),
            selection_strategy=ExpertSelectionStrategy(
                os.getenv("QA_EXPERT_SELECTION_STRATEGY", "intelligent")),
            max_concurrent_experts=int(os.getenv("QA_MAX_CONCURRENT_EXPERTS", "4"))
        )

    def _parse_list_env(self, env_var: str, default: list) -> list:
        """Parse comma-separated environment variable into list."""
        env_value = os.getenv(env_var)
        if env_value:
            return [item.strip() for item in env_value.split(",")]
        return default

    def _validate_config(self):
        """Validate configuration values."""

        # Validate model
        supported_models = [
            "gemini-2.5-pro", "gemini-2.0-flash-exp", "gemini-1.5-pro",
            "claude-3-5-sonnet", "gpt-4o", "gpt-4-turbo"
        ]
        if self.model_config.primary_model not in supported_models:
            logger.warning(f"Model {self.model_config.primary_model} not in supported models: {supported_models}")
            logger.info(f"Falling back to: {self.model_config.fallback_model}")

        # Validate timeouts and limits
        if self.performance_config.request_timeout < 10 or self.performance_config.request_timeout > 300:
            raise ValueError("Request timeout must be between 10 and 300 seconds")

        if self.performance_config.max_retries < 0 or self.performance_config.max_retries > 10:
            raise ValueError("Max retries must be between 0 and 10")

        if self.performance_config.max_parallel_experts < 1 or self.performance_config.max_parallel_experts > 10:
            raise ValueError("Max parallel experts must be between 1 and 10")

        # Validate quality thresholds
        if self.quality_config.min_quality_score < 50.0 or self.quality_config.min_quality_score > 100.0:
            raise ValueError("Min quality score must be between 50.0 and 100.0")

        # Validate frameworks
        valid_frameworks = ["cypress", "karate", "newman", "playwright"]
        invalid_frameworks = [fw for fw in self.expert_config.available_frameworks if fw not in valid_frameworks]
        if invalid_frameworks:
            raise ValueError(f"Invalid frameworks: {invalid_frameworks}. Valid: {valid_frameworks}")

        # Validate complexity
        valid_complexity = ["simple", "medium", "complex", "enterprise"]
        if self.default_complexity not in valid_complexity:
            raise ValueError(f"Default complexity must be one of: {valid_complexity}")

        # Validate expert selection strategy
        valid_strategies = ["intelligent", "round_robin", "load_balanced", "priority_based"]
        if self.expert_config.selection_strategy.value not in valid_strategies:
            raise ValueError(f"Expert selection strategy must be one of: {valid_strategies}")

        logger.info("QA configuration validation completed successfully")

    def _setup_logging(self):
        """Setup logging configuration."""

        # Create logs directory if it doesn't exist
        log_dir = os.path.dirname(self.log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Configure logging level
        numeric_level = getattr(logging, self.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=numeric_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file_path),
                logging.StreamHandler()
            ]
        )

        logger.info(f"Logging configured: Level={self.log_level}, Debug={self.enable_debug}")

    def _get_bool_env(self, env_var: str, default: bool) -> bool:
        """Parse boolean environment variable."""
        value = os.getenv(env_var, str(default)).lower()
        return value in ('true', '1', 'yes', 'on')

    def _get_optional_int_env(self, env_var: str) -> Optional[int]:
        """Parse optional integer environment variable."""
        value = os.getenv(env_var)
        return int(value) if value else None

    def _get_json_env(self, env_var: str, default: Dict[str, Any]) -> Dict[str, Any]:
        """Parse JSON environment variable with fallback to default."""
        try:
            value = os.getenv(env_var)
            return json.loads(value) if value else default
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Invalid JSON in {env_var}, using default")
            return default

    def get_model_config(self) -> Dict[str, Any]:
        """Get model configuration with fallback support."""
        return {
            "primary_model": self.model_config.primary_model,
            "fallback_model": self.model_config.fallback_model,
            "timeout": self.performance_config.request_timeout,
            "max_retries": self.performance_config.max_retries
        }

    def get_expert_config(self) -> Dict[str, Any]:
        """Get expert selection and coordination configuration."""
        return {
            "available_frameworks": self.expert_config.available_frameworks,
            "max_parallel_experts": self.performance_config.max_parallel_experts,
            "auto_select": self.expert_config.auto_select_experts,
            "allow_multi_expert": self.expert_config.allow_multi_expert,
            "selection_strategy": self.expert_selection_strategy,
            "confidence_threshold": self.quality_config.expert_confidence_threshold
        }

    def get_quality_config(self) -> Dict[str, Any]:
        """Get quality assurance configuration."""
        return {
            "min_quality_score": self.quality_config.min_quality_score,
            "enable_security_validation": self.quality_config.enable_security_validation,
            "compliance_standards": self.quality_config.compliance_standards,
            "reporting_format": self.quality_config.reporting_formats
        }

    def get_performance_config(self) -> Dict[str, Any]:
        """Get performance configuration."""
        return {
            "request_timeout": self.performance_config.request_timeout,
            "max_retries": self.performance_config.max_retries,
            "max_parallel_experts": self.performance_config.max_parallel_experts,
            "default_complexity": self.default_complexity
        }

    def get_integration_config(self) -> Dict[str, Any]:
        """Get CI/CD and integration configuration."""
        return {
            "enable_ci_cd": self.enable_ci_cd_integration,
            "reporting_formats": self.quality_config.reporting_formats,
            "log_tool_calls": self.log_tool_calls
        }

    def is_framework_enabled(self, framework: str) -> bool:
        """Check if a specific framework is enabled."""
        return framework.lower() in [fw.lower() for fw in self.expert_config.available_frameworks]

    def get_complexity_config(self, complexity: str) -> Dict[str, Any]:
        """Get configuration for specific complexity level."""

        complexity_configs = {
            "simple": {
                "max_parallel_experts": 1,
                "timeout_multiplier": 0.5,
                "retry_count": 2,
                "quality_threshold": 85.0
            },
            "medium": {
                "max_parallel_experts": 2,
                "timeout_multiplier": 1.0,
                "retry_count": 3,
                "quality_threshold": 90.0
            },
            "complex": {
                "max_parallel_experts": 3,
                "timeout_multiplier": 1.5,
                "retry_count": 4,
                "quality_threshold": 95.0
            },
            "enterprise": {
                "max_parallel_experts": 4,
                "timeout_multiplier": 2.0,
                "retry_count": 5,
                "quality_threshold": 97.0
            }
        }

        return complexity_configs.get(complexity, complexity_configs["medium"])

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for serialization."""
        return {
            "model": self.model_config.primary_model,
            "model_fallback": self.model_config.fallback_model,
            "agent_name": self.agent_name,
            "max_parallel_experts": self.performance_config.max_parallel_experts,
            "available_frameworks": self.expert_config.available_frameworks,
            "request_timeout": self.performance_config.request_timeout,
            "max_retries": self.performance_config.max_retries,
            "default_complexity": self.default_complexity,
            "min_quality_score": self.quality_config.min_quality_score,
            "expert_confidence_threshold": self.quality_config.expert_confidence_threshold,
            "log_level": self.log_level,
            "enable_debug": self.enable_debug,
            "log_tool_calls": self.log_tool_calls,
            "auto_select_experts": self.expert_config.auto_select_experts,
            "allow_multi_expert": self.expert_config.allow_multi_expert,
            "expert_selection_strategy": self.expert_selection_strategy,
            "enable_security_validation": self.quality_config.enable_security_validation,
            "compliance_standards": self.quality_config.compliance_standards,
            "enable_ci_cd_integration": self.enable_ci_cd_integration,
            "reporting_format": self.quality_config.reporting_formats
        }

    def get_framework_priority(self, framework: str, default: int) -> int:
        """Get framework execution priority from environment variables."""
        env_key = f"QA_{framework.upper()}_PRIORITY"
        return int(os.getenv(env_key, str(default)))

    def get_maintenance_schedule(self) -> Dict[str, List[str]]:
        """Get maintenance schedule configuration."""
        return {
            "daily": self._parse_list_env("QA_DAILY_MAINTENANCE",
                ["Monitor execution metrics", "Update test data"]),
            "weekly": self._parse_list_env("QA_WEEKLY_MAINTENANCE",
                ["Review configurations", "Optimize performance"]),
            "monthly": self._parse_list_env("QA_MONTHLY_MAINTENANCE",
                ["Comprehensive audit", "Update dependencies"])
        }

    def get_extraction_patterns(self) -> Dict[str, Any]:
        """Get configurable patterns for requirement extraction."""
        return {
            "should_pattern": os.getenv("QA_SHOULD_PATTERN", r'should\s+([^.]+)'),
            "user_pattern": os.getenv("QA_USER_PATTERN", r'user\s+(can|must|should)\s+([^.]+)'),
            "default_criteria": self._parse_list_env("QA_DEFAULT_CRITERIA", [
                "load successfully",
                "display correct information",
                "handle user interactions properly",
                "provide appropriate feedback"
            ]),
            "scenario_pattern": os.getenv("QA_SCENARIO_PATTERN", r'scenario[:\s]+([^.]+)'),
            "test_pattern": os.getenv("QA_TEST_PATTERN", r'test\s+([^.]+)'),
            "scenario_templates": {
                "login": self._parse_list_env("QA_LOGIN_SCENARIOS", ["valid login", "invalid login", "logout"]),
                "payment": self._parse_list_env("QA_PAYMENT_SCENARIOS", ["successful payment", "failed payment", "payment validation"]),
                "search": self._parse_list_env("QA_SEARCH_SCENARIOS", ["successful search", "no results search", "invalid search"]),
                "generic": self._parse_list_env("QA_GENERIC_SCENARIOS", ["happy path flow", "error handling", "edge cases"])
            }
        }

    def get_endpoint_pattern(self) -> str:
        """Get API endpoint extraction pattern."""
        return os.getenv("QA_ENDPOINT_PATTERN", r'/api/[\w/]+')

    def get_default_endpoints_template(self) -> List[Dict[str, str]]:
        """Get default API endpoints template."""
        return [
            {"path": "/api/{domain}/health", "method": "GET", "description": "Health check for {domain}"},
            {"path": "/api/{domain}/status", "method": "GET", "description": "Status check for {domain}"},
            {"path": "/api/{domain}/data", "method": "GET", "description": "Get {domain} data"},
            {"path": "/api/{domain}/data", "method": "POST", "description": "Create {domain} data"}
        ]

    def get_http_method_keywords(self) -> Dict[str, List[str]]:
        """Get HTTP method detection keywords."""
        return {
            "POST": self._parse_list_env("QA_POST_KEYWORDS", ["create", "add", "post", "submit"]),
            "PUT": self._parse_list_env("QA_PUT_KEYWORDS", ["update", "modify", "put", "replace"]),
            "PATCH": self._parse_list_env("QA_PATCH_KEYWORDS", ["patch", "partial", "edit"]),
            "DELETE": self._parse_list_env("QA_DELETE_KEYWORDS", ["delete", "remove", "destroy"])
        }

    def get_scenario_patterns(self) -> Dict[str, Any]:
        """Get scenario extraction patterns."""
        return self.get_extraction_patterns()

    @property
    def max_acceptance_criteria(self) -> int:
        """Maximum number of acceptance criteria to extract."""
        return int(os.getenv("QA_MAX_ACCEPTANCE_CRITERIA", "5"))

    @property
    def max_api_endpoints(self) -> int:
        """Maximum number of API endpoints to process."""
        return int(os.getenv("QA_MAX_API_ENDPOINTS", "10"))

    @property
    def max_test_scenarios(self) -> int:
        """Maximum number of test scenarios to generate."""
        return int(os.getenv("QA_MAX_TEST_SCENARIOS", "10"))

    def get_framework_capabilities(self, framework: str) -> Dict[str, Any]:
        """Get capabilities for a specific framework."""
        return self.FRAMEWORK_CAPABILITIES.get(framework, {})

    def is_model_enterprise_ready(self, model: Optional[str] = None) -> bool:
        """Check if model is enterprise ready."""
        model = model or self.model_config.primary_model
        return self.SUPPORTED_MODELS.get(model, {}).get("enterprise", False)

    def get_optimal_model_for_complexity(self, complexity: str) -> str:
        """Get optimal model for given complexity level."""
        if complexity == "enterprise":
            # Use highest priority enterprise model
            enterprise_models = {k: v for k, v in self.SUPPORTED_MODELS.items() if v.get("enterprise")}
            if enterprise_models:
                return min(enterprise_models.keys(), key=lambda x: enterprise_models[x]["priority"])
        return self.model_config.primary_model

    def get_framework_selection_weights(self) -> Dict[str, float]:
        """Get framework selection weights for intelligent selection."""
        return self._get_json_env("QA_FRAMEWORK_WEIGHTS", {
            "cypress": 1.0,
            "playwright": 0.9,
            "karate": 1.0,
            "newman": 0.8
        })

    def get_security_config(self) -> Dict[str, Any]:
        """Get security validation configuration."""
        return {
            "enable_security_scanning": self._get_bool_env("QA_SECURITY_SCANNING", True),
            "enable_vulnerability_checks": self._get_bool_env("QA_VULNERABILITY_CHECKS", True),
            "enable_dependency_scanning": self._get_bool_env("QA_DEPENDENCY_SCANNING", True),
            "security_standards": self._parse_list_env("QA_SECURITY_STANDARDS", ["OWASP", "NIST"]),
            "max_security_score": float(os.getenv("QA_MAX_SECURITY_SCORE", "100.0"))
        }

    def get_accessibility_config(self) -> Dict[str, Any]:
        """Get accessibility validation configuration."""
        return {
            "enable_a11y_testing": self.quality_config.enable_accessibility_validation,
            "wcag_level": os.getenv("QA_WCAG_LEVEL", "AA"),
            "a11y_standards": self._parse_list_env("QA_A11Y_STANDARDS", ["WCAG", "Section508"]),
            "color_contrast_ratio": float(os.getenv("QA_COLOR_CONTRAST_RATIO", "4.5"))
        }

    def get_cache_config(self) -> Dict[str, Any]:
        """Get caching configuration."""
        return {
            "enable_caching": self.performance_config.enable_caching,
            "cache_ttl": self.performance_config.cache_ttl_seconds,
            "cache_provider": os.getenv("QA_CACHE_PROVIDER", "memory"),
            "cache_size_limit": int(os.getenv("QA_CACHE_SIZE_LIMIT", "1000"))
        }

    def validate_environment(self) -> Dict[str, Any]:
        """Validate environment setup and return status."""
        validation_results = {
            "model_validation": self._validate_model_access(),
            "framework_validation": self._validate_frameworks(),
            "dependency_validation": self._validate_dependencies(),
            "configuration_validation": self._validate_configuration_completeness()
        }

        overall_status = all(result["status"] == "valid" for result in validation_results.values())
        validation_results["overall_status"] = "valid" if overall_status else "invalid"

        return validation_results

    def _validate_model_access(self) -> Dict[str, Any]:
        """Validate model access and availability."""
        try:
            # Basic validation - in real implementation would test API access
            model_info = self.SUPPORTED_MODELS.get(self.model_config.primary_model)
            if not model_info:
                return {"status": "invalid", "message": f"Unsupported model: {self.model_config.primary_model}"}

            return {
                "status": "valid",
                "model": self.model_config.primary_model,
                "provider": model_info["provider"],
                "enterprise_ready": model_info.get("enterprise", False)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _validate_frameworks(self) -> Dict[str, Any]:
        """Validate framework availability."""
        invalid_frameworks = []
        for framework in self.expert_config.available_frameworks:
            if framework not in self.FRAMEWORK_CAPABILITIES:
                invalid_frameworks.append(framework)

        if invalid_frameworks:
            return {
                "status": "invalid",
                "message": f"Invalid frameworks: {invalid_frameworks}",
                "valid_frameworks": list(self.FRAMEWORK_CAPABILITIES.keys())
            }

        return {
            "status": "valid",
            "frameworks": self.expert_config.available_frameworks,
            "capabilities": {fw: self.FRAMEWORK_CAPABILITIES[fw] for fw in self.expert_config.available_frameworks}
        }

    def _validate_dependencies(self) -> Dict[str, Any]:
        """Validate required dependencies."""
        # This would validate actual package installations in real implementation
        return {
            "status": "valid",
            "message": "Dependency validation passed"
        }

    def _validate_configuration_completeness(self) -> Dict[str, Any]:
        """Validate configuration completeness."""
        required_configs = ["model_config", "quality_config", "performance_config", "expert_config"]
        missing_configs = []

        for config in required_configs:
            if not hasattr(self, config):
                missing_configs.append(config)

        if missing_configs:
            return {
                "status": "invalid",
                "message": f"Missing configurations: {missing_configs}"
            }

        return {
            "status": "valid",
            "message": "All required configurations present"
        }

    def get_monitoring_config(self) -> Dict[str, Any]:
        """Get monitoring and metrics configuration."""
        return {
            "enable_metrics": self.enable_metrics_collection,
            "metrics_interval": int(os.getenv("QA_METRICS_INTERVAL", "30")),
            "enable_health_checks": self._get_bool_env("QA_HEALTH_CHECKS", True),
            "enable_performance_monitoring": self._get_bool_env("QA_PERFORMANCE_MONITORING", True),
            "alert_thresholds": self._get_json_env("QA_ALERT_THRESHOLDS", {
                "response_time_ms": 5000,
                "error_rate_percent": 5.0,
                "quality_score_min": 85.0
            })
        }

    def export_config(self, format: str = "json") -> Union[str, Dict[str, Any]]:
        """Export configuration in specified format."""
        config_dict = self.to_dict()

        if format.lower() == "json":
            return json.dumps(config_dict, indent=2, default=str)
        elif format.lower() == "dict":
            return config_dict
        else:
            raise ValueError(f"Unsupported export format: {format}")

    @property
    def model(self) -> str:
        """Get primary model for backward compatibility."""
        return self.model_config.primary_model

    @property
    def available_frameworks(self) -> List[str]:
        """Get available frameworks for backward compatibility."""
        return self.expert_config.available_frameworks

    @property
    def auto_select_experts(self) -> bool:
        """Get auto select experts for backward compatibility."""
        return self.expert_config.auto_select_experts

    @property
    def allow_multi_expert(self) -> bool:
        """Get allow multi expert for backward compatibility."""
        return self.expert_config.allow_multi_expert

    @property
    def expert_selection_strategy(self) -> str:
        """Get expert selection strategy for backward compatibility."""
        return self.expert_config.selection_strategy.value

    @property
    def max_parallel_experts(self) -> int:
        """Get max parallel experts for backward compatibility."""
        return self.performance_config.max_parallel_experts

    @property
    def min_quality_score(self) -> float:
        """Get min quality score for backward compatibility."""
        return self.quality_config.min_quality_score

    @property
    def enable_security_validation(self) -> bool:
        """Get enable security validation for backward compatibility."""
        return self.quality_config.enable_security_validation

    @property
    def reporting_format(self) -> str:
        """Get reporting format for backward compatibility."""
        return ",".join(self.quality_config.reporting_formats)


# Global configuration instance
qa_config = QAConfig()
