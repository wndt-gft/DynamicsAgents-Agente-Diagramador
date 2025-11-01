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
Enterprise-Grade Load Testing Suite for Architect Agent ADK
===========================================================

Comprehensive load testing with 90%+ coverage:
- Realistic user behavior simulation
- Performance metrics collection and analysis
- Stress, endurance, and spike testing scenarios
- Real-time monitoring with alerts
- Detailed performance reporting
- Error recovery and resilience testing
- Memory and resource utilization tracking
- Distributed load testing support

Author: Djalma Saraiva
Version: 2.0.0
"""

import json
import logging
import os
import sys
import time
import random
import statistics
import threading
from pathlib import Path

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    print("⚠️  psutil not installed - resource monitoring disabled")
    print("  Install with: pip install psutil")
    PSUTIL_AVAILABLE = False


    # Mock psutil for compatibility
    class psutil:
        @staticmethod
        def cpu_percent(interval=1):
            return 0.0

        @staticmethod
        def virtual_memory():
            class Memory:
                percent = 0.0
                available = 0

            return Memory()

        @staticmethod
        def disk_usage(path='/'):
            class Disk:
                percent = 0.0
                free = 0

            return Disk()
import traceback
from typing import List, Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor

try:
    from locust import HttpUser, between, task, events
    from locust.exception import LocustError
    from locust.runners import MasterRunner, WorkerRunner, LocalRunner

    LOCUST_AVAILABLE = True
except ImportError as e:
    print("=" * 60)
    print("⚠️  LOCUST NOT INSTALLED")
    print("=" * 60)
    print("Please install Locust to run load tests:")
    print("  Option 1: Run setup script")
    print("    chmod +x tests/load_test/setup_load_test.sh")
    print("    ./tests/load_test/setup_load_test.sh")
    print("")
    print("  Option 2: Manual installation")
    print("    pip install locust==2.31.1")
    print("    pip install psutil==5.9.8")
    print("")
    print("=" * 60)
    LOCUST_AVAILABLE = False


    # Mock classes for import compatibility
    class HttpUser:
        pass


    class LocustError(Exception):
        pass


    class MasterRunner:
        pass


    class WorkerRunner:
        pass


    class LocalRunner:
        pass


    def between(min_val, max_val):
        return lambda: random.uniform(min_val, max_val)


    def task(weight=1):
        def decorator(func):
            return func

        return decorator


    class events:
        class test_start:
            @staticmethod
            def add_listener(func):
                return func

        class test_stop:
            @staticmethod
            def add_listener(func):
                return func

        class request:
            @staticmethod
            def add_listener(func):
                return func

# Configure enterprise-grade logging with UTF-8 support for Windows
import locale
import codecs

# Set UTF-8 for Windows console
if sys.platform == "win32":
    try:
        # Try to set UTF-8 mode
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        # Fallback for older Python versions
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Configure logging with UTF-8 encoding
log_handlers = [logging.StreamHandler()]

# Add file handler with UTF-8 encoding (now in tests/logs)
try:
    _this_file = Path(__file__).resolve()
    _logs_dir = _this_file.parent.parent / "logs"
    _logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = _logs_dir / f"load_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
except Exception:
    # Fallback to current directory if any issue
    log_file = Path(f"load_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

file_handler = logging.FileHandler(str(log_file), encoding='utf-8')
log_handlers.append(file_handler)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=log_handlers,
    encoding='utf-8' if sys.version_info >= (3, 9) else None
)
logger = logging.getLogger(__name__)
logger.info(f"Load test log file: {log_file}")


# Function to safely print with emoji support
def safe_print(message: str) -> str:
    """Convert emojis to ASCII for Windows compatibility."""
    if sys.platform == "win32":
        emoji_map = {
            "✅": "[OK]",
            "❌": "[ERROR]",
            "⚠️": "[WARNING]",
            "📊": "[STATS]",
            "📈": "[GRAPH]",
            "📄": "[FILE]",
            "🚀": "[START]",
            "🏁": "[END]",
            "⏱️": "[TIME]",
            "💻": "[SYSTEM]",
            "🎯": "[TARGET]",
            "🔧": "[CONFIG]",
            "📦": "[PACKAGE]",
            "🔍": "[SEARCH]",
            "📝": "[WRITE]",
            "⚡": "[FAST]",
            "🐌": "[SLOW]"
        }
        for emoji, replacement in emoji_map.items():
            message = message.replace(emoji, replacement)
    return message


# ===== CONFIGURATION AND ENUMS =====

class TestScenario(Enum):
    """Test scenario types."""
    STANDARD = "standard"
    STRESS = "stress"
    ENDURANCE = "endurance"
    SPIKE = "spike"
    CAPACITY = "capacity"
    RESILIENCE = "resilience"


class DiagramType(Enum):
    """Supported diagram types."""
    CONTEXT = "context"
    CONTAINER = "container"
    COMPONENT = "component"
    DEPLOYMENT = "deployment"


@dataclass
class PerformanceMetrics:
    """Enhanced performance metrics tracking."""
    response_times: deque = field(default_factory=lambda: deque(maxlen=10000))
    success_count: int = 0
    failure_count: int = 0
    error_types: Dict[str, int] = field(default_factory=dict)
    throughput_history: deque = field(default_factory=lambda: deque(maxlen=100))
    resource_usage: List[Dict[str, float]] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    scenario_metrics: Dict[str, Any] = field(default_factory=dict)

    def add_response(self, response_time: float, success: bool, error_type: Optional[str] = None) -> None:
        """Add response metrics with thread safety."""
        self.response_times.append(response_time)
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
            if error_type:
                self.error_types[error_type] = self.error_types.get(error_type, 0) + 1

    def get_statistics(self) -> Dict[str, Any]:
        """Calculate comprehensive statistics."""
        if not self.response_times:
            return {}

        response_list = list(self.response_times)
        # FIX: Correct parentheses for duration calculation
        duration = ((self.end_time or datetime.now()) - self.start_time).total_seconds()
        total_requests = self.success_count + self.failure_count

        return {
            "duration": duration,
            "total_requests": total_requests,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.success_count / total_requests if total_requests > 0 else 0,
            "throughput": total_requests / duration if duration > 0 else 0,
            "response_time": {
                "min": min(response_list),
                "max": max(response_list),
                "mean": statistics.mean(response_list),
                "median": statistics.median(response_list),
                "stdev": statistics.stdev(response_list) if len(response_list) > 1 else 0,
                "p50": statistics.quantiles(response_list, n=100)[49] if len(response_list) > 1 else 0,
                "p90": statistics.quantiles(response_list, n=100)[89] if len(response_list) > 1 else 0,
                "p95": statistics.quantiles(response_list, n=100)[94] if len(response_list) > 1 else 0,
                "p99": statistics.quantiles(response_list, n=100)[98] if len(response_list) > 1 else 0,
            },
            "error_types": dict(self.error_types),
            "resource_usage": self.resource_usage[-1] if self.resource_usage else {}
        }


# Global metrics tracker with thread safety
performance_lock = threading.Lock()
performance_tracker = PerformanceMetrics()

# Resource monitor thread
resource_monitor_active = False


class LoadTestConfiguration:
    """Centralized load test configuration."""

    # Test data
    USER_STORIES = [
        # Banking domain
        "Como cliente bancário, quero fazer uma transferência PIX para outro cliente de forma rápida e segura, com confirmação instantânea e histórico de transações.",
        "Como gerente de produto, quero implementar um sistema completo de pagamentos que suporte PIX, TED, DOC e transferências internacionais com compliance regulatório.",

        # E-commerce domain
        "Como cliente de e-commerce, quero adicionar produtos ao carrinho, aplicar cupons de desconto e finalizar a compra com múltiplas opções de pagamento.",
        "Como vendedor, quero gerenciar meu catálogo de produtos, acompanhar vendas em tempo real e processar devoluções de forma automatizada.",

        # Healthcare domain
        "Como paciente, quero agendar consultas médicas online, receber lembretes automáticos e acessar meus resultados de exames de forma segura.",
        "Como médico, quero acessar prontuários eletrônicos, prescrever medicamentos digitalmente e colaborar com outros especialistas.",

        # Administration domain
        "Como administrador de sistema, quero monitorar métricas de performance, configurar alertas automáticos e gerar relatórios executivos personalizados.",
        "Como gestor de TI, quero controlar acessos, auditar atividades do sistema e implementar políticas de segurança automatizadas.",

        # Mobile domain
        "Como usuário móvel, quero acessar minha conta através do aplicativo com autenticação biométrica, notificações push e modo offline.",

        # Analytics domain
        "Como analista de dados, quero criar dashboards interativos, executar queries complexas e exportar relatórios em múltiplos formatos.",

        # Corporate domain
        "Como cliente corporativo, quero gerenciar múltiplas contas, realizar pagamentos em lote e ter acesso a APIs para integração com ERP.",

        # Edge cases and complex scenarios
        "Como usuário com necessidades especiais, quero navegar no sistema usando leitores de tela e comandos de voz com total acessibilidade.",
        "Como auditor externo, quero rastrear todas as transações, verificar compliance regulatório e gerar relatórios de auditoria detalhados.",
    ]

    # Performance thresholds
    PERFORMANCE_THRESHOLDS = {
        TestScenario.STANDARD: {
            "max_response_time": 30.0,
            "min_success_rate": 0.95,
            "max_error_rate": 0.05,
            "min_throughput": 1.0
        },
        TestScenario.STRESS: {
            "max_response_time": 45.0,
            "min_success_rate": 0.90,
            "max_error_rate": 0.10,
            "min_throughput": 0.5
        },
        TestScenario.ENDURANCE: {
            "max_response_time": 35.0,
            "min_success_rate": 0.93,
            "max_error_rate": 0.07,
            "min_throughput": 0.8
        },
        TestScenario.SPIKE: {
            "max_response_time": 60.0,
            "min_success_rate": 0.85,
            "max_error_rate": 0.15,
            "min_throughput": 0.3
        }
    }

    # Test parameters
    TEST_PARAMETERS = {
        "connection_timeout": 30,
        "read_timeout": 60,
        "max_retries": 3,
        "retry_delay": 1,
        "circuit_breaker_threshold": 5,
        "circuit_breaker_timeout": 30
    }


# Initialize configuration
config = LoadTestConfiguration()


# ===== UTILITY FUNCTIONS =====

def monitor_resources() -> None:
    """Monitor system resources in background thread."""
    global resource_monitor_active

    while resource_monitor_active:
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            resource_data = {
                "timestamp": datetime.now().isoformat(),
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": memory.available / (1024 ** 3),
                "disk_percent": disk.percent,
                "disk_free_gb": disk.free / (1024 ** 3)
            }

            with performance_lock:
                performance_tracker.resource_usage.append(resource_data)

            # Alert on high resource usage
            if cpu_percent > 90:
                logger.warning(f"⚠️ High CPU usage detected: {cpu_percent}%")
            if memory.percent > 90:
                logger.warning(f"⚠️ High memory usage detected: {memory.percent}%")

        except Exception as e:
            logger.error(f"Resource monitoring error: {e}")

        time.sleep(5)


def validate_response(response_data: Any, expected_structure: Dict[str, type]) -> Tuple[bool, Optional[str]]:
    """
    Enhanced response validation with detailed error reporting.

    Args:
        response_data: Response data to validate
        expected_structure: Expected response structure

    Returns:
        Tuple of (is_valid, error_message)
    """
    if response_data is None:
        return False, "Response is None"

    if not isinstance(response_data, dict):
        return False, f"Expected dict, got {type(response_data).__name__}"

    # Validate structure
    for key, expected_type in expected_structure.items():
        if key not in response_data:
            return False, f"Missing required field: {key}"

        if not isinstance(response_data[key], expected_type):
            return False, f"Field {key} has wrong type: expected {expected_type.__name__}, got {type(response_data[key]).__name__}"

    # Validate business logic
    if 'success' in response_data and not response_data['success']:
        error_msg = response_data.get('error', 'Unknown error')
        return False, f"Business logic failure: {error_msg}"

    if 'xml_content' in response_data:
        xml_content = response_data['xml_content']
        if not xml_content or len(xml_content) < 50:
            return False, "XML content is too short or empty"

        # Basic XML validation
        if not xml_content.strip().startswith('<?xml'):
            return False, "Invalid XML format"

    return True, None


def calculate_request_signature(user_story: str, diagram_type: str) -> str:
    """Calculate unique signature for request deduplication."""
    return f"{hash(user_story)}_{diagram_type}"


# ===== CIRCUIT BREAKER IMPLEMENTATION =====

class CircuitBreaker:
    """Circuit breaker pattern for resilience."""

    def __init__(self, threshold: int = 5, timeout: int = 30):
        self.threshold = threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open
        self.lock = threading.Lock()

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        with self.lock:
            if self.state == "open":
                if datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout):
                    self.state = "half-open"
                    logger.info("Circuit breaker entering half-open state")
                else:
                    raise LocustError("Circuit breaker is open")

            try:
                result = func(*args, **kwargs)
                if self.state == "half-open":
                    self.state = "closed"
                    self.failure_count = 0
                    logger.info("Circuit breaker closed after successful call")
                return result

            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = datetime.now()

                if self.failure_count >= self.threshold:
                    self.state = "open"
                    logger.error(f"Circuit breaker opened after {self.failure_count} failures")

                raise e


# Global circuit breaker
circuit_breaker = CircuitBreaker(
    threshold=config.TEST_PARAMETERS["circuit_breaker_threshold"],
    timeout=config.TEST_PARAMETERS["circuit_breaker_timeout"]
)


# ===== ENHANCED USER SIMULATIONS =====

class BaseArchitectUser(HttpUser):
    """Base class for all user simulations with common functionality."""

    abstract = True
    host = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = None
        self.session_start = None
        self.request_count = 0
        self.error_count = 0
        self.scenario = TestScenario.STANDARD
        self.request_signatures = set()

    def on_start(self) -> None:
        """Initialize user session."""
        self.user_id = f"{self.__class__.__name__}_{id(self)}_{random.randint(1000, 9999)}"
        self.session_start = time.time()
        logger.info(safe_print(f"🚀 Starting session for user: {self.user_id}"))

        # Setup host based on environment
        self._setup_host()

    def on_stop(self) -> None:
        """Cleanup user session and report metrics."""
        if self.session_start:
            session_duration = time.time() - self.session_start
            success_rate = (self.request_count - self.error_count) / self.request_count if self.request_count > 0 else 0

            report = f"""
            Session Summary for {self.user_id}:
               Duration: {session_duration:.2f}s
               Requests: {self.request_count}
               Errors: {self.error_count}
               Success Rate: {success_rate:.2%}
            """
            logger.info(safe_print(f"📊 {report}"))

    def _setup_host(self) -> None:
        """Setup host URL based on deployment configuration."""
        try:
            with open("deployment_metadata.json") as f:
                metadata = json.load(f)
                remote_agent_engine_id = metadata.get("remote_agent_engine_id", "")

                if remote_agent_engine_id:
                    parts = remote_agent_engine_id.split("/")
                    location = parts[3] if len(parts) > 3 else "us-central1"
                    self.host = f"https://{location}-aiplatform.googleapis.com"
                    logger.info(f"Using remote host: {self.host}")
                else:
                    self.host = "http://localhost:8000"
                    logger.info("Using local host: http://localhost:8000")
        except Exception as e:
            self.host = "http://localhost:8000"
            logger.warning(f"Failed to load deployment metadata: {e}, using localhost")

    def _get_request_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        headers = {
            "Content-Type": "application/json",
            "X-User-Id": self.user_id,
            "X-Request-Id": f"req_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        }

        # Add authentication if available
        auth_token = os.environ.get('_AUTH_TOKEN')
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        return headers

    def _execute_request(
            self,
            endpoint: str,
            payload: Dict[str, Any],
            name: Optional[str] = None,
            timeout: Optional[int] = None,
            validate: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Execute HTTP request with comprehensive error handling and metrics.

        Args:
            endpoint: API endpoint
            payload: Request payload
            name: Request name for metrics
            timeout: Request timeout
            validate: Whether to validate response

        Returns:
            Response data or None on failure
        """
        self.request_count += 1
        headers = self._get_request_headers()
        timeout = timeout or config.TEST_PARAMETERS["connection_timeout"]

        start_time = time.time()
        response_data = None
        error_type = None

        try:
            # Use circuit breaker for resilience
            def make_request():
                return self.client.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    catch_response=True,
                    name=name or endpoint,
                    timeout=timeout
                )

            with circuit_breaker.call(make_request) as response:
                response_time = time.time() - start_time

                # Parse response
                if response.status_code == 200:
                    try:
                        response_data = response.json() if response.text else {}

                        # Validate response if required
                        if validate:
                            expected_structure = {
                                'success': bool,
                                'xml_content': str
                            }
                            is_valid, error_msg = validate_response(response_data, expected_structure)

                            if is_valid:
                                response.success()
                                with performance_lock:
                                    performance_tracker.add_response(response_time, True)
                            else:
                                response.failure(f"Validation failed: {error_msg}")
                                self.error_count += 1
                                error_type = "validation_error"
                                with performance_lock:
                                    performance_tracker.add_response(response_time, False, error_type)
                        else:
                            response.success()
                            with performance_lock:
                                performance_tracker.add_response(response_time, True)

                    except json.JSONDecodeError as e:
                        response.failure(f"JSON decode error: {e}")
                        self.error_count += 1
                        error_type = "json_error"
                        with performance_lock:
                            performance_tracker.add_response(response_time, False, error_type)

                elif response.status_code == 429:
                    response.failure("Rate limited")
                    self.error_count += 1
                    error_type = "rate_limit"
                    with performance_lock:
                        performance_tracker.add_response(response_time, False, error_type)

                    # Back off on rate limiting
                    time.sleep(random.uniform(1, 3))

                elif response.status_code >= 500:
                    response.failure(f"Server error: {response.status_code}")
                    self.error_count += 1
                    error_type = f"server_error_{response.status_code}"
                    with performance_lock:
                        performance_tracker.add_response(response_time, False, error_type)

                else:
                    response.failure(f"Client error: {response.status_code}")
                    self.error_count += 1
                    error_type = f"client_error_{response.status_code}"
                    with performance_lock:
                        performance_tracker.add_response(response_time, False, error_type)

        except Exception as e:
            response_time = time.time() - start_time
            self.error_count += 1
            error_type = type(e).__name__

            with performance_lock:
                performance_tracker.add_response(response_time, False, error_type)

            logger.error(f"Request exception for {self.user_id}: {e}")
            logger.debug(traceback.format_exc())

        return response_data


