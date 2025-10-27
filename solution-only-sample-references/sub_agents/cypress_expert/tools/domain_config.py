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

"""Domain configuration utilities for Cypress Expert."""

from typing import Dict, Any, List


def get_domain_config(domain: str, custom_config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Get domain-specific configuration for Cypress testing.

    Args:
        domain: Business domain (e.g., 'ecommerce', 'banking', 'healthcare')
        custom_config: Optional custom configuration to merge

    Returns:
        Domain-specific configuration dictionary
    """
    custom_config = custom_config or {}

    # Default configurations per domain
    domain_configs = {
        "ecommerce": {
            "base_url": "https://shop.example.com",
            "viewport_width": 1280,
            "viewport_height": 720,
            "test_timeout": 30000,
            "page_load_timeout": 60000,
            "api_timeout": 10000,
            "retry_attempts": 2,
            "screenshot_on_failure": True,
            "video_recording": True,
            "critical_paths": ["checkout", "payment", "product_search"],
            "accessibility_level": "AA",
        },
        "banking": {
            "base_url": "https://bank.example.com",
            "viewport_width": 1920,
            "viewport_height": 1080,
            "test_timeout": 45000,
            "page_load_timeout": 90000,
            "api_timeout": 15000,
            "retry_attempts": 3,
            "screenshot_on_failure": True,
            "video_recording": True,
            "critical_paths": ["login", "transfer", "statement"],
            "accessibility_level": "AAA",
            "security_headers": True,
        },
        "healthcare": {
            "base_url": "https://health.example.com",
            "viewport_width": 1440,
            "viewport_height": 900,
            "test_timeout": 40000,
            "page_load_timeout": 75000,
            "api_timeout": 12000,
            "retry_attempts": 3,
            "screenshot_on_failure": True,
            "video_recording": True,
            "critical_paths": ["appointments", "records", "prescriptions"],
            "accessibility_level": "AAA",
            "hipaa_compliance": True,
        },
        "general": {
            "base_url": "http://localhost:3000",
            "viewport_width": 1280,
            "viewport_height": 720,
            "test_timeout": 30000,
            "page_load_timeout": 60000,
            "api_timeout": 10000,
            "retry_attempts": 2,
            "screenshot_on_failure": True,
            "video_recording": False,
            "critical_paths": ["home", "about", "contact"],
            "accessibility_level": "AA",
        },
    }

    # Get domain config or default to general
    base_config = domain_configs.get(domain.lower(), domain_configs["general"])

    # Merge with custom config
    return {**base_config, **custom_config}


def get_browser_config(browsers: List[str] = None) -> Dict[str, Any]:
    """
    Get browser-specific configuration.

    Args:
        browsers: List of browser names (default: ['chrome'])

    Returns:
        Browser configuration dictionary
    """
    browsers = browsers or ["chrome"]

    browser_configs = {
        "chrome": {
            "args": [
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
            "preferences": {
                "download.default_directory": "./cypress/downloads",
            },
        },
        "firefox": {
            "preferences": {
                "browser.download.folderList": 2,
                "browser.download.dir": "./cypress/downloads",
            },
        },
        "edge": {
            "args": [
                "--disable-dev-shm-usage",
            ],
        },
    }

    return {
        "browsers": browsers,
        "browser_configs": {
            browser: browser_configs.get(browser, {})
            for browser in browsers
        },
    }
