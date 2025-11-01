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

"""File writer tools for saving generated test code to disk."""

import os
import json
import tempfile
import shutil
from typing import Dict, Any, List
from pathlib import Path


def write_generated_files_to_temp(
    generated_output: Dict[str, Any],
    framework: str
) -> Dict[str, Any]:
    """
    Write generated test files to a temporary directory.

    This function creates a temporary directory and saves all generated test files
    from the expert agent output. The directory is NOT cleaned up automatically -
    use cleanup_temp_directory() after Git operations are complete.

    Args:
        generated_output: Output from expert agent containing file contents
        framework: Framework type (karate, newman, cypress, playwright)

    Returns:
        Dictionary containing:
        - success: bool - Whether files were written successfully
        - temp_directory: str - Path to temporary directory
        - files_written: List[str] - List of files written (relative paths)
        - file_count: int - Number of files written
        - message: str - Status message

    Example:
        >>> result = write_generated_files_to_temp(karate_output, "karate")
        >>> print(result["temp_directory"])
        C:\\Users\\dajr\\AppData\\Local\\Temp\\qa_tests_abc123
        >>> print(result["files_written"])
        ['src/test/java/banking/auth/auth.feature', 'karate-config.js']
    """

    result = {
        "success": False,
        "temp_directory": None,
        "files_written": [],
        "file_count": 0,
        "message": ""
    }

    try:
        # Create temporary directory with prefix
        temp_dir = tempfile.mkdtemp(prefix=f"qa_tests_{framework}_")
        result["temp_directory"] = temp_dir

        # Write files based on framework
        if framework == "karate":
            files_written = _write_karate_files(temp_dir, generated_output)
        elif framework == "newman":
            files_written = _write_newman_files(temp_dir, generated_output)
        elif framework == "cypress":
            files_written = _write_cypress_files(temp_dir, generated_output)
        elif framework == "playwright":
            files_written = _write_playwright_files(temp_dir, generated_output)
        else:
            result["message"] = f"Unsupported framework: {framework}"
            return result

        result["files_written"] = files_written
        result["file_count"] = len(files_written)
        result["success"] = True
        result["message"] = f"✅ Successfully wrote {len(files_written)} files to {temp_dir}"

    except Exception as e:
        result["message"] = f"Error writing files: {str(e)}"
        # Cleanup temp dir if creation failed
        if result["temp_directory"] and os.path.exists(result["temp_directory"]):
            shutil.rmtree(result["temp_directory"], ignore_errors=True)

    return result


def _write_karate_files(temp_dir: str, output: Dict[str, Any]) -> List[str]:
    """Write Karate framework files to disk."""
    files_written = []

    # Create standard Karate directory structure
    src_test_java = Path(temp_dir) / "src" / "test" / "java"
    src_test_java.mkdir(parents=True, exist_ok=True)

    # Write feature files
    if "feature_files" in output:
        for feature in output["feature_files"]:
            # Extract domain/module path
            domain = feature.get("domain", "tests")
            module = feature.get("module", "api")

            feature_dir = src_test_java / domain / module
            feature_dir.mkdir(parents=True, exist_ok=True)

            file_path = feature_dir / f"{feature['name']}.feature"
            file_path.write_text(feature["content"], encoding="utf-8")
            files_written.append(str(file_path.relative_to(temp_dir)))

    # Write config files
    if "config_files" in output:
        for config in output["config_files"]:
            file_path = Path(temp_dir) / config["name"]
            file_path.write_text(config["content"], encoding="utf-8")
            files_written.append(config["name"])

    # Write test data
    if "test_data" in output:
        data_dir = src_test_java / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        for data_file in output["test_data"]:
            file_path = data_dir / data_file["name"]
            if data_file["name"].endswith(".json"):
                file_path.write_text(json.dumps(data_file["content"], indent=2), encoding="utf-8")
            else:
                file_path.write_text(data_file["content"], encoding="utf-8")
            files_written.append(str(file_path.relative_to(temp_dir)))

    # Write pom.xml if present
    if "pom_xml" in output:
        pom_path = Path(temp_dir) / "pom.xml"
        pom_path.write_text(output["pom_xml"], encoding="utf-8")
        files_written.append("pom.xml")

    return files_written