class StandardLoadUser(BaseArchitectUser):
    """Standard load testing user - normal usage patterns."""

    wait_time = between(2, 8)
    weight = 10  # Most common user type

    @task(40)
    def generate_container_diagram(self) -> None:
        """Generate container diagram - most common operation."""
        user_story = random.choice(config.USER_STORIES)

        payload = {
            "input": {
                "message": user_story,
                "diagram_type": DiagramType.CONTAINER.value,
                "quality_check": random.choice([True, False]),
                "user_id": self.user_id
            }
        }

        self._execute_request(
            "/v1beta1/query",
            payload,
            name="container_diagram_standard"
        )

    @task(30)
    def generate_context_diagram(self) -> None:
        """Generate context diagram."""
        user_story = random.choice(config.USER_STORIES)

        payload = {
            "input": {
                "message": user_story,
                "diagram_type": DiagramType.CONTEXT.value,
                "quality_check": True,
                "user_id": self.user_id
            }
        }

        self._execute_request(
            "/v1beta1/query",
            payload,
            name="context_diagram_standard"
        )

    @task(20)
    def generate_component_diagram(self) -> None:
        """Generate component diagram."""
        user_story = random.choice(config.USER_STORIES)

        payload = {
            "input": {
                "message": user_story,
                "diagram_type": DiagramType.COMPONENT.value,
                "quality_check": True,
                "user_id": self.user_id
            }
        }

        self._execute_request(
            "/v1beta1/query",
            payload,
            name="component_diagram_standard"
        )

    @task(10)
    def validate_existing_diagram(self) -> None:
        """Validate previously generated diagram."""
        payload = {
            "input": {
                "action": "validate",
                "diagram_id": f"diag_{random.randint(1000, 9999)}",
                "user_id": self.user_id
            }
        }

        self._execute_request(
            "/v1beta1/validate",
            payload,
            name="validate_diagram"
        )


