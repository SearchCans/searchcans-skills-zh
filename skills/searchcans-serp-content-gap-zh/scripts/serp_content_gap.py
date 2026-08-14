#!/usr/bin/env python3
"""Collect a localized SERP evidence pack for a content-gap analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from searchcans_v1 import SearchCansError, account_guard, normalize_organic, post, request_metadata


def domains(results: list[dict[str, Any]]) -> list[str]:
    return sorted({urlparse(str(result.get("url", ""))).netloc.lower() for result in results if result.get("url")})


def value(data: Any, name: str) -> Any:
    return data.get(name, []) if isinstance(data, dict) else []


def build_report(
    args: argparse.Namespace,
    budget: dict[str, Any],
    body: dict[str, Any] | None = None,
    error: str | None = None,
    status_override: str | None = None,
) -> dict[str, Any]:
    request = (
        request_metadata(body)
        if body is not None
        else {
            "status": "failed",
            "api_code": None,
            "api_message": error or "Request failed.",
            "request_id": None,
            "attempts": None,
            "retry_count": None,
        }
    )
    data = body.get("data") or {} if body is not None else {}
    organic = normalize_organic(data)
    return {
        "status": status_override or request["status"],
        "request": request,
        "account_guard": budget,
        "keyword": args.keyword,
        "market": {
            "engine": args.engine,
            "country": args.country,
            "language": args.language,
            "requested_pages": args.page,
            "effective_pages": budget.get("effective_pages", args.page),
        },
        "organic": organic,
        "competitor_domains": domains(organic),
        "people_also_ask": value(data, "peopleAlsoAsk"),
        "related_searches": value(data, "relatedSearches"),
        "knowledge_graph": data.get("knowledgeGraph") if isinstance(data, dict) else None,
        "top_stories": value(data, "topStories"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keyword")
    parser.add_argument("--engine", choices=["google", "bing"], default="google")
    parser.add_argument("--country", default="us")
    parser.add_argument("--language", default="en")
    parser.add_argument("--page", type=int, default=1, help="Fetch pages 1 through N; do not combine with a specific SERP page.")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--client-timeout", type=int, default=35)
    parser.add_argument("--retries", type=int, default=2, help="Maximum attempts for transient API or transport errors (default: 2).")
    parser.add_argument("--account-mode", choices=["auto", "off", "warn", "enforce", "cap"], default="auto", help="Account pre-flight policy. auto caps only multi-page jobs.")
    parser.add_argument("--out", type=Path, help="Write the JSON evidence pack to this file.")
    args = parser.parse_args()
    if args.page < 1:
        parser.error("--page must be at least 1")
    if args.retries < 1 or args.retries > 3:
        parser.error("--retries must be between 1 and 3")

    mode = "cap" if args.account_mode == "auto" and args.page > 1 else "off" if args.account_mode == "auto" else args.account_mode
    budget = account_guard(mode, estimated_credits=args.page, timeout_seconds=args.client_timeout)
    budget["requested_pages"] = args.page
    effective_page = args.page
    if budget["decision"] == "block":
        report = build_report(args, budget, error="Account guard blocked this job before the SERP request.", status_override="blocked")
        encoded = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            args.out.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        return 2
    if mode == "cap" and budget["budget_status"] == "insufficient":
        remaining = budget["remaining_credits"]
        effective_page = min(args.page, remaining) if isinstance(remaining, int) else 0
        if effective_page < 1:
            budget.update({"decision": "block", "effective_pages": 0, "effective_estimated_credits": 0})
            report = build_report(args, budget, error="No credits are available for a SERP page.", status_override="blocked")
            encoded = json.dumps(report, ensure_ascii=False, indent=2)
            if args.out:
                args.out.write_text(encoded + "\n", encoding="utf-8")
            print(encoded)
            return 2
        budget.update({"decision": "capped", "effective_pages": effective_page, "effective_estimated_credits": effective_page})
    else:
        budget["effective_pages"] = effective_page

    payload = {
        "t": args.engine,
        "s": args.keyword,
        "country": args.country,
        "language": args.language,
        "page": effective_page,
        "d": args.timeout_ms,
        "peopleAlsoAsk": True,
        "peopleAlsoSearchFor": True,
        "knowledgeGraph": True,
        "newsAggregation": True,
    }
    try:
        body = post("search", payload, timeout_seconds=args.client_timeout, retries=args.retries)
        report = build_report(args, budget, body=body)
        exit_code = 0
    except SearchCansError as error:
        report = build_report(args, budget, error=str(error))
        exit_code = 1
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
