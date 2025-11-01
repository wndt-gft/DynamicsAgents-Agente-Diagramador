"""Synthetic travel search tool backed by an offline catalogue.

The original sample relied on DuckDuckGo's instant answer API to retrieve
results.  External connectivity is no longer desirable, so this module now
ships a curated synthetic dataset that emulates the previous responses without
performing HTTP requests.  The tool retains the same public interface expected
by the runtime while guaranteeing deterministic behaviour in offline
environments.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from dynamic_agents import RuntimeToolError, SESSION_REGISTRY_KEY

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    description: str
    price: Optional[float] = None
    currency: Optional[str] = None
    provider: str = "synthetic_catalog"

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "title": self.title,
            "url": self.url,
            "description": self.description,
            "provider": self.provider,
        }
        if self.price is not None:
            payload["price"] = self.price
        if self.currency:
            payload["currency"] = self.currency
        return payload


class Tool:
    """Tool implementation expected by the dynamic runtime."""

    def __init__(self, metadata: Optional[Dict[str, Any]] = None):
        self.metadata = metadata or {}

    # --- tool API ------------------------------------------------------- #

    def search_hotels(
        self,
        destination: Optional[str] = None,
        check_in: Optional[str] = None,
        check_out: Optional[str] = None,
        guests: Optional[int] = None,
        max_budget: Optional[float] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = state or {}
        destination = self._coalesce_argument(
            "destination",
            destination,
            state,
            extra_paths=("travel.destination", "trip.destination", "profile.destination"),
        )
        if destination in (None, ""):
            raise RuntimeToolError("Parâmetros obrigatórios ausentes: destination")
        self._store_state_value(state, "destination", destination)
        guests = self._coalesce_argument(
            "guests",
            guests,
            state,
            extra_paths=(
                "travel.guests",
                "trip.guests",
                "profile.guests",
                "travel.passengers",
                "trip.passengers",
            ),
        )
        check_in = self._coalesce_argument(
            "check_in",
            check_in,
            state,
            extra_paths=("travel_dates.departure", "travel_dates.check_in"),
        )
        check_out = self._coalesce_argument(
            "check_out",
            check_out,
            state,
            extra_paths=("travel_dates.return", "travel_dates.check_out"),
        )
        max_budget = self._coalesce_argument(
            "max_budget",
            max_budget,
            state,
            extra_paths=("preferences.max_budget", "budget.max"),
        )
        if guests not in (None, ""):
            self._store_state_value(state, "travel.guests", guests)
        query = f"hotel {destination} best prices"
        if check_in and check_out:
            query += f" {check_in} {check_out}"
        if guests not in (None, ""):
            query += f" for {guests} guests"
        if max_budget:
            query += f" under {max_budget}"
        results, diagnostics = self._safe_search(
            query,
            limit=6,
            fallback=lambda: self._fallback_hotels(destination, max_budget),
            context={
                "destination": destination,
                "check_in": check_in,
                "check_out": check_out,
                "guests": guests,
                "max_budget": max_budget,
                "type": "hotel",
            },
        )
        payload = {
            "options": [result.to_dict() for result in results],
            "source": diagnostics.get("provider", "unknown"),
            "diagnostics": diagnostics,
        }
        self._emit_event(
            "search_completed",
            {
                "items_found": len(results),
                "provider": diagnostics.get("provider", "unknown"),
                "filters_applied": {
                    "destination": destination,
                    "check_in": check_in,
                    "check_out": check_out,
                    "guests": guests,
                    "max_budget": max_budget,
                },
                "type": "hotel",
                "diagnostics": diagnostics,
            },
            state,
        )
        return payload

    def search_flights(
        self,
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        departure_date: Optional[str] = None,
        return_date: Optional[str] = None,
        passengers: Optional[int] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = state or {}
        origin = self._coalesce_argument(
            "origin",
            origin,
            state,
            extra_paths=(
                "travel.origin",
                "trip.origin",
                "profile.origin",
                "travel.route.origin",
            ),
        )
        origin = self._normalize_location_value(origin)
        destination = self._coalesce_argument(
            "destination",
            destination,
            state,
            extra_paths=(
                "travel.destination",
                "trip.destination",
                "profile.destination",
                "travel.route.destination",
            ),
        )
        destination = self._normalize_location_value(destination)
        departure_date = self._coalesce_argument(
            "departure_date",
            departure_date,
            state,
            extra_paths=(
                "travel_dates.departure",
                "travel_dates.start",
                "travel_dates.departure_date",
            ),
        )
        return_date = self._coalesce_argument(
            "return_date",
            return_date,
            state,
            extra_paths=(
                "travel_dates.return",
                "travel_dates.end",
                "travel_dates.return_date",
            ),
        )
        passengers = self._coalesce_argument(
            "passengers",
            passengers,
            state,
            extra_paths=(
                "travel.passengers",
                "trip.passengers",
                "profile.passengers",
            ),
        )
        missing = [
            key
            for key, value in (("origin", origin), ("destination", destination))
            if value in (None, "")
        ]
        if missing:
            inferred = self._infer_flight_context(state)
            if origin in (None, ""):
                origin = self._normalize_location_value(inferred.get("origin", origin))
            if destination in (None, ""):
                destination = self._normalize_location_value(
                    inferred.get("destination", destination)
                )
            if departure_date in (None, ""):
                departure_date = inferred.get("departure_date", departure_date)
            if return_date in (None, ""):
                return_date = inferred.get("return_date", return_date)
            origin = self._normalize_location_value(origin)
            destination = self._normalize_location_value(destination)
            missing = [
                key
                for key, value in (("origin", origin), ("destination", destination))
                if value in (None, "")
            ]
        if missing:
            raise RuntimeToolError("Parâmetros obrigatórios ausentes: " + ", ".join(sorted(missing)))
        self._store_state_value(state, "origin", origin)
        self._store_state_value(state, "destination", destination)
        if departure_date not in (None, ""):
            self._store_state_value(state, "travel_dates.departure", departure_date)
        if return_date not in (None, ""):
            self._store_state_value(state, "travel_dates.return", return_date)
        if passengers not in (None, ""):
            self._store_state_value(state, "travel.passengers", passengers)
        query = f"flight {origin} to {destination}"
        if departure_date:
            query += f" {departure_date}"
        if return_date:
            query += f" return {return_date}"
        results, diagnostics = self._safe_search(
            query,
            limit=6,
            fallback=lambda: self._fallback_flights(origin, destination),
            context={
                "origin": origin,
                "destination": destination,
                "departure_date": departure_date,
                "return_date": return_date,
                "type": "flight",
            },
        )
        payload = {
            "itineraries": [result.to_dict() for result in results],
            "source": diagnostics.get("provider", "unknown"),
            "diagnostics": diagnostics,
        }
        self._emit_event(
            "search_completed",
            {
                "items_found": len(results),
                "provider": diagnostics.get("provider", "unknown"),
                "filters_applied": {
                    "origin": origin,
                    "destination": destination,
                    "departure_date": departure_date,
                    "return_date": return_date,
                },
                "type": "flight",
                "diagnostics": diagnostics,
            },
            state,
        )
        return payload

    def search_experiences(
        self,
        destination: Optional[str] = None,
        interests: Optional[List[str]] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        state = state or {}
        destination = self._coalesce_argument(
            "destination",
            destination,
            state,
            extra_paths=("travel.destination", "trip.destination", "profile.destination"),
        )
        if destination in (None, ""):
            raise RuntimeToolError("Parâmetros obrigatórios ausentes: destination")
        self._store_state_value(state, "destination", destination)
        if interests is None or not interests:
            resolved = self._coalesce_argument(
                "interests",
                interests,
                state,
                extra_paths=("preferences.interests",),
            )
            if isinstance(resolved, list):
                interests = resolved
            elif resolved not in (None, ""):
                interests = [resolved]
        interests_fragment = " ".join(interests or [])
        query = f"tour {destination} activities {interests_fragment}".strip()
        results, diagnostics = self._safe_search(
            query,
            limit=8,
            fallback=lambda: self._fallback_experiences(destination, interests or []),
            context={
                "destination": destination,
                "interests": interests,
                "type": "experience",
            },
        )
        payload = {
            "activities": [result.to_dict() for result in results],
            "source": diagnostics.get("provider", "unknown"),
            "diagnostics": diagnostics,
        }
        self._emit_event(
            "search_completed",
            {
                "items_found": len(results),
                "provider": diagnostics.get("provider", "unknown"),
                "filters_applied": {
                    "destination": destination,
                    "interests": interests,
                },
                "type": "experience",
                "diagnostics": diagnostics,
            },
            state,
        )
        return payload

    # --- internal helpers ---------------------------------------------- #

    def _infer_flight_context(self, state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Derive missing flight arguments from conversational context."""

        if not isinstance(state, dict):
            return {}

        candidates: List[str] = []
        for view in self._state_views(state):
            specialists = view.get("specialists")
            if isinstance(specialists, dict):
                for details in specialists.values():
                    if not isinstance(details, dict):
                        continue
                    inputs = details.get("inputs")
                    if isinstance(inputs, dict):
                        for field in ("request", "prompt", "message"):
                            value = inputs.get(field)
                            if isinstance(value, str) and value.strip():
                                candidates.append(value)
                    prompt = details.get("prompt")
                    if isinstance(prompt, str) and prompt.strip():
                        candidates.append(prompt)
            transcript = view.get("transcript")
            if isinstance(transcript, list):
                for entry in reversed(transcript):
                    if not isinstance(entry, dict):
                        continue
                    payload = entry.get("payload")
                    if isinstance(payload, dict):
                        text = payload.get("text") or payload.get("response")
                        if isinstance(text, str) and text.strip():
                            candidates.append(text)
                        content = payload.get("content")
                        if isinstance(content, dict):
                            parts = content.get("parts")
                            if isinstance(parts, list):
                                for part in parts:
                                    if isinstance(part, dict):
                                        part_text = part.get("text") or part.get("response")
                                        if isinstance(part_text, str) and part_text.strip():
                                            candidates.append(part_text)

        extracted: Dict[str, Any] = {}
        for text in candidates:
            parsed = self._parse_flight_details(text)
            for key, value in parsed.items():
                if key not in extracted and value not in (None, ""):
                    extracted[key] = value
            if {"origin", "destination"}.issubset(extracted):
                break

        if extracted.get("origin"):
            self._store_state_value(state, "origin", extracted["origin"])
        if extracted.get("destination"):
            self._store_state_value(state, "destination", extracted["destination"])
        if extracted.get("departure_date"):
            self._store_state_value(state, "travel_dates.departure", extracted["departure_date"])
        if extracted.get("return_date"):
            self._store_state_value(state, "travel_dates.return", extracted["return_date"])

        return extracted

    def _parse_flight_details(self, text: str) -> Dict[str, str]:
        """Extract flight route and date hints from free-form text."""

        if not isinstance(text, str) or not text:
            return {}

        cleaned = " ".join(text.strip().split())
        origin_token = self._extract_location(
            cleaned,
            prefix=r"(?:saindo|partindo|de|from)(?:\s+(?:de|da|do|desde))?\s+",
        )
        destination_token = self._extract_location(
            cleaned,
            prefix=r"(?:para|até|to)\s+",
        )
        range_match = re.search(
            r"(?:de|do dia)\s+(?:dia\s+)?(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+(?:a|ao|até)\s+(?:o\s+)?(?:dia\s+)?(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
            cleaned,
            flags=re.IGNORECASE,
        )
        labeled_range_match = re.search(
            r"(?:datas?|período)\s*[:\-]\s*(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+(?:a|até|ao)\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
            cleaned,
            flags=re.IGNORECASE,
        )
        between_match = re.search(
            r"entre\s+(?:o\s+)?(?:dia\s+)?(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+(?:e|até|ao)\s+(?:o\s+)?(?:dia\s+)?(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
            cleaned,
            flags=re.IGNORECASE,
        )
        departure_match = re.search(
            r"(?:ida|partida)\s+(?:no\s+)?(?:dia\s+)?(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
            cleaned,
            flags=re.IGNORECASE,
        )
        return_match = re.search(
            r"(?:volta|retorno)\s+(?:no\s+)?(?:dia\s+)?(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
            cleaned,
            flags=re.IGNORECASE,
        )

        details: Dict[str, str] = {}
        if origin_token:
            details["origin"] = origin_token
        if destination_token:
            details["destination"] = destination_token
        if range_match:
            details["departure_date"] = range_match.group(1)
            details["return_date"] = range_match.group(2)
        if labeled_range_match:
            details.setdefault("departure_date", labeled_range_match.group(1))
            details.setdefault("return_date", labeled_range_match.group(2))
        if between_match:
            details.setdefault("departure_date", between_match.group(1))
            details.setdefault("return_date", between_match.group(2))
        if departure_match and "departure_date" not in details:
            details["departure_date"] = departure_match.group(1)
        if return_match and "return_date" not in details:
            details["return_date"] = return_match.group(1)

        bullet_lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in bullet_lines:
            normalized = line.lower()
            origin_label = re.match(
                r"^[\-*•]?\s*(?:\*\*)?(origem|sa[ií]da|partida)(?:\*\*)?\s*[:\-]\s*(.+)$",
                line,
                flags=re.IGNORECASE,
            )
            if origin_label and "origin" not in details:
                details["origin"] = self._clean_location(origin_label.group(2))
            destination_label = re.match(
                r"^[\-*•]?\s*(?:\*\*)?(destino|chegada)(?:\*\*)?\s*[:\-]\s*(.+)$",
                line,
                flags=re.IGNORECASE,
            )
            if destination_label and "destination" not in details:
                details["destination"] = self._clean_location(destination_label.group(2))

            if re.search(r"\bida\b", normalized, flags=re.IGNORECASE):
                ida_label = re.match(
                    r"^[\-*•]?\s*(?:\*\*)?ida(?:\*\*)?\s*[:\-]\s*(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
                    line,
                    flags=re.IGNORECASE,
                )
                if ida_label:
                    details.setdefault("departure_date", ida_label.group(1))
            if re.search(r"\b(volta|retorno)\b", normalized, flags=re.IGNORECASE):
                volta_label = re.match(
                    r"^[\-*•]?\s*(?:\*\*)?(volta|retorno)(?:\*\*)?\s*[:\-]\s*(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
                    line,
                    flags=re.IGNORECASE,
                )
                if volta_label:
                    details.setdefault("return_date", volta_label.group(2))

            if re.search(r"\bdatas?\b|per[ií]odo", normalized, flags=re.IGNORECASE):
                labeled_range = re.search(
                    r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+(?:a|até|ao)\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
                    line,
                    flags=re.IGNORECASE,
                )
                if labeled_range:
                    details.setdefault("departure_date", labeled_range.group(1))
                    details.setdefault("return_date", labeled_range.group(2))

        return details

    @staticmethod
    def _clean_location(value: str) -> str:
        value = value.strip()
        value = re.sub(r"^[*_`]+", "", value)
        value = re.sub(r"[*_`]+$", "", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip(",.;: ")

    def _normalize_location_value(self, value: Optional[Any]) -> Optional[str]:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            cleaned = self._clean_location(value)
            return cleaned or None
        if isinstance(value, dict):
            priority_keys = (
                "code",
                "iata",
                "iata_code",
                "airport_code",
                "value",
                "name",
                "city",
                "label",
                "text",
            )
            for key in priority_keys:
                candidate = value.get(key)
                normalized = self._normalize_location_value(candidate)
                if normalized:
                    return normalized
            for candidate in value.values():
                normalized = self._normalize_location_value(candidate)
                if normalized:
                    return normalized
            return None
        if isinstance(value, (list, tuple)):
            for item in value:
                normalized = self._normalize_location_value(item)
                if normalized:
                    return normalized
            return None
        if isinstance(value, (int, float)):
            return str(value)
        cleaned = self._clean_location(str(value))
        return cleaned or None

    def _extract_location(self, text: str, *, prefix: str) -> Optional[str]:
        pattern = prefix + r"([A-Za-zÀ-ÿ'\-\s/()]+?)(?=(?:\s+(?:para|até|entre|com|do|da|no|na|em|por|de)\b|[,.]|$))"
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            candidate = self._clean_location(match.group(1))
            lowered = candidate.lower()
            if any(
                word in lowered
                for word in ("pessoa", "passageir", "adult", "crian", "voo", "voos", "passagem", "passagens")
            ):
                continue
            if not candidate:
                continue
            return candidate
        return None

    def _coalesce_argument(
        self,
        name: str,
        explicit: Optional[Any],
        state: Optional[Dict[str, Any]],
        *,
        extra_paths: tuple[str, ...] = (),
    ) -> Optional[Any]:
        if explicit not in (None, ""):
            return explicit
        state = state or {}
        for path in self._candidate_paths(name, extra_paths):
            value = self._lookup_state_path(state, path)
            if value not in (None, ""):
                return value
        for view in self._state_views(state):
            specialists = view.get("specialists")
            if not isinstance(specialists, dict):
                continue
            for details in specialists.values():
                if not isinstance(details, dict):
                    continue
                inputs = details.get("inputs")
                if isinstance(inputs, dict) and inputs.get(name) not in (None, ""):
                    return inputs[name]
                result = details.get("result")
                if isinstance(result, dict) and result.get(name) not in (None, ""):
                    return result[name]
        return explicit

    @staticmethod
    def _candidate_paths(name: str, extra_paths: tuple[str, ...]) -> List[str]:
        prefixes = ["", "profile", "preferences", "travel", "travel_details", "trip", "itinerary", "context"]
        paths: List[str] = []
        for prefix in prefixes:
            if prefix:
                paths.append(f"{prefix}.{name}")
            else:
                paths.append(name)
        paths.extend(list(extra_paths))
        seen = set()
        ordered: List[str] = []
        for path in paths:
            if path not in seen:
                ordered.append(path)
                seen.add(path)
        return ordered

    @staticmethod
    def _state_views(state: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not isinstance(state, dict):
            return []
        views: List[Dict[str, Any]] = [state]
        registry = state.get(SESSION_REGISTRY_KEY)
        if isinstance(registry, dict):
            for entry in registry.values():
                if isinstance(entry, dict):
                    views.append(entry)
        return views

    @classmethod
    def _lookup_state_path(cls, state: Dict[str, Any], path: str) -> Optional[Any]:
        if not path:
            return None
        for view in cls._state_views(state):
            current: Any = view
            for part in path.split('.'):
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(part)
                if current is None:
                    break
            if current not in (None, ""):
                return current
        return None

    @classmethod
    def _store_state_value(cls, state: Dict[str, Any], path: str, value: Any) -> None:
        if not isinstance(state, dict) or value in (None, ""):
            return

        def _assign(target: Dict[str, Any]) -> None:
            parts = path.split('.')
            current = target
            for part in parts[:-1]:
                next_value = current.get(part)
                if not isinstance(next_value, dict):
                    next_value = {}
                    current[part] = next_value
                current = next_value
            leaf = parts[-1]
            existing = current.get(leaf)
            if existing in (None, "") or leaf not in current:
                current[leaf] = value
                return
            if isinstance(value, str) and existing != value:
                current[leaf] = value

        for view in cls._state_views(state):
            _assign(view)

    def _safe_search(
        self,
        query: str,
        *,
        limit: int,
        fallback: Callable[[], List[SearchResult]],
        context: Dict[str, Any],
    ) -> tuple[List[SearchResult], Dict[str, Any]]:
        diagnostics = dict(context)
        diagnostics["query"] = query
        results = self._synthetic_search(limit=limit, context=context)
        if len(results) < limit:
            fallback_results = fallback() or []
            if fallback_results:
                diagnostics["fallback_used"] = True
            for item in fallback_results:
                if len(results) >= limit:
                    break
                results.append(item)
        if results:
            diagnostics["provider"] = results[0].provider
        else:
            diagnostics["provider"] = "synthetic_catalog"
        diagnostics["items_found"] = len(results)
        return results[:limit], diagnostics

    def _synthetic_search(self, *, limit: int, context: Dict[str, Any]) -> List[SearchResult]:
        search_type = context.get("type")
        if search_type == "hotel":
            destination = self._normalize_location_value(context.get("destination"))
            return self._generate_hotel_catalog(
                destination,
                context.get("max_budget"),
                limit,
            )
        if search_type == "flight":
            origin = self._normalize_location_value(context.get("origin"))
            destination = self._normalize_location_value(context.get("destination"))
            return self._generate_flight_catalog(
                origin,
                destination,
                context.get("departure_date"),
                context.get("return_date"),
                limit,
            )
        if search_type == "experience":
            destination = self._normalize_location_value(context.get("destination"))
            interests = self._normalize_interests(context.get("interests"))
            return self._generate_experience_catalog(destination, interests, limit)
        return []

    def _generate_hotel_catalog(
        self,
        destination: Optional[str],
        max_budget: Optional[Any],
        limit: int,
    ) -> List[SearchResult]:
        if not destination:
            return []
        baseline = self._resolve_budget_hint(max_budget)
        templates = [
            ("Historic Residence", "historic", 0.85, "Heritage property in {city} with daily breakfast."),
            ("City Lights Hotel", "city", 1.0, "Modern stay in the cultural heart of {city}."),
            ("Riverside Retreat", "riverside", 1.18, "Resort experience by the main river in {city}."),
            ("Creative Hub Lofts", "creative", 0.72, "Boutique lofts surrounded by arts venues in {city}."),
        ]
        results: List[SearchResult] = []
        for label, slug, factor, description in templates:
            price = round(baseline * factor, 2)
            results.append(
                SearchResult(
                    title=f"{destination} {label}",
                    url=f"https://example.com/hotel/{slug}",
                    description=description.format(city=destination),
                    price=price,
                    currency="USD",
                    provider="synthetic_catalog",
                )
            )
            if len(results) >= limit:
                break
        return results[:limit]

    def _generate_flight_catalog(
        self,
        origin: Optional[str],
        destination: Optional[str],
        departure_date: Optional[str],
        return_date: Optional[str],
        limit: int,
    ) -> List[SearchResult]:
        if not origin or not destination:
            return []
        base_price = self._estimate_flight_price(origin, destination)
        segments = [
            (
                "Non-stop",
                "direct",
                1.0,
                "Non-stop service from {origin} to {destination} with included meals.",
            ),
            (
                "One-stop via Hub",
                "one-stop",
                0.82,
                "Single connection itinerary with under 2h layover.",
            ),
            (
                "Overnight Saver",
                "overnight",
                0.68,
                "Red-eye flight designed to maximise daylight at destination.",
            ),
        ]
        results: List[SearchResult] = []
        for label, slug, factor, description in segments:
            price = round(base_price * factor, 2)
            descriptor = description.format(origin=origin.upper(), destination=destination.upper())
            if departure_date and return_date:
                descriptor += f" Travel window: {departure_date} - {return_date}."
            results.append(
                SearchResult(
                    title=f"{origin.upper()} -> {destination.upper()} {label}",
                    url=f"https://example.com/flight/{slug}",
                    description=descriptor,
                    price=price,
                    currency="USD",
                    provider="synthetic_catalog",
                )
            )
            if len(results) >= limit:
                break
        return results[:limit]

    def _generate_experience_catalog(
        self,
        destination: Optional[str],
        interests: List[str],
        limit: int,
    ) -> List[SearchResult]:
        if not destination:
            return []
        summary = ", ".join(interests) if interests else "local highlights"
        templates = [
            (
                "Guided Heritage Walk",
                "heritage",
                f"Walking tour covering the historic districts of {destination}.",
            ),
            (
                "Signature Food Experience",
                "food",
                f"Curated tasting menu inspired by {summary} in {destination}.",
            ),
            (
                "Evening Cultural Showcase",
                "culture",
                f"Immersive performance featuring the traditions of {destination}.",
            ),
        ]
        results: List[SearchResult] = []
        for label, slug, description in templates:
            results.append(
                SearchResult(
                    title=f"{destination} {label}",
                    url=f"https://example.com/experience/{slug}",
                    description=description,
                    provider="synthetic_catalog",
                )
            )
            if len(results) >= limit:
                break
        return results[:limit]

    @staticmethod
    def _resolve_budget_hint(max_budget: Optional[Any]) -> float:
        try:
            if max_budget in (None, ""):
                raise ValueError
            value = float(max_budget)
            if value <= 0:
                raise ValueError
            return max(value, 140.0)
        except (TypeError, ValueError):
            return 220.0

    @staticmethod
    def _estimate_flight_price(origin: str, destination: str) -> float:
        token = f"{origin.upper()}-{destination.upper()}"
        hash_basis = sum(ord(ch) for ch in token)
        baseline = 520 + (hash_basis % 120)
        return float(baseline)

    @staticmethod
    def _normalize_interests(interests: Any) -> List[str]:
        if isinstance(interests, (list, tuple, set)):
            values = [str(item).strip() for item in interests if str(item).strip()]
            return [value for value in values if value]
        if isinstance(interests, str) and interests.strip():
            return [interests.strip()]
        return []

    @staticmethod
    def _emit_event(event: str, payload: Dict[str, Any], state: Optional[Dict[str, Any]]) -> None:
        if state is None:
            return
        state.setdefault("_events", []).append({"name": event, "payload": payload})

    @staticmethod
    def _fallback_hotels(destination: str, max_budget: Optional[float]) -> List[SearchResult]:
        try:
            base_price = float(max_budget) if max_budget is not None else 220.0
        except (TypeError, ValueError):
            base_price = 220.0
        options = [
            (
                f"{destination} Boutique Stay",
                "boutique",
                0.88,
                f"Elegant boutique hotel in {destination} with breakfast included.",
            ),
            (
                f"{destination} Riverside Resort",
                "resort",
                1.18,
                f"Resort experience in {destination} with spa access.",
            ),
            (
                f"{destination} Business Tower",
                "business",
                1.05,
                f"Business district hotel in {destination} with executive lounge access.",
            ),
            (
                f"{destination} Creative Studios",
                "studios",
                0.74,
                f"Art-inspired studios perfect for extended stays in {destination}.",
            ),
        ]
        results: List[SearchResult] = []
        for title, slug, factor, description in options:
            results.append(
                SearchResult(
                    title=title,
                    url=f"https://example.com/hotel/{slug}",
                    description=description,
                    price=round(base_price * factor, 2),
                    currency="USD",
                    provider="synthetic_catalog",
                )
            )
        return results

    @staticmethod
    def _fallback_flights(origin: str, destination: str) -> List[SearchResult]:
        return [
            SearchResult(
                title=f"{origin.upper()} -> {destination.upper()} Direct",
                url="https://example.com/flight/direct",
                description="Non-stop flight with 2x23kg baggage allowance.",
                price=680.0,
                currency="USD",
                provider="synthetic_catalog",
            ),
            SearchResult(
                title=f"{origin.upper()} -> {destination.upper()} One-stop",
                url="https://example.com/flight/onestop",
                description="Single connection with layover under 2 hours.",
                price=520.0,
                currency="USD",
                provider="synthetic_catalog",
            ),
            SearchResult(
                title=f"{origin.upper()} -> {destination.upper()} Explorer",
                url="https://example.com/flight/explorer",
                description="Two-stop itinerary prioritising lower fares.",
                price=450.0,
                currency="USD",
                provider="synthetic_catalog",
            ),
        ]

    @staticmethod
    def _fallback_experiences(destination: str, interests: List[str]) -> List[SearchResult]:
        summary = ", ".join(interests) if interests else "destaques locais"
        return [
            SearchResult(
                title=f"Tour guiado por {destination}",
                url="https://example.com/tour/guided",
                description=f"Passeio a pe por {destination} cobrindo os principais pontos historicos.",
                provider="synthetic_catalog",
            ),
            SearchResult(
                title=f"Experiencia gastronomica em {destination}",
                url="https://example.com/tour/food",
                description=f"Degustacao de pratos regionais focada em {summary}.",
                provider="synthetic_catalog",
            ),
            SearchResult(
                title=f"Noite cultural em {destination}",
                url="https://example.com/tour/culture",
                description=f"Espetaculo noturno celebrando artistas locais de {destination}.",
                provider="synthetic_catalog",
            ),
        ]
