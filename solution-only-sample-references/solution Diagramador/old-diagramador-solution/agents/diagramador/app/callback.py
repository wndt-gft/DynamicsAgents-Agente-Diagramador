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
Enhanced Callbacks for Architecture Agent with improved ADK compatibility.
Handles URL processing and GCS link management with better error handling.
"""

import re
import json
import logging
from typing import Any, Dict, List, Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.genai import types as genai_types

# Configure logger
logger = logging.getLogger(__name__)

# GCS Configuration
GCS_BUCKET_NAME = "diagram_signed_temp"
GCS_BASE_URL = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}"
GCS_BUCKET_PATH = f"gs://{GCS_BUCKET_NAME}"

# URL Patterns
HTTPS_URL_PATTERN = re.compile(
    r'https://storage\.googleapis\.com/[\w-]+/[\w_\-/]+\.xml(?:\?[^"\s]*)?'
)
GS_PATH_PATTERN = re.compile(
    r'gs://[\w-]+/[\w_\-/]+\.xml'
)

PLACEHOLDER_PATTERN = re.compile(
    r"\[?Link temporariamente indispon[ií]vel\]?|Link n[aã]o dispon[ií]vel",
    re.IGNORECASE,
)


def after_agent_callback(callback_context: CallbackContext) -> Optional[genai_types.Content]:
    """
    Enhanced after_agent_callback that properly handles ADK callback context.

    This callback ensures correct GCS URLs in agent responses and properly
    extracts content from the ADK callback context structure.

    Args:
        callback_context: ADK CallbackContext containing execution information

    Returns:
        Modified Content with corrected URLs or None to use original
    """
    try:
        logger.info("🔄 after_agent_callback iniciado - validando URLs do GCS")

        # Extract content from callback context using ADK-specific attributes
        output = None

        # Try different methods to extract content from CallbackContext
        if hasattr(callback_context, 'final_content'):
            output = callback_context.final_content
            logger.debug("✅ Extracted content from final_content")
        elif hasattr(callback_context, 'content'):
            output = callback_context.content
            logger.debug("✅ Extracted content from content attribute")
        elif hasattr(callback_context, '_invocation_context'):
            # Try to get from invocation context
            invocation_ctx = callback_context._invocation_context
            if hasattr(invocation_ctx, 'session') and hasattr(invocation_ctx.session, 'events'):
                # Get the last event with content
                for event in reversed(invocation_ctx.session.events):
                    if hasattr(event, 'content') and event.content:
                        output = event.content
                        logger.debug("✅ Extracted content from session events")
                        break

        # If we still don't have output, check state for any stored content
        if output is None and hasattr(callback_context, 'state'):
            state = callback_context.state
            if isinstance(state, dict):
                # Check for any keys that might contain output
                for key in ['last_output', 'final_output', 'agent_response', 'response']:
                    if key in state:
                        output = state[key]
                        logger.debug(f"✅ Extracted content from state['{key}']")
                        break

        if output is None:
            logger.warning("⚠️ Não foi possível extrair output do callback_context")
            logger.debug(f"CallbackContext attributes: {dir(callback_context)}")
            return None

        # Process the output based on its type
        if isinstance(output, genai_types.Content):
            sanitized_content = _sanitize_content_parts(
                output, callback_context
            )
            if sanitized_content is not None:
                return sanitized_content
              
        elif isinstance(output, str):
            # Handle string output
            processed_output = _process_string_output(output, callback_context)
            if output != processed_output:
                logger.info(f"✅ URLs corrigidas no conteúdo string")

                # Store in state
                if hasattr(callback_context, 'state'):
                    callback_context.state['processed_urls'] = True
                    callback_context.state['gcs_urls_corrected'] = True

                return genai_types.Content(parts=[genai_types.Part(text=processed_output)])

        elif isinstance(output, dict):
            # Handle dictionary output
            processed_dict = _process_dict_output(output.copy(), callback_context)
            if output != processed_dict:
                logger.info(f"✅ URLs corrigidas no conteúdo dict")

                # Store in state
                if hasattr(callback_context, 'state'):
                    callback_context.state['processed_urls'] = True
                    callback_context.state['gcs_urls_corrected'] = True

                # Convert dict to JSON string in Content
                json_str = json.dumps(processed_dict, ensure_ascii=False, indent=2)
                return genai_types.Content(parts=[genai_types.Part(text=json_str)])

        logger.debug("No URL corrections needed")
        return None

    except Exception as e:
        logger.error(f"❌ Erro no after_agent_callback: {e}", exc_info=True)
        return None


def sanitize_model_response_callback(
        callback_context: CallbackContext,
        llm_response: LlmResponse
) -> Optional[LlmResponse]:
    """Sanitize model responses immediately after LLM generation.

    This callback replaces the deprecated after-agent sanitation flow, ensuring
    that URL corrections happen between the raw LLM output and delivery to the
    user. Returning a modified ``LlmResponse`` prevents duplicate messages
    because the sanitized content replaces the original response in-place.
    """
    try:
        if not llm_response or not llm_response.content:
            return None

        sanitized_content = _sanitize_content_parts(
            llm_response.content, callback_context
        )
        if sanitized_content is None:
            return None

        return llm_response.model_copy(update={"content": sanitized_content})
    except Exception as exc:
        logger.error(
            "❌ Erro no sanitize_model_response_callback: %s", exc,
            exc_info=True
        )
        return None

def _get_last_generation_result() -> Optional[dict]:
    """Safely fetch the last generation result from app.agent without hard import at module load."""
    try:
        import importlib
        agent_mod = importlib.import_module('app.agent')
        return getattr(agent_mod, 'LAST_GENERATION_RESULT', None)
    except Exception:
        return None


def _looks_like_xml_link(value: str) -> bool:
    """Check if a string resembles a downloadable XML link."""
    if not isinstance(value, str) or not value:
        return False
    lowered = value.lower()
    if lowered.startswith(('http://', 'https://', 'gs://', 'file:///')):
        return lowered.endswith('.xml')
    return False


def _merge_candidate_links(store: Dict[str, str], candidate: Dict[str, str]) -> None:
    """Merge candidate links, allowing fresher values to override older ones."""
    for key in ('signed_url', 'gcs_blob_name', 'file_url'):
        value = candidate.get(key)
        if value:
            store[key] = value


def _extract_links_from_mapping(data: Any) -> Dict[str, str]:
    """Recursively extract potential canonical links from nested mappings."""
    found: Dict[str, str] = {}

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str) and _looks_like_xml_link(value):
                lowered_key = key.lower()
                candidate: Dict[str, str] = {}
                if value.startswith(('http://', 'https://', 'file:///')):
                    candidate['signed_url'] = value
                if value.startswith('gs://'):
                    candidate['gcs_blob_name'] = value
                if value.startswith('file:///'):
                    candidate['file_url'] = value

                if 'gcs' in lowered_key:
                    candidate.setdefault('gcs_blob_name', value)
                if 'signed' in lowered_key or 'download' in lowered_key or 'url' in lowered_key:
                    candidate.setdefault('signed_url', value)

                _merge_candidate_links(found, candidate)
            elif isinstance(value, (dict, list)):
                nested = _extract_links_from_mapping(value)
                _merge_candidate_links(found, nested)

    elif isinstance(data, list):
        for item in data:
            nested = _extract_links_from_mapping(item)
            _merge_candidate_links(found, nested)

    return found


def _collect_canonical_links(callback_context: Optional[CallbackContext]) -> Dict[str, str]:
    """Gather canonical links from last generation result and callback state."""
    canonical: Dict[str, str] = {}

    last_result = _get_last_generation_result() or {}
    if isinstance(last_result, dict):
        _merge_candidate_links(canonical, _extract_links_from_mapping(last_result))

    if callback_context and hasattr(callback_context, 'state'):
        state = getattr(callback_context, 'state', None)
        if isinstance(state, dict):
            _merge_candidate_links(canonical, _extract_links_from_mapping(state))

    return canonical


def _override_with_canonical_urls(
        text: str,
        callback_context: Optional[CallbackContext] = None
) -> str:
    """Replace any placeholders or outdated URLs with canonical links when available."""
    if not text:
        return text

    try:
        canonical_links = _collect_canonical_links(callback_context)
        canon_https = canonical_links.get('signed_url')
        canon_gs = canonical_links.get('gcs_blob_name')
        canon_file = canonical_links.get('file_url')

        replacement_https = canon_https or canon_file
        replacement_generic = replacement_https or canon_gs

        if replacement_https and PLACEHOLDER_PATTERN.search(text):
            text = PLACEHOLDER_PATTERN.sub(replacement_https, text)

        if canon_https and canon_https.endswith('.xml'):
            text = re.sub(
                r'https://storage\.googleapis\.com/[\w\-]+/[\w_\-/]+\.xml(?:\?[^"\s]*)?',
                canon_https,
                text,
            )

        if canon_gs and canon_gs.startswith('gs://') and canon_gs.endswith('.xml'):
            text = re.sub(r'gs://[\w\-]+/[\w_\-/]+\.xml', canon_gs, text)

        if replacement_generic and PLACEHOLDER_PATTERN.search(text):
            text = PLACEHOLDER_PATTERN.sub(replacement_generic, text)

        return text
    except Exception:
        return text


def _process_string_output(
        output: str,
        callback_context: Optional[CallbackContext] = None
) -> str:
    """
    Process string output to correct GCS URLs.

    Args:
        output: String containing potential URLs

    Returns:
        String with corrected URLs
    """
    if not output:
        return output

    # First, enforce canonical URLs from the latest tool run if available
    output = _override_with_canonical_urls(output, callback_context)

    corrected = output
    urls_found = []

    # Find all URLs that need correction
    for match in HTTPS_URL_PATTERN.finditer(output):
        url = match.group(0)
        if GCS_BUCKET_NAME not in url:
            urls_found.append(url)

    for match in GS_PATH_PATTERN.finditer(output):
        url = match.group(0)
        if GCS_BUCKET_NAME not in url:
            urls_found.append(url)

    # Correct each URL (bucket-fix) if needed
    for original_url in urls_found:
        corrected_url = _correct_single_url(original_url)
        if corrected_url != original_url:
            corrected = corrected.replace(original_url, corrected_url)
            logger.debug(f"  📝 URL corrigida: {corrected_url}")

    return corrected


def _process_dict_output(
        output: dict,
        callback_context: Optional[CallbackContext] = None
) -> dict:
    """
    Process dictionary output to correct GCS URLs in all string values.

    Args:
        output: Dictionary potentially containing URLs

    Returns:
        Dictionary with corrected URLs
    """
    if not output:
        return output

    for key, value in output.items():
        if isinstance(value, str):
            output[key] = _process_string_output(value, callback_context)
        elif isinstance(value, dict):
            output[key] = _process_dict_output(value, callback_context)
        elif isinstance(value, list):
            output[key] = [
                _process_string_output(item, callback_context) if isinstance(item, str)
                else _process_dict_output(item, callback_context) if isinstance(item, dict)
                else item
                for item in value
            ]

    return output


def _correct_single_url(url: str) -> str:
    """
    Correct a single GCS URL to point to the correct bucket.

    Args:
        url: URL to correct

    Returns:
        Corrected URL
    """
    if not url:
        return url

    # Extract filename from URL
    if 'storage.googleapis.com' in url:
        filename_match = re.search(r'/([^/?\s]+\.xml)', url)
        if filename_match:
            filename = filename_match.group(1)
            return f"{GCS_BASE_URL}/{filename}"
    elif url.startswith('gs://'):
        parts = url.split('/')
        filename = parts[-1] if parts else ''
        if filename.endswith('.xml'):
            return f"{GCS_BUCKET_PATH}/{filename}"

    return url


def validate_gcs_url(url: str) -> bool:
    """
    Validate if a GCS URL is correctly formatted.

    Args:
        url: URL to validate

    Returns:
        True if URL is valid and points to correct bucket
    """
    if not url:
        return False

    if url.startswith('https://'):
        return (
                'storage.googleapis.com' in url and
                GCS_BUCKET_NAME in url and
                url.endswith('.xml')
        )
    elif url.startswith('gs://'):
        return (
                GCS_BUCKET_NAME in url and
                url.endswith('.xml')
        )

    return False


def extract_urls_from_content(content: Any) -> List[str]:
    """
    Extract all GCS URLs from various content types.

    Args:
        content: Content to search for URLs

    Returns:
        List of found URLs
    """
    urls = []

    if isinstance(content, str):
        urls.extend(HTTPS_URL_PATTERN.findall(content))
        urls.extend(GS_PATH_PATTERN.findall(content))
    elif isinstance(content, dict):
        for value in content.values():
            urls.extend(extract_urls_from_content(value))
    elif isinstance(content, list):
        for item in content:
            urls.extend(extract_urls_from_content(item))
    elif isinstance(content, genai_types.Content):
        for part in content.parts:
            if hasattr(part, 'text'):
                urls.extend(extract_urls_from_content(part.text))
                
    return urls


def _sanitize_content_parts(
        content: genai_types.Content,
        callback_context: Optional[CallbackContext] = None
) -> Optional[genai_types.Content]:
    """Normalize URLs inside ``genai_types.Content`` instances."""
    if not content or not getattr(content, 'parts', None):
        return None

    processed_parts: List[genai_types.Part] = []
    modified = False

    for part in content.parts:
        if hasattr(part, 'text') and part.text:
            original_text = part.text
            processed_text = _process_string_output(original_text, callback_context)
            if original_text != processed_text:
                modified = True
                processed_parts.append(genai_types.Part(text=processed_text))
                logger.info("✅ URLs corrigidas no conteúdo")
            else:
                processed_parts.append(part)
        else:
            processed_parts.append(part)

    if not modified:
        return None

    if callback_context and hasattr(callback_context, 'state'):
        callback_context.state['processed_urls'] = True
        callback_context.state['gcs_urls_corrected'] = True

    return genai_types.Content(parts=processed_parts)


def ensure_correct_gcs_url_wrapper(callback_context: CallbackContext, *args, **kwargs) -> Optional[genai_types.Content]:
    """
    Thin wrapper maintained for backward/ADK compatibility.
    Delegates to after_agent_callback to sanitize GCS URLs in agent outputs.
    """
    try:
        return after_agent_callback(callback_context)
    except Exception as e:
        logger.error(f"❌ Erro no ensure_correct_gcs_url_wrapper: {e}", exc_info=True)
        return None


__all__ = [
    'after_agent_callback',
    'sanitize_model_response_callback',
    'validate_gcs_url',
    'extract_urls_from_content',
    'ensure_correct_gcs_url_wrapper',
]
