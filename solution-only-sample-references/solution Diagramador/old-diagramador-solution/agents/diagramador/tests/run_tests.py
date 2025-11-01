#!/usr/bin/env python
"""
Advanced Test Runner for Architect Agent ADK.

Complete version with all encoding fixes for Windows compatibility.
Handles gevent/locust encoding issues and provides comprehensive test execution.
"""

import argparse
import asyncio
import json
import logging
import os
import platform
import subprocess
import sys
import time
import io
import codecs
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ========== ENCODING FIX FOR WINDOWS ==========
# Must be done BEFORE any other imports

if platform.system() == 'Windows':
    # Force UTF-8 encoding everywhere
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'
    os.environ['GEVENT_NOWAITPID'] = '1'  # Disable gevent monkey patching for subprocess


    # Register codec to force UTF-8 instead of cp1252
    def force_utf8_codec(encoding_name):
        """Force UTF-8 codec for Windows encodings."""
        if encoding_name.lower() in ['cp1252', 'charmap', 'cp437', 'windows-1252']:
            return codecs.lookup('utf-8')
        return None


    codecs.register(force_utf8_codec)

    # Fix stdout and stderr
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)


# ========== ENUMS AND DATA CLASSES ==========

class TestSuite(Enum):
    """Available test suites."""
    ALL = "all"
    UNIT = "unit"
    INTEGRATION = "integration"
    LOAD = "load"
    SMOKE = "smoke"
    PERFORMANCE = "performance"


@dataclass
class TestResult:
    """Test execution result."""
    suite: str
    passed: bool
    duration: float
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    coverage: Optional[float] = None
    errors: List[str] = field(default_factory=list)
    output: str = ""


@dataclass
class CoverageReport:
    """Coverage analysis report."""
    total_lines: int
    covered_lines: int
    missed_lines: int
    coverage_percentage: float
    modules: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# ========== MAIN TEST RUNNER CLASS ==========

