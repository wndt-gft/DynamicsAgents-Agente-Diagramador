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

"""File Manager - Handles saving BDD test files to filesystem."""

import os
from pathlib import Path
from typing import Dict, List
from ....utils.logging_config import create_contextual_logger

logger = create_contextual_logger(
    "cypress_file_manager",
    framework="cypress",
    component="file_manager"
)


def save_bdd_files_to_disk(
        files: Dict[str, Dict[str, str]],
        base_output_dir: str = None,
        create_structure: bool = True
) -> Dict[str, str]:
    """
    Save the 3 BDD files (Feature, Steps, Page Object) to filesystem.

    Args:
        files: Dictionary with file data:
            {
                "feature": {"path": "...", "content": "..."},
                "steps": {"path": "...", "content": "..."},
                "page_object": {"path": "...", "content": "..."}
            }
        base_output_dir: Base directory for output (default: current dir)
        create_structure: Create full directory structure if needed

    Returns:
        Dictionary with absolute paths of saved files:
        {
            "feature": "/full/path/to/features/login.feature",
            "steps": "/full/path/to/step_definitions/login_steps.js",
            "page_object": "/full/path/to/page_objects/LoginPage.js"
        }

    Raises:
        OSError: If unable to create directories or write files
        ValueError: If files dictionary is invalid
    """
    logger.info("Starting file save operation", extra_fields={
        "files_count": len(files),
        "base_dir": base_output_dir or "current_directory"
    })

    # Validate input
    if not files or len(files) != 3:
        raise ValueError(f"Expected 3 files, got {len(files) if files else 0}")

    required_keys = {"feature", "steps", "page_object"}
    if set(files.keys()) != required_keys:
        raise ValueError(f"Invalid file keys. Expected {required_keys}, got {set(files.keys())}")

    # Determine base directory
    if base_output_dir:
        base_path = Path(base_output_dir)
    else:
        # Use project root or current directory
        base_path = Path.cwd()

    saved_paths = {}

    try:
        # Save each file
        for file_type, file_data in files.items():
            if "path" not in file_data or "content" not in file_data:
                raise ValueError(f"File '{file_type}' missing 'path' or 'content'")

            # Build full path
            relative_path = file_data["path"]
            full_path = base_path / relative_path

            # Create directory structure if needed
            if create_structure:
                full_path.parent.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Ensured directory exists: {full_path.parent}")

            # Write file
            full_path.write_text(file_data["content"], encoding='utf-8')

            saved_paths[file_type] = str(full_path.absolute())

            logger.info(f"Saved {file_type} file", extra_fields={
                "path": str(full_path),
                "size_bytes": len(file_data["content"]),
                "lines": len(file_data["content"].splitlines())
            })

        logger.info("All files saved successfully", extra_fields={
            "total_files": len(saved_paths),
            "base_directory": str(base_path.absolute())
        })

        return saved_paths

    except OSError as e:
        logger.error(f"Failed to save files: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error saving files: {e}", exc_info=True)
        raise


def get_default_output_directory() -> str:
    """
    Get the default output directory for Cypress tests.

    Returns:
        Absolute path to default output directory
    """
    # Try to find cypress directory in project
    current = Path.cwd()

    # Look for existing cypress directory
    cypress_dirs = list(current.rglob("cypress"))
    if cypress_dirs:
        logger.info(f"Found existing cypress directory: {cypress_dirs[0]}")
        return str(cypress_dirs[0])

    # Default to ./cypress in current directory
    default_dir = current / "cypress"
    logger.info(f"Using default cypress directory: {default_dir}")
    return str(default_dir)


def create_cypress_directory_structure(base_dir: str) -> Dict[str, str]:
    """
    Create standard Cypress BDD directory structure.

    Args:
        base_dir: Base directory for Cypress tests

    Returns:
        Dictionary with created directory paths
    """
    base_path = Path(base_dir)

    directories = {
        "features": base_path / "e2e" / "features",
        "step_definitions": base_path / "e2e" / "step_definitions",
        "page_objects": base_path / "support" / "page_objects",
        "fixtures": base_path / "fixtures",
        "support": base_path / "support",
    }

    created = {}

    for name, path in directories.items():
        path.mkdir(parents=True, exist_ok=True)
        created[name] = str(path.absolute())
        logger.debug(f"Created directory: {name} -> {path}")

    logger.info("Cypress directory structure created", extra_fields={
        "base_dir": str(base_path),
        "directories_created": len(created)
    })

    return created


def list_generated_files(base_dir: str = None) -> List[Dict[str, str]]:
    """
    List all generated BDD test files.

    Args:
        base_dir: Base directory to search (default: auto-detect)

    Returns:
        List of file information dictionaries
    """
    if not base_dir:
        base_dir = get_default_output_directory()

    base_path = Path(base_dir)

    files_info = []

    # Find feature files
    for feature_file in base_path.rglob("*.feature"):
        files_info.append({
            "type": "feature",
            "path": str(feature_file),
            "relative_path": str(feature_file.relative_to(base_path)),
            "size": feature_file.stat().st_size,
            "modified": feature_file.stat().st_mtime
        })

    # Find step definition files
    for steps_file in base_path.rglob("*_steps.js"):
        files_info.append({
            "type": "steps",
            "path": str(steps_file),
            "relative_path": str(steps_file.relative_to(base_path)),
            "size": steps_file.stat().st_size,
            "modified": steps_file.stat().st_mtime
        })

    # Find page object files
    for po_file in base_path.rglob("*Page.js"):
        files_info.append({
            "type": "page_object",
            "path": str(po_file),
            "relative_path": str(po_file.relative_to(base_path)),
            "size": po_file.stat().st_size,
            "modified": po_file.stat().st_mtime
        })

    logger.info(f"Found {len(files_info)} generated files")

    return files_info
