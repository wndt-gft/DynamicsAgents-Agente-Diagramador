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
Agent Engine Application Module
===============================

This module provides the main application class for the Architect Diagram Agent,
handling deployment to Vertex AI Agent Engine with proper logging, tracing,
and feedback mechanisms.

The module follows clean architecture principles with proper separation of concerns,
dependency injection, and comprehensive error handling.
"""

import asyncio
import copy
import datetime
import json
import logging
import os
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Union
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

logger = logging.getLogger(__name__)

# ===== DEPENDENCY IMPORTS WITH GRACEFUL FALLBACKS =====

# Pydantic for data validation
try:
    from pydantic import BaseModel, Field

    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False


    # Minimal BaseModel fallback
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self):
            return self.__dict__

        @classmethod
        def model_validate(cls, obj):
            return cls(**obj)


    def Field(*args, **kwargs):
        return None

# Google Auth
try:
    import google.auth
    from google.auth import credentials

    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False


    class GoogleAuthFallback:
        """Fallback for Google Auth when not available."""

        @staticmethod
        def default():
            return (None, os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project"))


    class google:  # type: ignore
        auth = GoogleAuthFallback()

# Vertex AI and Agent Engines
try:
    import vertexai
    from vertexai import agent_engines
    from vertexai.preview.reasoning_engines import AdkApp

    VERTEX_AI_AVAILABLE = True
except ImportError:
    VERTEX_AI_AVAILABLE = False


    class VertexAIFallback:
        """Fallback for Vertex AI when not available."""

        def init(self, *args, **kwargs):
            logger.info("Vertex AI not available - running in fallback mode")


    vertexai = VertexAIFallback()  # type: ignore


    class agent_engines:  # type: ignore
        @staticmethod
        def list(filter: Optional[str] = None) -> List:
            return []

        @staticmethod
        def create(**kwargs):
            class RemoteAgent:
                resource_name = "fallback/agents/test"

                def update(self, **kwargs):
                    return self

            return RemoteAgent()


    class AdkApp:  # type: ignore
        """Fallback ADK Application base class."""

        def __init__(self, *args, **kwargs):
            self._tmpl_attrs = kwargs

        def set_up(self) -> None:
            """Base setup method."""
            pass

        def register_operations(self) -> Dict[str, List[str]]:
            """Register available operations."""
            return {"": []}

        def stream_query(self, message: str, user_id: str):
            """Stream query handling."""
            return []

# Artifacts Service
try:
    from google.adk.artifacts import GcsArtifactService

    ARTIFACTS_SERVICE_AVAILABLE = True
except ImportError:
    ARTIFACTS_SERVICE_AVAILABLE = False


    class GcsArtifactService:  # type: ignore
        """Fallback GCS Artifact Service."""

        def __init__(self, bucket_name: str):
            self.bucket_name = bucket_name
            logger.info(f"GcsArtifactService fallback initialized with bucket: {bucket_name}")

# Cloud Logging
try:
    from google.cloud import logging as google_cloud_logging

    CLOUD_LOGGING_AVAILABLE = True
except ImportError:
    CLOUD_LOGGING_AVAILABLE = False


    class DummyLogger:
        """Fallback logger implementation."""

        def log_struct(self, data: Dict, severity: str = "INFO"):
            logger.info(f"[{severity}] {json.dumps(data, indent=2)}")


    class DummyLoggingClient:
        """Fallback logging client."""

        def logger(self, name: str):
            return DummyLogger()


    class google_cloud_logging:  # type: ignore
        Client = DummyLoggingClient

# OpenTelemetry Tracing
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False


    class NoOpSpanProcessor:
        """No-op span processor for when tracing is not available."""

        def __init__(self, *args, **kwargs):
            pass


    class NoOpProvider:
        """No-op tracer provider."""

        def add_span_processor(self, processor):
            pass


    class trace:  # type: ignore
        @staticmethod
        def set_tracer_provider(provider):
            pass


    BatchSpanProcessor = NoOpSpanProcessor  # type: ignore
    TracerProvider = NoOpProvider  # type: ignore

# ===== LOCAL IMPORTS WITH FALLBACKS =====

try:
    from app.agent import root_agent

    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False
    root_agent = None  # Will be created as fallback below

try:
    from app.utils.gcs import create_bucket_if_not_exists

    GCS_UTILS_AVAILABLE = True
except ImportError:
    GCS_UTILS_AVAILABLE = False


    def create_bucket_if_not_exists(bucket_name: str, project: str, location: str) -> None:
        """Fallback function when GCS utils not available."""
        logger.info(f"📦 Would create bucket: {bucket_name} in {project}/{location}")

try:
    from app.utils.tracing import CloudTraceLoggingSpanExporter

    TRACING_UTILS_AVAILABLE = True
except ImportError:
    TRACING_UTILS_AVAILABLE = False


    class CloudTraceLoggingSpanExporter:
        """Fallback span exporter."""

        def __init__(self, project_id: str):
            self.project_id = project_id

        def export(self, spans):
            logger.debug(f"Would export {len(spans) if spans else 0} spans to {self.project_id}")
            return True


# Feedback model
class Feedback(BaseModel):
    """Feedback model for user responses."""
    score: int = Field(..., ge=1, le=5, description="Feedback score from 1 to 5")
    text: str = Field(..., description="Feedback text")
    invocation_id: str = Field(..., description="Unique invocation identifier")
    timestamp: Optional[str] = Field(None, description="Feedback timestamp")
    user_id: Optional[str] = Field(None, description="User identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")


def _normalize_feedback_score(raw_score: Any) -> int:
    """Validate and normalise user provided feedback scores.

    Accepts integer values or digit-only strings within the inclusive range 1-5.
    Values outside the range or non-integer numbers raise ``ValueError`` which
    signals that the feedback should be rejected.
    """

    if isinstance(raw_score, str):
        stripped = raw_score.strip()
        if not stripped.isdigit():
            raise ValueError("Score string must contain only digits")
        raw_score = int(stripped)
    elif isinstance(raw_score, bool):
        raise ValueError("Boolean score is not allowed")
    elif isinstance(raw_score, (int,)):
        pass
    elif isinstance(raw_score, float):
        if raw_score.is_integer():
            raw_score = int(raw_score)
        else:
            raise ValueError("Score must be an integer between 1 and 5")
    else:
        raise ValueError("Unsupported score type")

    if not 1 <= int(raw_score) <= 5:
        raise ValueError("Score must be between 1 and 5")

    return int(raw_score)


# Create fallback root_agent if needed
if not AGENT_AVAILABLE:
    class FallbackAgent:
        """Fallback agent for testing/development."""

        def __init__(self):
            self.name = "Architect Diagram Agent (Fallback)"
            self.version = "5.1.0"
            self.description = "Architecture agent in fallback mode"

        def process(self, message: str) -> str:
            return f"Fallback response for: {message}"

        def setup(self) -> None:
            logger.info("FallbackAgent setup completed")

        async def stream_async(self, message: str) -> str:
            return self.process(message)


    root_agent = FallbackAgent()


# ===== CONFIGURATION DATACLASSES =====

@dataclass
class DeploymentConfig:
    """Configuration for agent deployment."""
    project: str
    location: str = "us-central1"
    agent_name: str = "diagramador"
    requirements_file: str = ".requirements.txt"
    env_vars: Dict[str, str] = field(default_factory=dict)
    description: str = "Architect Diagram Agent built with Google ADK"
    max_concurrent_requests: int = 10
    timeout_seconds: int = 300
    memory_limit: str = "2Gi"
    cpu_limit: str = "1"

    @property
    def staging_bucket_uri(self) -> str:
        """Get staging bucket URI."""
        return f"gs://{self.project}-agent-engine"

    @property
    def artifacts_bucket_name(self) -> str:
        """Get artifacts bucket name."""
        return f"{self.project}-diagramador-logs-data"

    def validate(self) -> None:
        """Validate configuration."""
        if not self.project:
            raise ValueError("Project ID is required")
        if not self.agent_name:
            raise ValueError("Agent name is required")
        if self.timeout_seconds < 1:
            raise ValueError("Timeout must be at least 1 second")
        if self.max_concurrent_requests < 1:
            raise ValueError("Max concurrent requests must be at least 1")


@dataclass
class LoggingConfig:
    """Configuration for logging and tracing."""
    enable_cloud_logging: bool = True
    enable_tracing: bool = True
    log_level: str = "INFO"
    project_id: Optional[str] = None
    log_to_file: bool = False
    log_file_path: str = "agent_engine.log"

    def __post_init__(self):
        """Post-initialization setup."""
        if not self.project_id:
            self.project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project")


# ===== MAIN APPLICATION CLASS =====

class AgentEngineApp(AdkApp):
    """
    Main application class for the Architect Diagram Agent.

    This class extends AdkApp to provide additional functionality
    for deployment, logging, tracing, and feedback handling.
    """

    def __init__(
            self,
            agent: Any = None,
            deployment_config: Optional[DeploymentConfig] = None,
            logging_config: Optional[LoggingConfig] = None
    ):
        """
        Initialize the Agent Engine Application.

        Args:
            agent: The agent instance to deploy
            deployment_config: Deployment configuration
            logging_config: Logging and tracing configuration
        """
        # Use provided agent or fallback
        self.agent = agent or root_agent

        # Use provided configs or defaults
        self.deployment_config = deployment_config or DeploymentConfig(
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project")
        )
        self.logging_config = logging_config or LoggingConfig()

        # Validate configuration
        self.deployment_config.validate()

        # Initialize parent class
        super().__init__(
            agent=self.agent,
            description=self.deployment_config.description
        )

        # Setup components
        self._setup_logging()
        self._setup_tracing()
        self._setup_cloud_services()

        # Initialize metrics
        self.metrics = {
            "requests_processed": 0,
            "errors": 0,
            "total_feedback": 0,
            "average_score": 0.0
        }

        logger.info(f"🚀 AgentEngineApp initialized for project: {self.deployment_config.project}")

    def _setup_logging(self) -> None:
        """Configure logging based on configuration."""
        log_level = getattr(logging, self.logging_config.log_level.upper(), logging.INFO)
        logging.getLogger().setLevel(log_level)

        # Setup file logging if enabled
        if self.logging_config.log_to_file:
            file_handler = logging.FileHandler(self.logging_config.log_file_path)
            file_handler.setLevel(log_level)
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
            )
            file_handler.setFormatter(formatter)
            logging.getLogger().addHandler(file_handler)
            logger.info(f"📝 File logging enabled: {self.logging_config.log_file_path}")

        # Setup cloud logging if enabled
        if self.logging_config.enable_cloud_logging and CLOUD_LOGGING_AVAILABLE:
            try:
                self.cloud_logger_client = google_cloud_logging.Client(
                    project=self.logging_config.project_id
                )
                self.cloud_logger = self.cloud_logger_client.logger("architect-agent")
                logger.info("☁️ Cloud logging enabled")
            except Exception as e:
                logger.warning(f"⚠️ Could not enable cloud logging: {e}")
                self.cloud_logger = None
        else:
            self.cloud_logger = None

    def _setup_tracing(self) -> None:
        """Configure distributed tracing."""
        if self.logging_config.enable_tracing and TRACING_AVAILABLE:
            try:
                # Setup tracer provider
                tracer_provider = TracerProvider()

                # Add span processor
                if TRACING_UTILS_AVAILABLE:
                    span_processor = BatchSpanProcessor(
                        CloudTraceLoggingSpanExporter(self.logging_config.project_id)
                    )
                else:
                    span_processor = BatchSpanProcessor(NoOpSpanProcessor())

                tracer_provider.add_span_processor(span_processor)
                trace.set_tracer_provider(tracer_provider)

                logger.info("🔍 Tracing enabled")
            except Exception as e:
                logger.warning(f"⚠️ Could not enable tracing: {e}")

    def _setup_cloud_services(self) -> None:
        """Initialize cloud services."""
        # Setup artifact service
        if ARTIFACTS_SERVICE_AVAILABLE:
            try:
                self.artifact_service = GcsArtifactService(
                    bucket_name=self.deployment_config.artifacts_bucket_name
                )
                logger.info(f"📦 Artifact service initialized: {self.deployment_config.artifacts_bucket_name}")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize artifact service: {e}")
                self.artifact_service = None
        else:
            self.artifact_service = None

    def set_up(self) -> None:
        """
        Setup method called during deployment.

        This method is called once when the agent is deployed to Agent Engine.
        """
        logger.info("🔧 Setting up Agent Engine App...")

        try:
            # Initialize required services
            self._initialize_services()

            # Setup agent if needed
            if hasattr(self.agent, 'setup'):
                self.agent.setup()

            # Log configuration
            self._log_configuration()

            logger.info("✅ Agent Engine App setup complete")

        except Exception as e:
            logger.error(f"❌ Setup failed: {e}")
            logger.error(traceback.format_exc())
            raise

    def _initialize_services(self) -> None:
        """Initialize required cloud services."""
        try:
            # Initialize GCS bucket if needed
            if GCS_UTILS_AVAILABLE:
                bucket_name = self.deployment_config.artifacts_bucket_name
                create_bucket_if_not_exists(
                    bucket_name=bucket_name,
                    project=self.deployment_config.project,
                    location=self.deployment_config.location
                )
                logger.info(f"📦 Bucket ready: {bucket_name}")

            # Initialize Vertex AI if available
            if VERTEX_AI_AVAILABLE:
                vertexai.init(
                    project=self.deployment_config.project,
                    location=self.deployment_config.location
                )
                logger.info("🚀 Vertex AI initialized")

            logger.info("✅ Services initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize services: {e}")
            # Continue anyway - services might already exist

    def _log_configuration(self) -> None:
        """Log current configuration for debugging."""
        config_info = {
            "deployment": {
                "project": self.deployment_config.project,
                "location": self.deployment_config.location,
                "agent_name": self.deployment_config.agent_name,
                "timeout": self.deployment_config.timeout_seconds,
                "max_concurrent": self.deployment_config.max_concurrent_requests
            },
            "logging": {
                "level": self.logging_config.log_level,
                "cloud_logging": self.logging_config.enable_cloud_logging,
                "tracing": self.logging_config.enable_tracing
            },
            "agent": {
                "name": getattr(self.agent, 'name', 'unknown'),
                "version": getattr(self.agent, 'version', 'unknown')
            }
        }

        logger.info(f"📋 Configuration: {json.dumps(config_info, indent=2)}")

    def register_operations(self) -> Dict[str, List[str]]:
        """
        Register available operations for the agent.

        Returns:
            Dict mapping operation categories to operation names
        """
        operations = {
            "diagram_generation": [
                "generate_context_diagram",
                "generate_container_diagram",
                "generate_component_diagram",
                "auto_generate_diagram"
            ],
            "validation": [
                "validate_diagram",
                "check_compliance",
                "validate_archimate",
                "check_metamodel"
            ],
            "search": [
                "search_knowledge_base",
                "vertex_ai_search"
            ],
            "management": [
                "list_diagrams",
                "get_diagram",
                "delete_diagram",
                "update_diagram"
            ]
        }

        total_ops = sum(len(ops) for ops in operations.values())
        logger.info(f"📋 Registered {total_ops} operations across {len(operations)} categories")

        return operations

    async def stream_query(
            self,
            message: str,
            user_id: str,
            session_id: Optional[str] = None,
            context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Handle streaming queries to the agent.

        Args:
            message: User message
            user_id: User identifier
            session_id: Optional session identifier
            context: Optional additional context

        Returns:
            Streamed response from the agent
        """
        start_time = datetime.datetime.now()

        logger.info(f"💬 Processing query from user: {user_id}")
        logger.debug(f"Message: {message[:100]}...")

        try:
            # Update metrics
            self.metrics["requests_processed"] += 1

            # Log to cloud if available
            if self.cloud_logger:
                self.cloud_logger.log_struct({
                    "event": "query_received",
                    "user_id": user_id,
                    "session_id": session_id,
                    "message_length": len(message)
                })

            # Process through agent
            if hasattr(self.agent, 'stream_async'):
                response = await self.agent.stream_async(message)
            elif hasattr(self.agent, 'process'):
                response = self.agent.process(message)
            else:
                response = {"error": "Agent does not support processing"}

            # Calculate processing time
            processing_time = (datetime.datetime.now() - start_time).total_seconds()

            logger.info(f"✅ Query processed successfully in {processing_time:.2f}s")

            # Log success to cloud
            if self.cloud_logger:
                self.cloud_logger.log_struct({
                    "event": "query_processed",
                    "user_id": user_id,
                    "processing_time": processing_time,
                    "success": True
                })

            return response

        except Exception as e:
            # Update error metrics
            self.metrics["errors"] += 1

            logger.error(f"❌ Error processing query: {e}")
            logger.error(traceback.format_exc())

            # Log error to cloud
            if self.cloud_logger:
                self.cloud_logger.log_struct({
                    "event": "query_error",
                    "user_id": user_id,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }, severity="ERROR")

            return {
                "error": str(e),
                "message": "An error occurred while processing your request"
            }

    def handle_feedback(
            self,
            feedback_data: Union[Dict[str, Any], Feedback],
            user_id: str
    ) -> Dict[str, Any]:
        """
        Handle user feedback on agent responses.

        Args:
            feedback_data: Feedback information
            user_id: User identifier

        Returns:
            Dict with feedback processing result
        """
        logger.info(f"📝 Received feedback from user: {user_id}")

        try:
            # Convert to Feedback model if dict
            if isinstance(feedback_data, dict):
                normalised_data = dict(feedback_data)
                normalised_data["score"] = _normalize_feedback_score(
                    normalised_data.get("score")
                )
                feedback = Feedback.model_validate(normalised_data)
            else:
                # When receiving already parsed objects ensure score is valid
                feedback_data.score = _normalize_feedback_score(feedback_data.score)
                feedback = feedback_data

            # Update metrics
            self.metrics["total_feedback"] += 1

            # Calculate new average score
            current_avg = self.metrics["average_score"]
            total = self.metrics["total_feedback"]
            new_avg = ((current_avg * (total - 1)) + feedback.score) / total
            self.metrics["average_score"] = new_avg

            # Log feedback details
            logger.info(f"  Score: {feedback.score}/5")
            logger.info(f"  Comment: {feedback.text[:100]}...")
            logger.info(f"  New average score: {new_avg:.2f}")

            # Log to cloud if available
            if self.cloud_logger:
                self.cloud_logger.log_struct({
                    "event": "feedback_received",
                    "user_id": user_id,
                    "score": feedback.score,
                    "text": feedback.text,
                    "average_score": new_avg,
                    "total_feedback": total
                })

            # Process feedback if agent supports it
            if hasattr(self.agent, 'process_feedback'):
                result = self.agent.process_feedback(feedback.model_dump())
            else:
                result = {
                    "status": "received",
                    "message": "Thank you for your feedback"
                }

            result["metrics"] = {
                "average_score": new_avg,
                "total_feedback": total
            }

            return result

        except Exception as e:
            logger.error(f"❌ Error processing feedback: {e}")

            # Log error to cloud
            if self.cloud_logger:
                self.cloud_logger.log_struct({
                    "event": "feedback_error",
                    "user_id": user_id,
                    "error": str(e)
                }, severity="ERROR")

            return {
                "error": str(e),
                "status": "error",
                "message": "Could not process feedback"
            }

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current application metrics.

        Returns:
            Dict with current metrics
        """
        return copy.deepcopy(self.metrics)

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the application.

        Returns:
            Dict with health status
        """
        health = {
            "status": "healthy",
            "timestamp": datetime.datetime.now().isoformat(),
            "agent": {
                "available": self.agent is not None,
                "name": getattr(self.agent, 'name', 'unknown')
            },
            "services": {
                "cloud_logging": self.cloud_logger is not None,
                "artifacts": self.artifact_service is not None,
                "vertex_ai": VERTEX_AI_AVAILABLE
            },
            "metrics": self.get_metrics()
        }

        # Check if agent is responsive
        try:
            if hasattr(self.agent, 'process'):
                test_result = self.agent.process("health check")
                health["agent"]["responsive"] = True
        except Exception as e:
            health["agent"]["responsive"] = False
            health["agent"]["error"] = str(e)
            health["status"] = "degraded"

        return health