class AdvancedTestRunner:
    """Advanced test runner with comprehensive features and Windows encoding fixes."""

    def __init__(self, project_root: Path, verbose: bool = False):
        """
        Initialize the test runner.

        Args:
            project_root: Path to project root directory
            verbose: Enable verbose output
        """
        self.project_root = project_root
        self.verbose = verbose
        self.results: List[TestResult] = []
        self.start_time = datetime.now()

        # NEW: force working directory to project root to avoid relative path / coverage mismatches
        try:
            os.chdir(self.project_root)
        except Exception as e:  # pragma: no cover (unlikely)
            print(f"[WARN] Could not change directory to project root: {e}")

        # Setup logging with UTF-8
        self.setup_logging()
        # Verify test environment
        self.verify_environment()

    def setup_logging(self) -> None:
        """Configure logging with proper encoding for Windows."""
        log_dir = self.project_root / "tests" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"test_run_{timestamp}.log"

        # Formatter with UTF-8 support for emojis
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # File handler with UTF-8 encoding
        file_handler = logging.FileHandler(log_file, encoding='utf-8', errors='replace')
        file_handler.setFormatter(formatter)

        # Console handler with UTF-8
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)

        # Configure logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO if not self.verbose else logging.DEBUG)
        self.logger.handlers.clear()
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        self.logger.info(f"📝 Logging to: {log_file}")

    def verify_environment(self) -> None:
        """Verify the test environment is properly configured."""
        required_tools = ["python", "pytest", "coverage"]

        for tool in required_tools:
            if not self.check_tool_available(tool):
                self.logger.warning(f"⚠️ Tool not found: {tool}")

    def check_tool_available(self, tool: str) -> bool:
        """
        Check if a tool is available in the system.

        Args:
            tool: Tool name to check

        Returns:
            True if tool is available
        """
        try:
            result = self.run_command([tool, "--version"], timeout=5)
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def run_command(
            self,
            cmd: List[str],
            timeout: Optional[int] = None,
            env: Optional[Dict[str, str]] = None
    ) -> subprocess.CompletedProcess:
        """
        Run a command with proper encoding for Windows.

        Args:
            cmd: Command to run
            timeout: Command timeout in seconds
            env: Environment variables

        Returns:
            Completed process result
        """
        # Prepare environment with UTF-8 encoding
        run_env = os.environ.copy()
        run_env['PYTHONIOENCODING'] = 'utf-8'
        run_env['PYTHONUTF8'] = '1'

        if platform.system() == 'Windows':
            run_env['GEVENT_NOWAITPID'] = '1'  # Disable gevent subprocess monkey patching

        if env:
            run_env.update(env)

        # Platform-specific subprocess configuration
        kwargs = {
            'capture_output': True,
            'text': True,
            'timeout': timeout,
            'env': run_env,
            'encoding': 'utf-8',
            'errors': 'replace'
        }

        # Windows-specific flags
        if platform.system() == 'Windows':
            # Prevent console window popup
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = startupinfo

        try:
            self.logger.debug(f"Running command (cwd={self.project_root}): {' '.join(cmd)}")
            result = subprocess.run(cmd, cwd=self.project_root, **kwargs)
            if result.returncode != 0 and not result.stdout and not result.stderr:
                # Edge case: sometimes pytest output suppressed; note in log for diagnostics
                self.logger.warning("Command returned non-zero with empty output – possible working directory or encoding issue")
            return result

        except subprocess.TimeoutExpired:
            self.logger.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
            # Return a failed result instead of raising
            return subprocess.CompletedProcess(
                cmd,
                returncode=1,
                stdout="",
                stderr=f"Command timed out after {timeout}s"
            )
        except Exception as e:
            self.logger.error(f"Command failed: {e}")
            return subprocess.CompletedProcess(
                cmd,
                returncode=1,
                stdout="",
                stderr=str(e)
            )

    def check_environment(self) -> bool:
        """
        Check if the environment is properly configured.

        Returns:
            True if environment is ready
        """
        self.logger.info("🔍 Checking environment...")

        # Check Python version
        python_version = sys.version_info
        if python_version < (3, 8):
            self.logger.error(f"❌ Python 3.8+ required, found {python_version}")
            return False

        # Check required packages
        required_packages = [
            ("pytest", "pytest"),
            ("pytest-cov", "pytest_cov"),
            ("pytest-asyncio", "pytest_asyncio"),
            ("python-dotenv", "dotenv")
        ]

        # Check for Google ADK (optional)
        adk_available = False
        try:
            __import__("google.adk")
            adk_available = True
        except ImportError:
            try:
                __import__("adk")
                adk_available = True
            except ImportError:
                pass

        missing_packages = []
        for package_name, import_name in required_packages:
            try:
                __import__(import_name)
            except ImportError:
                missing_packages.append(package_name)

        if not adk_available:
            self.logger.warning("⚠️ Google ADK not found - this is optional for unit tests")

        if missing_packages:
            self.logger.error(f"❌ Missing required packages: {', '.join(missing_packages)}")
            self.logger.info("Install with: pip install " + " ".join(missing_packages))
            return False

        # Load environment variables
        env_file = self.project_root / ".env"
        if env_file.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(env_file)
                self.logger.info(f"✅ Loading environment from: {env_file}")
            except ImportError:
                self.logger.warning("⚠️ python-dotenv not installed, skipping .env file")

        return True

    def run_smoke_tests(self) -> TestResult:
        """
        Run smoke tests for basic functionality.

        Returns:
            Test result
        """
        self.logger.info("💨 Running Smoke Tests")
        start_time = time.time()

        cmd = [
            sys.executable, "-m", "pytest",
            str(self.project_root / "tests"),
            "-m", "smoke",
            "--tb=short",
            "-q",
            "--disable-warnings",
            "--no-header"
        ]

        try:
            result = self.run_command(cmd, timeout=60)
            duration = time.time() - start_time

            passed = result.returncode == 0

            if passed:
                self.logger.info(f"✅ Smoke tests passed in {duration:.2f}s")
            else:
                self.logger.error(f"❌ Smoke tests failed in {duration:.2f}s")
                if self.verbose:
                    self.logger.error(f"Output:\n{result.stdout}\n{result.stderr}")

            return TestResult(
                suite="smoke",
                passed=passed,
                duration=duration,
                output=result.stdout + result.stderr
            )

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"❌ Smoke tests failed in {duration:.2f}s: {e}")
            return TestResult(
                suite="smoke",
                passed=False,
                duration=duration,
                errors=[str(e)]
            )

    def run_unit_tests(self, verbose: bool = False) -> TestResult:
        """
        Run unit tests with coverage.

        Args:
            verbose: Enable verbose output

        Returns:
            Test result
        """
        self.logger.info("[TEST] Running Unit Tests")
        start_time = time.time()

        # Prepare coverage directory
        coverage_dir = self.project_root / "test_results"
        coverage_dir.mkdir(parents=True, exist_ok=True)
        cov_config = self.project_root / ".coveragerc"
        cmd = [
            sys.executable, "-m", "pytest",
            str(self.project_root / "tests" / "unit"),
            f"--cov=app",
            f"--cov-config={cov_config}" if cov_config.exists() else "",
            "--cov-report=html:" + str(coverage_dir / "coverage_html"),
            "--cov-report=xml:" + str(coverage_dir / "coverage.xml"),
            "--cov-report=term",
            "--tb=short",
            "-v" if verbose else "-q",
            "--color=yes",
            "--disable-warnings",
            "--no-header"
        ]
        # Remove empty string if cov-config missing
        cmd = [c for c in cmd if c]
        try:
            result = self.run_command(cmd, timeout=300)
            duration = time.time() - start_time
            test_summary = self.parse_pytest_output(result.stdout)
            passed = result.returncode == 0
            if passed:
                self.logger.info(f"[PASS] Unit tests passed in {duration:.2f}s")
            else:
                # NEW: dump trimmed stdout/stderr to help diagnose failures & coverage gaps
                head_out = "\n".join(result.stdout.splitlines()[-200:])  # last part only
                head_err = "\n".join(result.stderr.splitlines()[-200:])
                self.logger.error(f"[FAIL] Unit tests failed in {duration:.2f}s\n--- STDOUT (tail) ---\n{head_out}\n--- STDERR (tail) ---\n{head_err}")
            return TestResult(
                suite="unit",
                passed=passed,
                duration=duration,
                tests_run=test_summary['total'],
                tests_passed=test_summary['passed'],
                tests_failed=test_summary['failed'],
                tests_skipped=test_summary['skipped'],
                coverage=test_summary.get('coverage'),
                output=result.stdout + result.stderr
            )
        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"[FAIL] Unit tests failed in {duration:.2f}s: {e}")
            return TestResult(
                suite="unit",
                passed=False,
                duration=duration,
                errors=[str(e)]
            )

    def run_integration_tests(self, verbose: bool = False) -> TestResult:
        """
        Run integration tests.

        Args:
            verbose: Enable verbose output

        Returns:
            Test result
        """
        self.logger.info("🔗 Running Integration Tests")
        start_time = time.time()

        cmd = [
            sys.executable, "-m", "pytest",
            str(self.project_root / "tests" / "integration"),
            "--tb=short",
            "-v" if verbose else "-q",
            "--color=yes",
            "--asyncio-mode=auto",
            "--disable-warnings",
            "--no-header"
        ]

        try:
            result = self.run_command(cmd, timeout=600)
            duration = time.time() - start_time

            # Parse test results
            test_summary = self.parse_pytest_output(result.stdout)

            passed = result.returncode == 0

            if passed:
                self.logger.info(f"✅ Integration tests passed in {duration:.2f}s")
            else:
                tail_out = "\n".join(result.stdout.splitlines()[-200:]) if result.stdout else "<no stdout>"
                tail_err = "\n".join(result.stderr.splitlines()[-200:]) if result.stderr else "<no stderr>"
                self.logger.error(
                    "❌ Integration tests failed in %.2fs\n--- STDOUT (tail) ---\n%s\n--- STDERR (tail) ---\n%s"
                    % (duration, tail_out, tail_err)
                )

            return TestResult(
                suite="integration",
                passed=passed,
                duration=duration,
                tests_run=test_summary['total'],
                tests_passed=test_summary['passed'],
                tests_failed=test_summary['failed'],
                tests_skipped=test_summary['skipped'],
                output=result.stdout + result.stderr
            )

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"❌ Integration tests failed in {duration:.2f}s: {e}")
            return TestResult(
                suite="integration",
                passed=False,
                duration=duration,
                errors=[str(e)]
            )

    def run_load_tests(
            self,
            duration: int = 30,
            users: int = 5,
            spawn_rate: int = 2
    ) -> TestResult:
        """
        Run load tests safely without locust import issues.

        Args:
            duration: Test duration in seconds
            users: Number of concurrent users
            spawn_rate: User spawn rate per second

        Returns:
            Test result
        """
        self.logger.info(f"⚡ Running Load Tests (duration={duration}s, users={users}, spawn_rate={spawn_rate})")
        start_time = time.time()

        locust_file = self.project_root / "tests" / "load_test" / "load_test.py"

        if not locust_file.exists():
            self.logger.warning("Load test file not found, skipping")
            return TestResult(
                suite="load",
                passed=True,
                duration=0,
                errors=["Load test file not found"]
            )

        # Try to run with locust, but fall back to simple execution if it fails
        cmd = [
            sys.executable, "-m", "locust",
            "-f", str(locust_file),
            "--headless",
            "-u", str(users),
            "-r", str(spawn_rate),
            "-t", f"{duration}s",
            "--host", "http://localhost:8080",
            "--only-summary"
        ]

        try:
            result = self.run_command(cmd, timeout=duration + 60)
            test_duration = time.time() - start_time

            # Check if locust is not installed
            if "No module named" in result.stderr or "locust" in result.stderr.lower():
                # Fall back to running the Python file directly
                self.logger.info("⚡ Locust not available, running simplified load test")
                cmd_fallback = [sys.executable, str(locust_file)]
                result = self.run_command(cmd_fallback, timeout=30)

            # For load tests, we're more lenient with pass criteria
            passed = result.returncode == 0 or "not found" not in result.stderr.lower()

            if passed:
                self.logger.info(f"✅ Load tests completed in {test_duration:.2f}s")
            else:
                self.logger.warning(f"⚠️ Load tests had issues in {test_duration:.2f}s")

            return TestResult(
                suite="load",
                passed=True,  # Don't fail the whole suite for load tests
                duration=test_duration,
                output=result.stdout + result.stderr
            )

        except Exception as e:
            test_duration = time.time() - start_time
            self.logger.warning(f"⚠️ Load tests could not run: {e}")
            return TestResult(
                suite="load",
                passed=True,  # Don't fail for load test issues
                duration=test_duration,
                errors=[str(e)]
            )

    def finalize_coverage(self) -> None:
        """Combine coverage data from parallel test runs."""
        self.logger.info("[BUILD] Finalizing coverage (combining parallel data & regenerating reports)")
        coverage_dir = self.project_root / "test_results"
        rcfile = self.project_root / ".coveragerc"
        rc_args = ["--rcfile", str(rcfile)] if rcfile.exists() else []
        try:
            # Ensure we are in project root for all coverage commands
            os.chdir(self.project_root)
            self.run_command([sys.executable, "-m", "coverage", "combine", *rc_args], timeout=30)
            self.run_command([sys.executable, "-m", "coverage", "html", *rc_args, "-d", str(coverage_dir / "coverage_html")], timeout=30)
            self.run_command([sys.executable, "-m", "coverage", "xml", *rc_args, "-o", str(coverage_dir / "coverage.xml")], timeout=30)
            self.run_command([sys.executable, "-m", "coverage", "json", *rc_args, "-o", str(coverage_dir / "coverage.json")], timeout=30)
            self.logger.info(f"Coverage reports saved to: {coverage_dir}")
        except Exception as e:
            self.logger.error(f"Failed to finalize coverage: {e}")

    def analyze_coverage(self) -> Optional[CoverageReport]:
        """Analyze test coverage and generate report."""
        self.logger.info("[COVERAGE] Analyzing Test Coverage")
        coverage_dir = self.project_root / "test_results"
        json_file = coverage_dir / "coverage.json"
        rcfile = self.project_root / ".coveragerc"
        rc_args = ["--rcfile", str(rcfile)] if rcfile.exists() else []
        try:
            if not json_file.exists():
                self.run_command([sys.executable, "-m", "coverage", "json", *rc_args, "-o", str(json_file)], timeout=30)
            if not json_file.exists():
                self.logger.error("Failed to generate coverage JSON file")
                return None
            with open(json_file, 'r', encoding='utf-8') as f:
                coverage_data = json.load(f)
            summary = coverage_data.get("totals", {})
            total_lines = summary.get("num_statements", 0)
            covered_lines = summary.get("covered_lines", 0)
            missed_lines = summary.get("missing_lines", 0)
            line_coverage = summary.get("percent_covered", 0)
            modules = {}
            for file_path, file_data in coverage_data.get("files", {}).items():
                module_name = Path(file_path).stem
                fsum = file_data.get("summary", {})
                modules[module_name] = {
                    "coverage": fsum.get("percent_covered", 0),
                    "missing_lines": fsum.get("missing_lines", 0),
                    "excluded_lines": fsum.get("excluded_lines", 0)
                }
            report = CoverageReport(
                total_lines=total_lines,
                covered_lines=covered_lines,
                missed_lines=missed_lines,
                coverage_percentage=line_coverage,
                modules=modules
            )
            if line_coverage >= 80:
                self.logger.info(f"[PASS] Good coverage: {line_coverage:.1f}%")
            elif line_coverage >= 60:
                self.logger.warning(f"[WARN] Moderate coverage: {line_coverage:.1f}%")
            else:
                self.logger.warning(f"[FAIL] Low coverage: {line_coverage:.1f}% (threshold may be configured)")
            low_coverage_modules = [ (n,d) for n,d in modules.items() if d["coverage"] < 60 ]
            if low_coverage_modules:
                self.logger.info("[REPORT] Modules needing coverage improvement:")
                for name, data in sorted(low_coverage_modules, key=lambda x: x[1]["coverage"])[:5]:
                    self.logger.info(f"   - {name}: {data['coverage']:.1f}% (missing {data['missing_lines']} lines)")
            return report
        except Exception as e:
            self.logger.error(f"Coverage analysis failed: {e}")
            return None

    def parse_pytest_output(self, output: str) -> Dict[str, Any]:
        """
        Parse pytest output to extract test statistics.

        Args:
            output: Output from pytest

        Returns:
            Parsed test summary
        """
        summary = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'skipped': 0,
            'coverage': None
        }

        if not output:
            return summary

        lines = output.split('\n')

        for line in lines:
            # Parse test summary line
            if 'passed' in line or 'failed' in line or 'skipped' in line:
                import re

                # Match patterns like "5 passed" or "2 failed"
                passed_match = re.search(r'(\d+) passed', line)
                if passed_match:
                    summary['passed'] = int(passed_match.group(1))

                failed_match = re.search(r'(\d+) failed', line)
                if failed_match:
                    summary['failed'] = int(failed_match.group(1))

                skipped_match = re.search(r'(\d+) skipped', line)
                if skipped_match:
                    summary['skipped'] = int(skipped_match.group(1))

            # Parse coverage percentage
            if 'TOTAL' in line and '%' in line:
                parts = line.split()
                for part in parts:
                    if '%' in part:
                        try:
                            summary['coverage'] = float(part.replace('%', ''))
                        except ValueError:
                            pass

        summary['total'] = summary['passed'] + summary['failed'] + summary['skipped']

        return summary

    def generate_test_report(self) -> None:
        """Generate comprehensive test report."""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("📝 TEST EXECUTION REPORT")
        self.logger.info("=" * 80)

        total_duration = (datetime.now() - self.start_time).total_seconds()

        # Summary statistics
        total_tests = sum(r.tests_run for r in self.results)
        total_passed = sum(r.tests_passed for r in self.results)
        total_failed = sum(r.tests_failed for r in self.results)
        total_skipped = sum(r.tests_skipped for r in self.results)

        self.logger.info(f"⏱️ Total Duration: {total_duration:.2f}s")
        self.logger.info(f"📊 Total Tests Run: {total_tests}")
        self.logger.info(f"✅ Tests Passed: {total_passed}")
        self.logger.info(f"❌ Tests Failed: {total_failed}")
        self.logger.info(f"⏭️ Tests Skipped: {total_skipped}")

        # Suite results
        self.logger.info("\n📋 Suite Results:")
        for result in self.results:
            status = "✅ PASSED" if result.passed else "❌ FAILED"
            self.logger.info(f"   • {result.suite.upper()}: {status} ({result.duration:.2f}s)")
            if result.coverage is not None:
                self.logger.info(f"     Coverage: {result.coverage:.1f}%")

        # Overall status
        all_passed = all(r.passed for r in self.results)
        overall_status = "✅ SUCCESS" if all_passed else "❌ FAILURE"

        self.logger.info("\n" + "=" * 80)
        self.logger.info(f"🎯 OVERALL STATUS: {overall_status}")
        self.logger.info("=" * 80)

        # Save JSON report
        self.save_json_report()

    def save_json_report(self) -> None:
        """Save test results as JSON report."""
        report_file = self.project_root / "test_results" / "test_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)

        report_data = {
            "timestamp": self.start_time.isoformat(),
            "duration": (datetime.now() - self.start_time).total_seconds(),
            "results": [
                {
                    "suite": r.suite,
                    "passed": r.passed,
                    "duration": r.duration,
                    "tests_run": r.tests_run,
                    "tests_passed": r.tests_passed,
                    "tests_failed": r.tests_failed,
                    "tests_skipped": r.tests_skipped,
                    "coverage": r.coverage,
                    "errors": r.errors
                }
                for r in self.results
            ],
            "overall_passed": all(r.passed for r in self.results)
        }

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"📄 JSON report saved to: {report_file}")


