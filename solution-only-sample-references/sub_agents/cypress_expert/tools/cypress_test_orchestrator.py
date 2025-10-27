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

"""Cypress Test Orchestrator - Handles BDD test generation and file parsing."""

import re
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .file_manager import save_bdd_files_to_disk, get_default_output_directory
from ....utils.logging_config import create_contextual_logger

logger = create_contextual_logger(
    "cypress_orchestrator",
    framework="cypress",
    component="orchestrator"
)


@dataclass
class BDDTestFiles:
    """Structure to hold the 3 generated BDD files."""
    feature_file: str
    feature_content: str
    steps_file: str
    steps_content: str
    page_object_file: str
    page_object_content: str
    feature_name: str


def parse_bdd_response(agent_response: str, feature_name: Optional[str] = None) -> BDDTestFiles:
    """
    Parse agent response and extract the 3 BDD files.

    Expected format in agent response:
    === FILE: features/login.feature ===
    [content]
    === END FILE ===

    === FILE: cypress/e2e/step_definitions/login_steps.js ===
    [content]
    === END FILE ===

    === FILE: cypress/support/page_objects/LoginPage.js ===
    [content]
    === END FILE ===

    Args:
        agent_response: Raw response from the Gemini agent
        feature_name: Optional feature name (will be inferred if not provided)

    Returns:
        BDDTestFiles with parsed content

    Raises:
        ValueError: If response doesn't contain exactly 3 files
        KeyError: If file types cannot be identified
    """
    logger.debug("Parsing BDD response", extra_fields={
        "response_length": len(agent_response),
        "feature_name_provided": feature_name is not None
    })

    # Regex pattern to extract files between delimiters
    file_pattern = r'=== FILE: (.+?) ===\n(.*?)\n=== END FILE ==='
    matches = re.findall(file_pattern, agent_response, re.DOTALL)

    if len(matches) != 3:
        logger.error(f"Expected 3 files but found {len(matches)}", extra_fields={
            "matches_found": len(matches),
            "file_paths": [m[0] for m in matches]
        })
        raise ValueError(
            f"Expected exactly 3 files in response, but found {len(matches)}. "
            f"Agent response may be malformed or incomplete."
        )

    # Organize files in dictionary
    files = {}
    for filepath, content in matches:
        files[filepath.strip()] = content.strip()

    # Identify each file type
    feature_file = None
    steps_file = None
    page_object_file = None

    for filepath in files.keys():
        if filepath.endswith('.feature'):
            feature_file = filepath
        elif '_steps.js' in filepath or 'step_definitions' in filepath:
            steps_file = filepath
        elif 'Page.js' in filepath or 'page_objects' in filepath:
            page_object_file = filepath

    # Validate all files were identified
    if not all([feature_file, steps_file, page_object_file]):
        missing = []
        if not feature_file:
            missing.append("feature (.feature)")
        if not steps_file:
            missing.append("steps (_steps.js)")
        if not page_object_file:
            missing.append("page_object (Page.js)")

        logger.error("Could not identify all file types", extra_fields={
            "missing_types": missing,
            "found_paths": list(files.keys())
        })
        raise KeyError(
            f"Could not identify all three file types. Missing: {', '.join(missing)}"
        )

    # Infer feature_name if not provided
    if not feature_name:
        import os
        feature_name = os.path.splitext(os.path.basename(feature_file))[0]

    logger.info("Successfully parsed BDD files", extra_fields={
        "feature_name": feature_name,
        "feature_file": feature_file,
        "steps_file": steps_file,
        "page_object_file": page_object_file
    })

    return BDDTestFiles(
        feature_file=feature_file,
        feature_content=files[feature_file],
        steps_file=steps_file,
        steps_content=files[steps_file],
        page_object_file=page_object_file,
        page_object_content=files[page_object_file],
        feature_name=feature_name
    )


