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

"""Git tools for committing generated test code."""

import subprocess
import os
from typing import Dict, Any, Optional


def commit_generated_tests(
    commit_message: str,
    files_to_commit: Optional[list] = None,
    working_directory: Optional[str] = None
) -> Dict[str, Any]:
    """
    Commit generated test files to Git repository.

    This function stages and commits the generated test files to the Git repository.
    If no specific files are provided, it will stage all changes in the working directory.

    Args:
        commit_message: The commit message describing the changes
        files_to_commit: Optional list of specific files to commit. If None, stages all changes.
        working_directory: Optional working directory path. If None, uses current directory.

    Returns:
        Dictionary containing:
        - success: bool - Whether the commit was successful
        - commit_hash: str - The hash of the created commit (if successful)
        - message: str - Status message
        - files_committed: list - List of files that were committed

    Example:
        >>> result = commit_generated_tests(
        ...     commit_message="feat: add Karate API tests for banking system",
        ...     files_to_commit=["src/test/java/banking/auth/auth.feature"]
        ... )
        >>> print(result["success"])
        True
    """

    result = {
        "success": False,
        "commit_hash": None,
        "message": "",
        "files_committed": []
    }

    original_dir = None

    try:
        # Set working directory
        if working_directory:
            original_dir = os.getcwd()
            os.chdir(working_directory)

        # Check if we're in a git repository
        check_repo = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False
        )

        if check_repo.returncode != 0:
            result["message"] = "Error: Not inside a Git repository. Please initialize Git first with 'git init'."
            return result

        # Stage files
        if files_to_commit:
            # Stage specific files
            for file_path in files_to_commit:
                stage_result = subprocess.run(
                    ["git", "add", file_path],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if stage_result.returncode == 0:
                    result["files_committed"].append(file_path)
        else:
            # Stage all changes
            stage_result = subprocess.run(
                ["git", "add", "."],
                capture_output=True,
                text=True,
                check=False
            )

            if stage_result.returncode == 0:
                # Get list of staged files
                status_result = subprocess.run(
                    ["git", "diff", "--cached", "--name-only"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if status_result.returncode == 0:
                    result["files_committed"] = status_result.stdout.strip().split("\n")

        # Check if there are changes to commit
        if not result["files_committed"] or result["files_committed"] == ['']:
            result["message"] = "No changes to commit. All files are already up to date."
            result["success"] = True
            return result

        # Commit the changes
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            capture_output=True,
            text=True,
            check=False
        )

        if commit_result.returncode == 0:
            # Get the commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False
            )

            if hash_result.returncode == 0:
                result["commit_hash"] = hash_result.stdout.strip()

            result["success"] = True
            result["message"] = f"✅ Successfully committed {len(result['files_committed'])} file(s) with message: '{commit_message}'"
        else:
            result["message"] = f"Error committing changes: {commit_result.stderr}"

        # Restore original directory if changed
        if working_directory:
            os.chdir(original_dir)

    except subprocess.CalledProcessError as e:
        result["message"] = f"Git command failed: {str(e)}"
    except Exception as e:
        result["message"] = f"Unexpected error: {str(e)}"

    return result


def get_git_status() -> Dict[str, Any]:
    """
    Get the current Git repository status.

    Returns:
        Dictionary containing:
        - has_changes: bool - Whether there are uncommitted changes
        - staged_files: list - List of staged files
        - unstaged_files: list - List of modified but unstaged files
        - untracked_files: list - List of untracked files
        - current_branch: str - Current branch name
    """

    result = {
        "has_changes": False,
        "staged_files": [],
        "unstaged_files": [],
        "untracked_files": [],
        "current_branch": None
    }

    try:
        # Get current branch
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False
        )
        if branch_result.returncode == 0:
            result["current_branch"] = branch_result.stdout.strip()

        # Get staged files
        staged_result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=False
        )
        if staged_result.returncode == 0:
            staged = staged_result.stdout.strip().split("\n")
            result["staged_files"] = [f for f in staged if f]

        # Get unstaged files
        unstaged_result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
            check=False
        )
        if unstaged_result.returncode == 0:
            unstaged = unstaged_result.stdout.strip().split("\n")
            result["unstaged_files"] = [f for f in unstaged if f]

        # Get untracked files
        untracked_result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            check=False
        )
        if untracked_result.returncode == 0:
            untracked = untracked_result.stdout.strip().split("\n")
            result["untracked_files"] = [f for f in untracked if f]

        result["has_changes"] = bool(
            result["staged_files"] or
            result["unstaged_files"] or
            result["untracked_files"]
        )

    except Exception as e:
        print(f"Error getting git status: {str(e)}")

    return result