def _write_newman_files(temp_dir: str, output: Dict[str, Any]) -> List[str]:
    """Write Newman/Postman collection files to disk."""
    files_written = []

    # Write collection file
    if "collection" in output:
        collection_path = Path(temp_dir) / "collection.json"
        collection_path.write_text(
            json.dumps(output["collection"], indent=2),
            encoding="utf-8"
        )
        files_written.append("collection.json")

    # Write environment files
    if "environments" in output:
        for env_name, env_data in output["environments"].items():
            env_path = Path(temp_dir) / f"{env_name}.postman_environment.json"
            env_path.write_text(
                json.dumps(env_data, indent=2),
                encoding="utf-8"
            )
            files_written.append(f"{env_name}.postman_environment.json")

    # Write README if present
    if "readme" in output:
        readme_path = Path(temp_dir) / "README.md"
        readme_path.write_text(output["readme"], encoding="utf-8")
        files_written.append("README.md")

    return files_written


def _write_cypress_files(temp_dir: str, output: Dict[str, Any]) -> List[str]:
    """Write Cypress test files to disk."""
    files_written = []

    # Create Cypress directory structure
    cypress_dir = Path(temp_dir) / "cypress"
    e2e_dir = cypress_dir / "e2e"
    e2e_dir.mkdir(parents=True, exist_ok=True)

    # Write spec files
    if "spec_files" in output:
        for spec in output["spec_files"]:
            file_path = e2e_dir / spec["name"]
            file_path.write_text(spec["content"], encoding="utf-8")
            files_written.append(str(file_path.relative_to(temp_dir)))

    # Write config
    if "cypress_config" in output:
        config_path = Path(temp_dir) / "cypress.config.js"
        config_path.write_text(output["cypress_config"], encoding="utf-8")
        files_written.append("cypress.config.js")

    return files_written


def _write_playwright_files(temp_dir: str, output: Dict[str, Any]) -> List[str]:
    """Write Playwright test files to disk."""
    files_written = []

    # Create tests directory
    tests_dir = Path(temp_dir) / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    # Write test files
    if "test_files" in output:
        for test in output["test_files"]:
            file_path = tests_dir / test["name"]
            file_path.write_text(test["content"], encoding="utf-8")
            files_written.append(str(file_path.relative_to(temp_dir)))

    # Write config
    if "playwright_config" in output:
        config_path = Path(temp_dir) / "playwright.config.js"
        config_path.write_text(output["playwright_config"], encoding="utf-8")
        files_written.append("playwright.config.js")

    return files_written


def cleanup_temp_directory(temp_directory: str) -> Dict[str, Any]:
    """
    Clean up temporary directory after Git operations are complete.

    This should be called AFTER successful Git push to remove all temporary files.

    Args:
        temp_directory: Path to temporary directory to remove

    Returns:
        Dictionary containing:
        - success: bool - Whether cleanup was successful
        - message: str - Status message
    """

    result = {
        "success": False,
        "message": ""
    }

    try:
        if not temp_directory or not os.path.exists(temp_directory):
            result["message"] = "Temporary directory not found or already cleaned up"
            result["success"] = True
            return result

        # Verify it's actually a temp directory (safety check)
        if "qa_tests_" not in temp_directory or "Temp" not in temp_directory:
            result["message"] = f"Safety check failed: {temp_directory} doesn't look like a temp directory"
            return result

        # Remove directory and all contents
        shutil.rmtree(temp_directory)

        result["success"] = True
        result["message"] = f"✅ Cleaned up temporary directory: {temp_directory}"

    except Exception as e:
        result["message"] = f"Error cleaning up temp directory: {str(e)}"

    return result


def get_temp_directory_info(temp_directory: str) -> Dict[str, Any]:
    """
    Get information about the temporary directory.

    Args:
        temp_directory: Path to temporary directory

    Returns:
        Dictionary containing directory info (size, file count, etc.)
    """

    result = {
        "exists": False,
        "file_count": 0,
        "total_size_bytes": 0,
        "files": []
    }

    try:
        if not os.path.exists(temp_directory):
            return result

        result["exists"] = True

        # Walk through directory
        for root, dirs, files in os.walk(temp_directory):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, temp_directory)
                file_size = os.path.getsize(file_path)

                result["files"].append({
                    "path": rel_path,
                    "size_bytes": file_size
                })
                result["total_size_bytes"] += file_size

        result["file_count"] = len(result["files"])

    except Exception as e:
        result["error"] = str(e)

    return result