def validate_bdd_files(bdd_files: BDDTestFiles) -> Dict[str, Any]:
    """
    Validate the generated BDD files for quality and completeness.

    Args:
        bdd_files: Parsed BDD files structure

    Returns:
        Validation result:
        {
            "valid": bool,
            "quality_score": int (0-100),
            "errors": List[str],
            "warnings": List[str],
            "metrics": Dict[str, int]
        }
    """
    logger.debug("Validating BDD files", extra_fields={
        "feature_name": bdd_files.feature_name
    })

    errors = []
    warnings = []
    quality_score = 100

    # Validate Feature file
    if not bdd_files.feature_content.strip():
        errors.append("Feature file is empty")
        quality_score -= 40
    else:
        # Check for Gherkin keywords
        gherkin_keywords = ['Feature:', 'Scenario:', 'Given', 'When', 'Then']
        missing_keywords = [kw for kw in gherkin_keywords
                            if kw not in bdd_files.feature_content]
        if missing_keywords:
            errors.append(f"Feature file missing Gherkin keywords: {', '.join(missing_keywords)}")
            quality_score -= 20

        # Check for Background or Examples (bonus)
        if 'Background:' in bdd_files.feature_content:
            logger.debug("Feature includes Background section")
        if 'Examples:' in bdd_files.feature_content:
            logger.debug("Feature includes Scenario Outline with Examples")

    # Validate Steps file
    if not bdd_files.steps_content.strip():
        errors.append("Steps file is empty")
        quality_score -= 40
    else:
        # Check for Cucumber imports
        if '@badeball/cypress-cucumber-preprocessor' not in bdd_files.steps_content:
            errors.append("Steps file missing Cucumber preprocessor imports")
            quality_score -= 15

        # Check for step definitions
        step_keywords = ['Given(', 'When(', 'Then(', 'And(']
        if not any(kw in bdd_files.steps_content for kw in step_keywords):
            errors.append("Steps file missing step definitions (Given/When/Then/And)")
            quality_score -= 20

        # Check for Page Object import
        if 'import' not in bdd_files.steps_content or 'Page' not in bdd_files.steps_content:
            warnings.append("Steps file may be missing Page Object import")
            quality_score -= 5

    # Validate Page Object file
    if not bdd_files.page_object_content.strip():
        errors.append("Page Object file is empty")
        quality_score -= 40
    else:
        # Check for class definition
        if 'class ' not in bdd_files.page_object_content:
            errors.append("Page Object missing class definition")
            quality_score -= 20

        # Check for export
        if 'export default' not in bdd_files.page_object_content:
            errors.append("Page Object missing export statement")
            quality_score -= 10

        # Check for constructor and selectors
        if 'constructor()' not in bdd_files.page_object_content:
            warnings.append("Page Object may be missing constructor")
            quality_score -= 5

        if 'this.selectors' not in bdd_files.page_object_content:
            warnings.append("Page Object may be missing selectors definition")
            quality_score -= 5

    # Calculate metrics
    metrics = {
        "feature_lines": len(bdd_files.feature_content.split('\n')),
        "steps_lines": len(bdd_files.steps_content.split('\n')),
        "page_object_lines": len(bdd_files.page_object_content.split('\n')),
        "scenarios_count": bdd_files.feature_content.count('Scenario:'),
        "step_definitions_count": sum(
            bdd_files.steps_content.count(kw)
            for kw in ['Given(', 'When(', 'Then(', 'And(']
        )
    }

    # Ensure score doesn't go below 0
    quality_score = max(0, quality_score)

    is_valid = len(errors) == 0 and quality_score >= 60

    logger.info("BDD files validation completed", extra_fields={
        "valid": is_valid,
        "quality_score": quality_score,
        "errors_count": len(errors),
        "warnings_count": len(warnings),
        **metrics
    })

    return {
        "valid": is_valid,
        "quality_score": quality_score,
        "errors": errors,
        "warnings": warnings,
        "metrics": metrics
    }


def process_agent_response_and_save(
        agent_response: str,
        feature_name: Optional[str] = None,
        output_dir: Optional[str] = None,
        save_to_disk: bool = True
) -> Dict[str, Any]:
    """
    Process raw agent response, validate, and save files to disk.

    This is the MAIN function that ties everything together.

    Args:
        agent_response: Raw response from agent containing 3 files
        feature_name: Optional feature name
        output_dir: Output directory (default: auto-detect cypress dir)
        save_to_disk: Whether to save files to filesystem

    Returns:
        Structured result with validated files and saved paths
    """
    logger.info("Processing agent response", extra_fields={
        "response_length": len(agent_response),
        "feature_name": feature_name or "auto",
        "save_to_disk": save_to_disk
    })

    try:
        # 1. Parse the 3 files
        bdd_files = parse_bdd_response(agent_response, feature_name)

        # 2. Validate files
        validation = validate_bdd_files(bdd_files)

        # 3. Prepare file structure for saving
        files_dict = {
            "feature": {
                "path": bdd_files.feature_file,
                "content": bdd_files.feature_content
            },
            "steps": {
                "path": bdd_files.steps_file,
                "content": bdd_files.steps_content
            },
            "page_object": {
                "path": bdd_files.page_object_file,
                "content": bdd_files.page_object_content
            }
        }

        # 4. Save to disk if requested
        saved_paths = None
        if save_to_disk:
            if not output_dir:
                output_dir = get_default_output_directory()

            logger.info(f"Saving files to: {output_dir}")
            saved_paths = save_bdd_files_to_disk(
                files_dict,
                base_output_dir=output_dir,
                create_structure=True
            )

            logger.info("Files saved successfully", extra_fields={
                "saved_count": len(saved_paths),
                "output_dir": output_dir
            })

        # 5. Build structured response
        result = {
            "status": "success" if validation["valid"] else "warning",
            "files": files_dict,
            "saved_paths": saved_paths,
            "metadata": {
                "feature_name": bdd_files.feature_name,
                "test_type": "bdd",
                "output_format": "three_files",
                "scenarios_count": validation["metrics"]["scenarios_count"],
                "steps_count": validation["metrics"]["step_definitions_count"],
                "output_directory": output_dir if save_to_disk else None
            },
            "quality_score": validation["quality_score"],
            "validation": {
                "valid": validation["valid"],
                "errors": validation["errors"],
                "warnings": validation["warnings"],
                "metrics": validation["metrics"]
            }
        }

        logger.info("Agent response processed successfully", extra_fields={
            "feature_name": bdd_files.feature_name,
            "quality_score": validation["quality_score"],
            "valid": validation["valid"],
            "files_saved": save_to_disk
        })

        return result

    except Exception as e:
        logger.error(f"Error processing agent response: {e}", exc_info=True)
        raise


# Keep for backwards compatibility
def generate_expert_cypress_qa_tests(
        gherkin_scenario: str,
        page_html: str,
        feature_name: Optional[str] = None,
        test_type: str = "bdd",
        output_format: str = "three_files",
        include_error_scenarios: bool = True,
        automation_level: str = "medium",
        custom_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Main orchestrator function for generating Cypress BDD tests.

    NOTE: This function is called by the wrapper, but the actual
    generation happens in the agent. This prepares the context.

    Use process_agent_response_and_save() to handle the agent's response.
    """
    logger.info("Cypress test generation orchestration started", extra_fields={
        "feature_name": feature_name or "auto",
        "test_type": test_type,
        "output_format": output_format
    })

    # Return template - will be populated by agent
    return {
        "gherkin_scenario": gherkin_scenario,
        "page_html": page_html,
        "feature_name": feature_name,
        "test_type": test_type,
        "output_format": output_format
    }