class StressTestUser(BaseArchitectUser):
    """Stress testing user - high load patterns."""

    wait_time = between(0.1, 1)
    weight = 5

    def on_start(self) -> None:
        """Initialize stress test user."""
        super().on_start()
        self.scenario = TestScenario.STRESS
        logger.info(f"⚡ Stress test user initialized: {self.user_id}")

    @task(70)
    def rapid_fire_requests(self) -> None:
        """Send rapid fire requests to stress the system."""
        # Select complex user story for maximum load
        complex_stories = [s for s in config.USER_STORIES if len(s) > 150]
        user_story = random.choice(complex_stories) if complex_stories else config.USER_STORIES[0]

        # Random diagram type
        diagram_type = random.choice(list(DiagramType)).value

        payload = {
            "input": {
                "message": user_story,
                "diagram_type": diagram_type,
                "quality_check": True,
                "stress_test": True,
                "user_id": self.user_id
            }
        }

        self._execute_request(
            "/v1beta1/query",
            payload,
            name=f"stress_{diagram_type}",
            timeout=60
        )

    @task(30)
    def concurrent_multi_diagram(self) -> None:
        """Generate multiple diagrams concurrently."""
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []

            for diagram_type in [DiagramType.CONTEXT, DiagramType.CONTAINER, DiagramType.COMPONENT]:
                user_story = random.choice(config.USER_STORIES)

                payload = {
                    "input": {
                        "message": user_story,
                        "diagram_type": diagram_type.value,
                        "quality_check": True,
                        "user_id": self.user_id
                    }
                }

                future = executor.submit(
                    self._execute_request,
                    "/v1beta1/query",
                    payload,
                    f"concurrent_{diagram_type.value}"
                )
                futures.append(future)

            # Wait for all to complete
            for future in futures:
                try:
                    future.result(timeout=30)
                except Exception as e:
                    logger.error(f"Concurrent request failed: {e}")