def push_to_remote(
    remote_name: str = "origin",
    branch_name: Optional[str] = None,
    force: bool = False,
    working_directory: Optional[str] = None
) -> Dict[str, Any]:
    """
    Push commits to remote Git repository.

    This function pushes local commits to the remote repository (e.g., GitHub, GitLab).
    By default, it pushes to 'origin' remote on the current branch.

    Args:
        remote_name: Name of the remote (default: "origin")
        branch_name: Branch to push. If None, uses current branch.
        force: Whether to force push (use with caution!)
        working_directory: Optional working directory path. If None, uses current directory.

    Returns:
        Dictionary containing:
        - success: bool - Whether the push was successful
        - remote: str - Remote name used
        - branch: str - Branch that was pushed
        - message: str - Status message
        - remote_url: str - URL of the remote repository

    Example:
        >>> result = push_to_remote(remote_name="origin", branch_name="main")
        >>> print(result["success"])
        True
    """

    result = {
        "success": False,
        "remote": remote_name,
        "branch": None,
        "message": "",
        "remote_url": None
    }

    original_dir = None

    try:
        # Set working directory
        if working_directory:
            original_dir = os.getcwd()
            os.chdir(working_directory)

        # Check if we're in a git repository
        check_repo = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False
        )

        if check_repo.returncode != 0:
            result["message"] = "Error: Not inside a Git repository."
            return result

        # Get current branch if not specified
        if not branch_name:
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=False
            )
            if branch_result.returncode == 0:
                branch_name = branch_result.stdout.strip()
            else:
                result["message"] = "Error: Could not determine current branch."
                return result

        result["branch"] = branch_name

        # Get remote URL
        remote_url_result = subprocess.run(
            ["git", "remote", "get-url", remote_name],
            capture_output=True,
            text=True,
            check=False
        )

        if remote_url_result.returncode == 0:
            result["remote_url"] = remote_url_result.stdout.strip()
        else:
            result["message"] = f"Error: Remote '{remote_name}' not found. Please check your Git remote configuration."
            return result

        # Check if there are commits to push
        status_result = subprocess.run(
            ["git", "status", "-sb"],
            capture_output=True,
            text=True,
            check=False
        )

        # Build push command
        push_cmd = ["git", "push", remote_name, branch_name]
        if force:
            push_cmd.append("--force")

        # Execute push
        push_result = subprocess.run(
            push_cmd,
            capture_output=True,
            text=True,
            check=False
        )

        if push_result.returncode == 0:
            result["success"] = True
            result["message"] = f"✅ Successfully pushed to {remote_name}/{branch_name}\n{result['remote_url']}"
        else:
            error_message = push_result.stderr.strip()

            # Check for common errors
            if "rejected" in error_message.lower():
                result["message"] = f"❌ Push rejected. The remote has changes you don't have locally.\nSuggestion: Run 'git pull' first to merge remote changes."
            elif "authentication" in error_message.lower() or "permission" in error_message.lower():
                result["message"] = f"❌ Authentication failed. Please check your Git credentials and access rights."
            else:
                result["message"] = f"❌ Push failed: {error_message}"

        # Restore original directory if changed
        if original_dir:
            os.chdir(original_dir)

    except subprocess.CalledProcessError as e:
        result["message"] = f"Git command failed: {str(e)}"
    except Exception as e:
        result["message"] = f"Unexpected error: {str(e)}"

    return result
