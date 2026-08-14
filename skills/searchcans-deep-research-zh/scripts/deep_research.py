#!/usr/bin/env python3
"""Build a bounded SearchCans search-and-read research bundle."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from searchcans_v1 import SearchCansError, account_guard, normalize_organic, post, reader_credit_cost


def is_http_url(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"} and bool(urlparse(value).netloc)


def select_sources(results: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    """Prefer diverse domains while keeping the SERP order inside each domain."""
    by_domain: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for result in results:
        if not is_http_url(str(result.get("url", ""))):
            continue
        domain = urlparse(str(result["url"])).netloc.lower()
        by_domain.setdefault(domain, []).append(result)

    chosen: list[dict[str, Any]] = []
    while by_domain and len(chosen) < maximum:
        for domain in list(by_domain):
            chosen.append(by_domain[domain].pop(0))
            if not by_domain[domain]:
                del by_domain[domain]
            if len(chosen) == maximum:
                break
    return chosen


def evidence_gate(sources: list[dict[str, Any]]) -> dict[str, Any]:
    eligible_urls = [source["url"] for source in sources if source.get("claim_ready")]
    ineligible_sources = [
        {"url": source.get("url", ""), "status": source.get("status", "unknown")}
        for source in sources
        if not source.get("claim_ready")
    ]
    return {
        "claim_eligible_urls": eligible_urls,
        "ineligible_sources": ineligible_sources,
        "rule": "Cite only claim_eligible_urls for consequential claims; SERP snippets are leads, not evidence.",
    }


def bounded_map(items: list[Any], worker: Any, max_workers: int) -> list[Any]:
    """Run independent API calls without exceeding the selected lane limit."""
    if max_workers == 1:
        return [worker(item) for item in items]
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(worker, items))


def resolve_workers(value: str, budget: dict[str, Any]) -> int:
    if value == "auto":
        lanes = budget.get("concurrent_lanes")
        return lanes if isinstance(lanes, int) and lanes > 0 else 1
    try:
        requested = int(value)
    except ValueError as error:
        raise ValueError("--max-concurrency must be auto or a positive integer") from error
    if requested < 1:
        raise ValueError("--max-concurrency must be auto or a positive integer")
    lanes = budget.get("concurrent_lanes")
    return min(requested, lanes) if isinstance(lanes, int) and lanes > 0 else requested


def cap_sources_for_budget(remaining_credits: int, search_credits: int, reader_credits: int, requested_sources: int) -> int | None:
    """Return a budget-safe Reader source count, or None when searches cannot start."""
    if remaining_credits < search_credits:
        return None
    return min(requested_sources, (remaining_credits - search_credits) // reader_credits)


def blocked_bundle(question: str, queries: list[str], subquestions: list[str], budget: dict[str, Any], limits: dict[str, int]) -> dict[str, Any]:
    return {
        "status": "blocked",
        "question": question,
        "research_plan": subquestions,
        "queries": queries,
        "searches": [],
        "sources": [],
        "evidence_gate": evidence_gate([]),
        "limits": limits,
        "account_guard": budget,
    }


def search(query: str, args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "t": args.engine,
        "s": query,
        "d": args.timeout_ms,
        "country": args.country,
        "language": args.language,
        "peopleAlsoAsk": True,
        "knowledgeGraph": True,
        "newsAggregation": True,
    }
    body = post("search", payload, timeout_seconds=args.client_timeout)
    data = body.get("data") or {}
    return {
        "query": query,
        "organic": normalize_organic(data),
        "peopleAlsoAsk": data.get("peopleAlsoAsk", []) if isinstance(data, dict) else [],
        "relatedSearches": data.get("relatedSearches", []) if isinstance(data, dict) else [],
    }


def read(source: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {"t": "url", "s": source["url"], "d": args.timeout_ms, "proxy": args.proxy}
    if args.headless:
        payload.update({"mode": 1, "w": args.wait_ms})
    try:
        body = post("url", payload, timeout_seconds=args.client_timeout)
        data = body.get("data") or {}
        return {
            "url": source["url"],
            "serp_title": source.get("title", ""),
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "markdown": data.get("markdown", ""),
            "status": "ok" if data.get("markdown") else "empty",
            "claim_ready": bool(data.get("markdown")),
        }
    except SearchCansError as error:
        return {"url": source["url"], "serp_title": source.get("title", ""), "status": "error", "claim_ready": False, "error": str(error)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--subquestion", action="append", default=[], help="Research question to investigate; supply 3–5 before searching.")
    parser.add_argument("--query", action="append", default=[], help="Additional search query; repeat for a query matrix.")
    parser.add_argument("--engine", choices=["google", "bing"], default="google")
    parser.add_argument("--country", default="us")
    parser.add_argument("--language", default="en")
    parser.add_argument("--max-results-per-query", type=int, default=5)
    parser.add_argument("--max-sources", type=int, default=5)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--wait-ms", type=int, default=3000)
    parser.add_argument("--proxy", type=int, choices=range(4), default=0)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--client-timeout", type=int, default=35)
    parser.add_argument("--account-mode", choices=["auto", "off", "warn", "enforce", "cap"], default="auto", help="Account pre-flight policy. auto caps source reads to the available budget.")
    parser.add_argument("--max-concurrency", default="auto", help="Maximum simultaneous API calls, or auto to use the account lane count.")
    parser.add_argument("--out", type=Path, help="Write the complete JSON bundle to this file.")
    args = parser.parse_args()
    if args.max_results_per_query < 1 or args.max_sources < 1:
        parser.error("--max-results-per-query and --max-sources must be positive")
    if not 3 <= len(args.subquestion) <= 5:
        parser.error("Provide 3–5 --subquestion values to create a traceable research plan.")

    queries = list(dict.fromkeys([*args.subquestion, *args.query]))
    mode = "cap" if args.account_mode == "auto" else args.account_mode
    search_credits = len(queries)
    reader_credits = reader_credit_cost(args.proxy)
    budget = account_guard(mode, estimated_credits=search_credits + args.max_sources * reader_credits, timeout_seconds=args.client_timeout)
    budget.update({"requested_max_sources": args.max_sources, "search_credits": search_credits, "reader_credits_per_source": reader_credits})
    effective_max_sources = args.max_sources
    limits = {"max_results_per_query": args.max_results_per_query, "requested_max_sources": args.max_sources, "effective_max_sources": effective_max_sources}

    if budget["decision"] == "block":
        bundle = blocked_bundle(args.question, queries, args.subquestion, budget, limits)
        encoded = json.dumps(bundle, ensure_ascii=False, indent=2)
        if args.out:
            args.out.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        return 2
    if mode == "cap" and budget["budget_status"] == "insufficient":
        remaining = budget["remaining_credits"]
        effective_max_sources = cap_sources_for_budget(remaining, search_credits, reader_credits, args.max_sources) if isinstance(remaining, int) else None
        if effective_max_sources is None:
            budget.update({"decision": "block", "effective_estimated_credits": 0})
            bundle = blocked_bundle(args.question, queries, args.subquestion, budget, limits)
            encoded = json.dumps(bundle, ensure_ascii=False, indent=2)
            if args.out:
                args.out.write_text(encoded + "\n", encoding="utf-8")
            print(encoded)
            return 2
        budget.update({"decision": "capped", "effective_estimated_credits": search_credits + effective_max_sources * reader_credits})

    try:
        workers = resolve_workers(args.max_concurrency, budget)
    except ValueError as error:
        parser.error(str(error))
    budget["effective_concurrency"] = workers
    limits["effective_max_sources"] = effective_max_sources

    searches = bounded_map(queries, lambda query: search(query, args), workers)
    all_results = [result for search_result in searches for result in search_result["organic"][: args.max_results_per_query]]
    selected_sources = select_sources(all_results, effective_max_sources)
    sources = bounded_map(selected_sources, lambda source: read(source, args), workers)
    bundle = {
        "status": "capped" if budget["decision"] == "capped" else "ok",
        "question": args.question,
        "research_plan": args.subquestion,
        "queries": queries,
        "searches": searches,
        "sources": sources,
        "evidence_gate": evidence_gate(sources),
        "limits": limits,
        "account_guard": budget,
    }
    encoded = json.dumps(bundle, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(encoded + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": bundle["status"],
                    "question": args.question,
                    "queries": queries,
                    "source_count": len(bundle["sources"]),
                    "claim_eligible_source_count": len(bundle["evidence_gate"]["claim_eligible_urls"]),
                    "effective_concurrency": workers,
                    "output": str(args.out),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