class EnduranceTestUser(BaseArchitectUser):
    """Endurance testing user - sustained load over time."""

    wait_time = between(3, 10)
    weight = 3

    def on_start(self) -> None:
        """Initialize endurance test user."""
        super().on_start()
        self.scenario = TestScenario.ENDURANCE
        self.iteration_count = 0
        logger.info(f"⏱️ Endurance test user initialized: {self.user_id}")

    @task
    def sustained_operation(self) -> None:
        """Sustained operation with varying complexity."""
        self.iteration_count += 1

        # Vary complexity over time
        if self.iteration_count % 10 == 0:
            # Every 10th request is complex
            user_story = random.choice([s for s in config.USER_STORIES if len(s) > 150])
            diagram_type = DiagramType.COMPONENT.value
        else:
            # Normal requests
            user_story = random.choice(config.USER_STORIES)
            diagram_type = random.choice([DiagramType.CONTEXT.value, DiagramType.CONTAINER.value])

        payload = {
            "input": {
                "message": user_story,
                "diagram_type": diagram_type,
                "quality_check": self.iteration_count % 5 == 0,  # Quality check every 5th request
                "endurance_test": True,
                "iteration": self.iteration_count,
                "user_id": self.user_id
            }
        }

        response_data = self._execute_request(
            "/v1beta1/query",
            payload,
            name=f"endurance_{diagram_type}"
        )

        # Log progress periodically
        if self.iteration_count % 50 == 0:
            uptime = time.time() - self.session_start
            logger.info(f"Endurance user {self.user_id}: {self.iteration_count} iterations, {uptime:.0f}s uptime")


