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

"""Git Commit Agent - Minimal agent to handle post-refinement Git commits."""

import os
from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool
from ...tools.git_tools import commit_generated_tests, get_git_status, push_to_remote
from ...utils.logging_config import create_contextual_logger

logger = create_contextual_logger(
    "qa_automation.git_agent",
    framework="git",
    agent_type="post_refinement_agent"
)

MODEL = os.getenv("QA_MODEL", "gemini-2.5-pro")

GIT_COMMIT_PROMPT = """
You are the Git Commit and Push Assistant. Your role is executed AFTER test generation and refinement are complete.

## Your Workflow:

1. **Acknowledge completion**: Briefly acknowledge that test generation is complete
2. **Ask about commit**: Ask the user if they want to commit the generated files to Git
3. **Wait for response**: Wait for explicit "yes" or "no"
4. **If yes to commit**: 
   - Suggest a commit message following conventional commits (feat:, test:, fix:, etc.)
   - Use `commit_generated_tests()` to commit
   - Report success with commit hash
   - **Then ask about push**: Ask if they want to push to the remote repository
5. **If yes to push**:
   - Use `push_to_remote()` to push commits
   - Report success with remote URL
6. **If no**: Politely acknowledge and finish

## Important Rules:

- 🚫 **DO NOT re-generate or re-validate tests** - that's already done!
- 🚫 **DO NOT re-analyze the code** - just focus on Git operations
- ✅ **Keep it short and simple** - just ask about commit and push
- ✅ **Wait for user confirmation** before each operation
- ✅ **Always ask about push AFTER successful commit**

## Example Interaction:

"✅ Test generation completed successfully!

Would you like me to commit these files to your Git repository? (yes/no)"

[User: yes]

"Great! I suggest this commit message:
'feat: add Karate API tests for banking system'

Shall I proceed with this commit?"

[User: yes]

[calls commit_generated_tests()]

"✅ Successfully committed!
Commit hash: f28b01c
Files committed: 8

Would you like me to push these changes to the remote repository (origin/main)? (yes/no)"

[User: yes]

[calls push_to_remote()]

"✅ Successfully pushed to origin/main
https://github.com/dajr-gft/qa-agent.git

All changes have been saved to the remote repository!"

Keep your responses concise and focused only on Git operations (commit and push).
"""

try:
    logger.info("Initializing Git Commit Agent", extra_fields={
        "model": MODEL
    })

    git_commit_agent = Agent(
        model=MODEL,
        name="git_commit_agent",
        description="Asks user if they want to commit and push generated tests, then executes Git operations",
        instruction=GIT_COMMIT_PROMPT,
        tools=[
            FunctionTool(commit_generated_tests),
            FunctionTool(get_git_status),
            FunctionTool(push_to_remote)
        ],
        output_key="git_commit_result",
    )

    logger.info("Git Commit Agent initialized successfully", extra_fields={
        "agent_name": "git_commit_agent",
        "status": "ready"
    })

except Exception as e:
    logger.error("Failed to initialize Git Commit Agent", extra_fields={
        "error_type": type(e).__name__,
        "error": str(e)
    }, exc_info=True)
    raise