# ===== DEPLOYMENT FUNCTIONS =====

def create_app(
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        agent: Optional[Any] = None
) -> AgentEngineApp:
    """
    Factory function to create an AgentEngineApp instance.

    Args:
        project_id: Google Cloud project ID
        location: Deployment location
        agent: Optional agent instance to use

    Returns:
        Configured AgentEngineApp instance
    """
    # Create deployment config
    deployment_config = DeploymentConfig(
        project=project_id or os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project"),
        location=location or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    )

    # Add environment variables
    deployment_config.env_vars = {
        "GOOGLE_CLOUD_PROJECT": deployment_config.project,
        "GOOGLE_CLOUD_LOCATION": deployment_config.location,
        "PYTHONUNBUFFERED": "1"
    }

    # Create logging config
    logging_config = LoggingConfig(
        project_id=deployment_config.project,
        enable_cloud_logging=True,
        enable_tracing=True
    )

    # Create and return app
    return AgentEngineApp(
        agent=agent or root_agent,
        deployment_config=deployment_config,
        logging_config=logging_config
    )


async def main():
    """
    Main entry point for local testing (async).
    """
    logger.info("🚀 Starting Agent Engine App in local mode...")

    # Create app
    app = create_app()

    # Setup
    app.set_up()

    # Register operations
    operations = app.register_operations()
    logger.info(f"📋 Available operations: {list(operations.keys())}")

    # Test health check
    health = await app.health_check()
    logger.info(f"🏥 Health check: {health['status']}")

    # Test query
    test_message = "Generate a context diagram for a banking system with PIX integration"
    logger.info(f"🧪 Testing with message: {test_message}")

    response = await app.stream_query(
        message=test_message,
        user_id="test_user",
        session_id="test_session"
    )

    logger.info(f"✅ Response received: {type(response)}")

    # Test feedback
    feedback = Feedback(
        score=5,
        text="Great diagram!",
        invocation_id="test_invocation",
        user_id="test_user"
    )

    feedback_result = app.handle_feedback(feedback, "test_user")
    logger.info(f"📝 Feedback result: {feedback_result}")

    # Get final metrics
    metrics = app.get_metrics()
    logger.info(f"📊 Final metrics: {metrics}")

    logger.info("✅ Local test complete")


def sync_main():
    """
    Synchronous wrapper for main function.
    """
    asyncio.run(main())


# ===== EXPORTS =====

__all__ = [
    "AgentEngineApp",
    "DeploymentConfig",
    "LoggingConfig",
    "Feedback",
    "create_app",
    "root_agent",
    "main",
    "sync_main"
]

if __name__ == "__main__":
    sync_main()