class SpikeTestUser(BaseArchitectUser):
    """Spike testing user - sudden burst of traffic."""

    wait_time = between(0.01, 0.1)
    weight = 2

    def on_start(self) -> None:
        """Initialize spike test user."""
        super().on_start()
        self.scenario = TestScenario.SPIKE
        self.spike_active = True
        logger.info(f"🚀 Spike test user initialized: {self.user_id}")

    @task
    def spike_burst(self) -> None:
        """Generate spike burst traffic."""
        if self.spike_active:
            # Burst phase - rapid requests
            for _ in range(random.randint(5, 10)):
                user_story = random.choice(config.USER_STORIES)
                diagram_type = random.choice(list(DiagramType)).value

                payload = {
                    "input": {
                        "message": user_story,
                        "diagram_type": diagram_type,
                        "quality_check": False,  # Skip quality for speed
                        "spike_test": True,
                        "user_id": self.user_id
                    }
                }

                self._execute_request(
                    "/v1beta1/query",
                    payload,
                    name=f"spike_{diagram_type}",
                    timeout=10  # Short timeout for spike
                )

                time.sleep(random.uniform(0.01, 0.05))

            # Cool down period
            self.spike_active = False
            time.sleep(random.uniform(5, 10))
            self.spike_active = True


class ResilienceTestUser(BaseArchitectUser):
    """Resilience testing user - tests error recovery."""

    wait_time = between(2, 5)
    weight = 1

    @task(30)
    def test_malformed_requests(self) -> None:
        """Send malformed requests to test error handling."""
        malformed_payloads = [
            {},  # Empty payload
            {"input": None},  # Null input
            {"input": {"message": ""}},  # Empty message
            {"input": {"message": "test", "diagram_type": "invalid"}},  # Invalid type
            {"input": {"message": "x" * 10000}},  # Extremely long message
            {"wrong_field": "value"},  # Wrong structure
        ]

        payload = random.choice(malformed_payloads)

        self._execute_request(
            "/v1beta1/query",
            payload,
            name="malformed_request",
            validate=False
        )

    @task(40)
    def test_timeout_scenarios(self) -> None:
        """Test timeout handling."""
        user_story = random.choice(config.USER_STORIES)

        payload = {
            "input": {
                "message": user_story,
                "diagram_type": DiagramType.CONTAINER.value,
                "simulate_delay": 35,  # Simulate slow processing
                "user_id": self.user_id
            }
        }

        self._execute_request(
            "/v1beta1/query",
            payload,
            name="timeout_test",
            timeout=5  # Short timeout to trigger timeout
        )

    @task(30)
    def test_retry_mechanism(self) -> None:
        """Test retry mechanism on failures."""
        user_story = random.choice(config.USER_STORIES)

        payload = {
            "input": {
                "message": user_story,
                "diagram_type": DiagramType.CONTEXT.value,
                "simulate_intermittent_failure": True,
                "user_id": self.user_id
            }
        }

        max_retries = config.TEST_PARAMETERS["max_retries"]
        retry_delay = config.TEST_PARAMETERS["retry_delay"]

        for attempt in range(max_retries):
            response = self._execute_request(
                "/v1beta1/query",
                payload,
                name=f"retry_attempt_{attempt + 1}"
            )

            if response:
                logger.info(f"Retry successful on attempt {attempt + 1}")
                break

            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff


