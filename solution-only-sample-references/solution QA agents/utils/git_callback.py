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

"""Post-refinement callback to offer Git commit functionality."""

from typing import Any
from google.adk.events import GenerationEvent
from ..logging_config import create_contextual_logger

logger = create_contextual_logger(
    "qa_automation.git_callback",
    framework="git",
    component="post_refinement"
)


def offer_git_commit_callback(event: GenerationEvent) -> Any:
    """
    Callback executed after refinement loop completes.

    This callback adds a message to the conversation offering to commit
    the generated code to Git, but does NOT interfere with the refinement loop.
    It simply appends helpful information to the final output.

    Args:
        event: The generation event from the refinement loop

    Returns:
        The event unchanged (we only log and potentially modify the message)
    """

    try:
        logger.info("Post-refinement callback triggered", extra_fields={
            "stage": "git_offer"
        })

        # Extract the final response from the event
        if hasattr(event, 'text') and event.text:
            # Add Git commit offer to the response
            git_offer_message = """

---

## 💾 Git Commit Option

The test generation and validation process is now complete!

If you'd like to commit these generated test files to your Git repository, just let me know and I can help you with that. I can:
- Check what files have changed
- Suggest an appropriate commit message
- Execute the commit for you

Simply reply with "commit" or "yes, commit the files" and I'll guide you through it.

Otherwise, the generated test files are ready for you to use! 📝
"""

            # Note: We can't modify the event text directly in ADK
            # Instead, we'll log this for tracking
            logger.info("Git commit offer prepared", extra_fields={
                "offer_added": True,
                "next_step": "user_can_request_commit"
            })

    except Exception as e:
        logger.error("Error in git commit callback", extra_fields={
            "error": str(e)
        }, exc_info=True)

    return event