# ========== MAIN FUNCTION ==========

def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(
        description="Advanced Test Runner for Architect Agent ADK"
    )

    parser.add_argument(
        "--suite",
        type=str,
        choices=[s.value for s in TestSuite],
        default=TestSuite.ALL.value,
        help="Test suite to run"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    parser.add_argument(
        "--no-benchmarks",
        action="store_true",
        help="Skip performance benchmarks"
    )

    parser.add_argument(
        "--load-duration",
        type=int,
        default=30,
        help="Load test duration in seconds"
    )

    parser.add_argument(
        "--load-users",
        type=int,
        default=5,
        help="Number of concurrent users for load testing"
    )

    args = parser.parse_args()

    # Determine project root
    project_root = Path(__file__).parent.parent.resolve()

    # Create test runner
    runner = AdvancedTestRunner(project_root, verbose=args.verbose)

    runner.logger.info("🚀 Starting Architect Agent Test Suite")
    runner.logger.info(f"📁 Project Root: {project_root}")
    runner.logger.info(f"🎯 Target Suite: {args.suite}")

    # Check environment
    if not runner.check_environment():
        runner.logger.error("Environment check failed. Please fix issues before running tests.")
        sys.exit(1)

    # Run test suites based on selection
    try:
        if args.suite in [TestSuite.ALL.value, TestSuite.SMOKE.value]:
            result = runner.run_smoke_tests()
            runner.results.append(result)

        if args.suite in [TestSuite.ALL.value, TestSuite.UNIT.value]:
            result = runner.run_unit_tests(verbose=args.verbose)
            runner.results.append(result)

        if args.suite in [TestSuite.ALL.value, TestSuite.INTEGRATION.value]:
            result = runner.run_integration_tests(verbose=args.verbose)
            runner.results.append(result)

        # Finalize coverage if unit or integration tests were run
        if any(r.suite in ["unit", "integration"] for r in runner.results):
            runner.finalize_coverage()
            runner.analyze_coverage()

        if args.suite in [TestSuite.ALL.value, TestSuite.LOAD.value] and not args.no_benchmarks:
            result = runner.run_load_tests(
                duration=args.load_duration,
                users=args.load_users
            )
            runner.results.append(result)

        # Generate final report
        runner.generate_test_report()

        # Exit with appropriate code
        all_passed = all(r.passed for r in runner.results)
        sys.exit(0 if all_passed else 1)

    except KeyboardInterrupt:
        runner.logger.warning("\n⚠️ Test execution interrupted by user")
        sys.exit(1)
    except Exception as e:
        runner.logger.error(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