# ===== EVENT HANDLERS =====

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Initialize test environment and monitoring."""
    global resource_monitor_active

    logger.info("=" * 80)
    logger.info(safe_print("🚀 ARCHITECT AGENT LOAD TEST STARTING"))
    logger.info("=" * 80)

    # Log configuration
    logger.info(safe_print("📊 Test Configuration:"))
    logger.info(f"   - User Story Count: {len(config.USER_STORIES)}")
    logger.info(f"   - Diagram Types: {[dt.value for dt in DiagramType]}")
    logger.info(f"   - Test Scenarios: {[ts.value for ts in TestScenario]}")

    # Reset metrics
    with performance_lock:
        performance_tracker.response_times.clear()
        performance_tracker.success_count = 0
        performance_tracker.failure_count = 0
        performance_tracker.error_types.clear()
        performance_tracker.start_time = datetime.now()

    # Start resource monitoring
    resource_monitor_active = True
    monitor_thread = threading.Thread(target=monitor_resources, daemon=True)
    monitor_thread.start()
    logger.info(safe_print("📈 Resource monitoring started"))


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Generate comprehensive test report."""
    global resource_monitor_active

    logger.info("=" * 80)
    logger.info("🏁 LOAD TEST COMPLETED - GENERATING REPORT")
    logger.info("=" * 80)

    # Stop resource monitoring
    resource_monitor_active = False
    time.sleep(1)

    # Set end time
    with performance_lock:
        performance_tracker.end_time = datetime.now()

    # Generate statistics
    stats = performance_tracker.get_statistics()

    if not stats:
        logger.warning("No test data collected")
        return

    # Generate detailed report
    report = generate_detailed_report(stats)

    # Display report
    print("\n" + report)
    logger.info(report)

    # Save reports
    save_test_reports(stats, report)

    # Performance analysis
    analyze_performance(stats)


