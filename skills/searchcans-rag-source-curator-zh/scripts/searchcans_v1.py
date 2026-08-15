#!/usr/bin/env python3
"""Minimal, dependency-free client for SearchCans API v1."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE = "https://www.searchcans.com/api/v1"
ACCOUNT_URL = "https://www.searchcans.com/api/user/key"
RETRYABLE_APP_CODES = {1001, 1002, 1003, 1004, 1005, 1006, 1009, 1010, 443, 10054}
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
FATAL_HTTP_CODES = {400, 401, 402, 403}
NO_RESULTS_APP_CODES = {9999, -9999}
READER_CREDITS_BY_PROXY = {0: 2, 1: 4, 2: 7, 3: 12}


class SearchCansError(RuntimeError):
    """Describe a failed SearchCans request without exposing credentials."""


def is_success_code(code: Any) -> bool:
    return code == 0 or code in NO_RESULTS_APP_CODES


def response_status(code: Any) -> str:
    if code == 0:
        return "ok"
    if code in NO_RESULTS_APP_CODES:
        return "no_results"
    return "failed"


def request_metadata(body: Mapping[str, Any]) -> dict[str, Any]:
    client = body.get("_searchcans_client", {})
    if not isinstance(client, Mapping):
        client = {}
    return {
        "status": str(client.get("status") or response_status(body.get("code"))),
        "api_code": body.get("code"),
        "api_message": body.get("msg", ""),
        "request_id": body.get("requestId") or body.get("request_id"),
        "attempts": client.get("attempts"),
        "retry_count": client.get("retry_count"),
    }


def with_request_metadata(body: dict[str, Any], attempts: int) -> dict[str, Any]:
    enriched = dict(body)
    enriched["_searchcans_client"] = {
        "status": response_status(body.get("code")),
        "attempts": attempts,
        "retry_count": attempts - 1,
    }
    return enriched


def api_key() -> str:
    key = os.environ.get("SEARCHCANS_API_KEY", "").strip()
    if not key:
        raise SearchCansError("Set SEARCHCANS_API_KEY before calling SearchCans.")
    return key


def reader_credit_cost(proxy: int) -> int:
    """Return the documented Reader credit cost for a proxy tier."""
    return READER_CREDITS_BY_PROXY[proxy]


def account_snapshot(timeout_seconds: int = 35, retries: int = 2) -> dict[str, Any]:
    """Return only account fields safe to include in a job report."""
    headers = {
        "Authorization": f"Bearer {api_key()}",
        "Content-Type": "application/json",
        "User-Agent": "searchcans-agent-skills/0.1",
    }
    last_error: Exception | None = None
    for attempt in range(retries):
        request = Request(ACCOUNT_URL, data=b"{}", headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8", errors="replace"))
        except HTTPError as error:
            if error.code in FATAL_HTTP_CODES:
                raise SearchCansError(f"Account API HTTP {error.code}") from error
            last_error = error
            if error.code not in RETRYABLE_HTTP_CODES:
                raise SearchCansError(f"Account API HTTP {error.code}") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
        else:
            if body.get("code") != 0 or not isinstance(body.get("data"), Mapping):
                raise SearchCansError(f"Account API returned code {body.get('code')}")
            data = body["data"]
            current_key = data.get("key")
            current_key_active: bool | None = None
            if isinstance(current_key, str):
                keys = data.get("keys")
                for candidate in keys if isinstance(keys, list) else []:
                    if isinstance(candidate, Mapping) and candidate.get("key") == current_key and isinstance(candidate.get("active"), bool):
                        current_key_active = candidate["active"]
                        break
            remain = data.get("remain")
            concurrent = data.get("concurrent")
            return {
                "remaining_credits": remain if isinstance(remain, int) and remain >= 0 else None,
                "concurrent_lanes": concurrent if isinstance(concurrent, int) and concurrent > 0 else None,
                "current_key_active": current_key_active,
                "attempts": attempt + 1,
            }
        if attempt < retries - 1:
            time.sleep(min(0.3 * (2**attempt), 2.0))
    raise SearchCansError("Account API unavailable") from last_error


def account_guard(mode: str, estimated_credits: int, timeout_seconds: int = 35) -> dict[str, Any]:
    """Build a sanitized pre-flight budget decision for one job."""
    guard: dict[str, Any] = {
        "mode": mode,
        "estimated_credits": estimated_credits,
        "effective_estimated_credits": estimated_credits,
        "budget_status": "not_checked",
        "decision": "proceed",
        "remaining_credits": None,
        "concurrent_lanes": None,
        "current_key_active": None,
    }
    if mode == "off":
        return guard
    try:
        snapshot = account_snapshot(timeout_seconds=timeout_seconds)
    except SearchCansError:
        guard.update({"budget_status": "unavailable", "decision": "proceed" if mode == "warn" else "block"})
        return guard

    guard.update(snapshot)
    if snapshot["current_key_active"] is False:
        guard.update({"budget_status": "key_inactive", "decision": "proceed" if mode == "warn" else "block"})
    elif snapshot["remaining_credits"] is None:
        guard.update({"budget_status": "unknown", "decision": "proceed" if mode == "warn" else "block"})
    elif snapshot["remaining_credits"] >= estimated_credits:
        guard.update({"budget_status": "sufficient", "decision": "proceed"})
    else:
        guard.update({"budget_status": "insufficient", "decision": "warn" if mode == "warn" else "cap" if mode == "cap" else "block"})
    return guard


def post(endpoint: str, payload: dict[str, Any], timeout_seconds: int = 35, retries: int = 3) -> dict[str, Any]:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json", "User-Agent": "searchcans-agent-skills/0.1"}
    last_error: Exception | None = None
    for attempt in range(retries):
        request = Request(f"{API_BASE}/{endpoint}", data=raw, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8", errors="replace"))
        except HTTPError as error:
            if error.code in FATAL_HTTP_CODES:
                raise SearchCansError(f"HTTP {error.code}: {error.read().decode('utf-8', errors='replace')[:500]}") from error
            last_error = error
            if error.code not in RETRYABLE_HTTP_CODES:
                raise SearchCansError(f"HTTP {error.code}") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
        else:
            code = body.get("code")
            if is_success_code(code):
                return with_request_metadata(body, attempt + 1)
            if isinstance(code, int) and abs(code) in RETRYABLE_APP_CODES:
                last_error = SearchCansError(f"API code {code}: {body.get('msg', '')}")
            else:
                raise SearchCansError(f"API code {code}: {body.get('msg', '')}")
        if attempt < retries - 1:
            time.sleep(min(0.3 * (2**attempt), 2.0))
    raise SearchCansError(f"Request failed after {retries} attempts: {last_error}")


def normalize_organic(data: Any) -> list[dict[str, Any]]:
    raw_results = data.get("organic", []) if isinstance(data, Mapping) else data
    if not isinstance(raw_results, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(raw_results, start=1):
        if not isinstance(item, Mapping):
            continue
        normalized.append({"position": item.get("position", index), "title": item.get("title", ""), "url": item.get("link") or item.get("url") or "", "snippet": item.get("snippet") or item.get("content") or "", "source": item.get("source", "")})
    return normalized
