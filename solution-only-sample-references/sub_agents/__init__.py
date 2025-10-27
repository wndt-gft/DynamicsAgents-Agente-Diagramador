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

"""Sub-agents package for QA automation specialized experts."""


def _safe_import(module: str, symbol: str):
    try:
        import importlib

        mod = importlib.import_module(module, package=__name__)
        return getattr(mod, symbol)
    except ModuleNotFoundError as exc:  # pragma: no cover - import guard
        if exc.name and exc.name.startswith("google"):
            return None
        raise


cypress_expert_agent = _safe_import(
    ".cypress_expert", "cypress_expert_agent"
)
karate_expert_agent = _safe_import(
    ".karate_expert", "karate_expert_agent"
)
newman_expert_agent = _safe_import(
    ".newman_expert", "newman_expert_agent"
)
playwright_expert_agent = _safe_import(
    ".playwright_expert", "playwright_expert_agent"
)

__all__ = [
    "cypress_expert_agent",
    "karate_expert_agent",
    "newman_expert_agent",
    "playwright_expert_agent"
]