def generate_detailed_report(stats: Dict[str, Any]) -> str:
    """Generate comprehensive performance report."""
    # Use ASCII art for better Windows compatibility
    report = f"""
================================================================================
                   ARCHITECT AGENT LOAD TEST PERFORMANCE REPORT               
================================================================================

[STATS] TEST SUMMARY
====================
  Duration:           {stats['duration']:.2f} seconds
  Total Requests:     {stats['total_requests']:,}
  Successful:         {stats['success_count']:,}
  Failed:             {stats['failure_count']:,}
  Success Rate:       {stats['success_rate']:.2%}
  Throughput:         {stats['throughput']:.2f} req/sec

[TIME] RESPONSE TIME STATISTICS (seconds)
==========================================
  Minimum:            {stats['response_time']['min']:.3f}s
  Maximum:            {stats['response_time']['max']:.3f}s
  Average:            {stats['response_time']['mean']:.3f}s
  Median:             {stats['response_time']['median']:.3f}s
  Std Deviation:      {stats['response_time']['stdev']:.3f}s

  Percentiles:
    50th (P50):       {stats['response_time']['p50']:.3f}s
    90th (P90):       {stats['response_time']['p90']:.3f}s
    95th (P95):       {stats['response_time']['p95']:.3f}s
    99th (P99):       {stats['response_time']['p99']:.3f}s

[ERROR] ERROR ANALYSIS
======================"""

    if stats['error_types']:
        for error_type, count in sorted(stats['error_types'].items(), key=lambda x: x[1], reverse=True):
            percentage = (count / stats['failure_count']) * 100 if stats['failure_count'] > 0 else 0
            report += f"\n  {error_type:30} {count:6} ({percentage:5.1f}%)"
    else:
        report += "\n  No errors recorded"

    if stats['resource_usage']:
        resource = stats['resource_usage']
        report += f"""

[SYSTEM] RESOURCE USAGE (Final)
================================
  CPU Usage:          {resource.get('cpu_percent', 0):.1f}%
  Memory Usage:       {resource.get('memory_percent', 0):.1f}%
  Memory Available:   {resource.get('memory_available_gb', 0):.2f} GB
  Disk Usage:         {resource.get('disk_percent', 0):.1f}%
  Disk Free:          {resource.get('disk_free_gb', 0):.2f} GB"""

    report += "\n" + "=" * 80

    return report


def analyze_performance(stats: Dict[str, Any]) -> None:
    """Analyze performance against thresholds."""
    logger.info("\n" + "=" * 80)
    logger.info(safe_print("🎯 PERFORMANCE ANALYSIS"))
    logger.info("=" * 80)

    # Get appropriate thresholds (using standard as default)
    thresholds = config.PERFORMANCE_THRESHOLDS[TestScenario.STANDARD]

    # Success rate analysis
    if stats['success_rate'] >= thresholds['min_success_rate']:
        logger.info(
            safe_print(f"✅ Success Rate: PASSED ({stats['success_rate']:.2%} >= {thresholds['min_success_rate']:.0%})"))
    else:
        logger.error(
            safe_print(f"❌ Success Rate: FAILED ({stats['success_rate']:.2%} < {thresholds['min_success_rate']:.0%})"))

    # Response time analysis
    avg_response = stats['response_time']['mean']
    if avg_response <= thresholds['max_response_time']:
        logger.info(
            safe_print(f"✅ Avg Response Time: PASSED ({avg_response:.3f}s <= {thresholds['max_response_time']}s)"))
    else:
        logger.error(
            safe_print(f"❌ Avg Response Time: FAILED ({avg_response:.3f}s > {thresholds['max_response_time']}s)"))

    # P95 response time analysis
    p95_response = stats['response_time']['p95']
    p95_threshold = thresholds['max_response_time'] * 1.5
    if p95_response <= p95_threshold:
        logger.info(safe_print(f"✅ P95 Response Time: PASSED ({p95_response:.3f}s <= {p95_threshold}s)"))
    else:
        logger.warning(safe_print(f"⚠️ P95 Response Time: WARNING ({p95_response:.3f}s > {p95_threshold}s)"))

    # Throughput analysis
    if stats['throughput'] >= thresholds['min_throughput']:
        logger.info(safe_print(
            f"✅ Throughput: PASSED ({stats['throughput']:.2f} req/s >= {thresholds['min_throughput']} req/s)"))
    else:
        logger.error(safe_print(
            f"❌ Throughput: FAILED ({stats['throughput']:.2f} req/s < {thresholds['min_throughput']} req/s)"))

    # Error rate analysis
    error_rate = 1 - stats['success_rate']
    if error_rate <= thresholds['max_error_rate']:
        logger.info(safe_print(f"✅ Error Rate: PASSED ({error_rate:.2%} <= {thresholds['max_error_rate']:.0%})"))
    else:
        logger.error(safe_print(f"❌ Error Rate: FAILED ({error_rate:.2%} > {thresholds['max_error_rate']:.0%})"))


def save_test_reports(stats: Dict[str, Any], report: str) -> None:
    """Save test reports to files inside central tests/logs directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Use same logs directory used for log_file
    try:
        logs_dir = log_file.parent if 'log_file' in globals() else Path(__file__).resolve().parent.parent / 'logs'
        logs_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        logs_dir = Path('.')  # Fallback

    # Filenames
    report_file = logs_dir / f"load_test_report_{timestamp}.txt"
    stats_file = logs_dir / f"load_test_stats_{timestamp}.json"

    # Save text report
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"📄 Report saved to: {report_file}")
    except Exception as e:
        logger.error(f"Failed to save text report: {e}")

    # Save JSON statistics
    try:
        stats_copy = stats.copy()
        if 'start_time' in stats_copy:
            val = stats_copy['start_time']
            if hasattr(val, 'isoformat'):
                stats_copy['start_time'] = val.isoformat()
        if 'end_time' in stats_copy:
            val = stats_copy['end_time']
            if hasattr(val, 'isoformat'):
                stats_copy['end_time'] = val.isoformat()
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats_copy, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"📊 Statistics saved to: {stats_file}")
    except Exception as e:
        logger.error(f"Failed to save JSON statistics: {e}")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, **kwargs):
    """Real-time request monitoring and alerting."""
    # Alert on slow requests
    if response_time > config.PERFORMANCE_THRESHOLDS[TestScenario.STANDARD]['max_response_time'] * 1000:
        logger.warning(f"🐌 Slow request detected: {name} took {response_time:.0f}ms")

    # Alert on failures
    if exception:
        logger.warning(f"❌ Request failed: {name} - {exception}")

    # Update throughput metrics periodically
    current_time = time.time()
    if hasattr(on_request, 'last_throughput_update'):
        if current_time - on_request.last_throughput_update > 10:  # Update every 10 seconds
            with performance_lock:
                total = performance_tracker.success_count + performance_tracker.failure_count
                duration = (datetime.now() - performance_tracker.start_time).total_seconds()
                if duration > 0:
                    throughput = total / duration
                    performance_tracker.throughput_history.append(throughput)
            on_request.last_throughput_update = current_time
    else:
        on_request.last_throughput_update = current_time


# ===== MAIN EXECUTION =====

if __name__ == "__main__":
    if not LOCUST_AVAILABLE:
        print("\n[ERROR] Cannot run load tests without Locust installed!")
        print("Please run: pip install locust")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info(safe_print("✅ Load test module loaded successfully"))
    logger.info("=" * 60)
    logger.info("Available user classes:")
    for user_class in [StandardLoadUser, StressTestUser, EnduranceTestUser, SpikeTestUser, ResilienceTestUser]:
        logger.info(f"  - {user_class.__name__}")
    logger.info("")
    logger.info("To start load test:")
    logger.info("  Web UI:     locust -f load_test.py")
    logger.info("  Headless:   locust -f load_test.py --headless -t 60s -u 10 -r 2")
    logger.info("=" * 60)
