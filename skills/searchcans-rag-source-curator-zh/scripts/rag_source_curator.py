#!/usr/bin/env python3
"""Find, diversify, and fetch a bounded set of Reader-ready RAG sources."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from searchcans_v1 import SearchCansError, account_guard, normalize_organic, post, reader_credit_cost, request_metadata


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def canonical_url(value: str) -> str:
    parsed = urlparse(value)
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.params, parsed.query, ""))


def parallel_map(items: list[Any], worker: Any, workers: int) -> list[Any]:
    if workers == 1:
        return [worker(item) for item in items]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(worker, items))


def resolve_workers(value: str, budget: dict[str, Any]) -> int:
    if value == "auto":
        lanes = budget.get("concurrent_lanes")
        return lanes if isinstance(lanes, int) and lanes > 0 else 1
    try:
        workers = int(value)
    except ValueError as error:
        raise ValueError("--max-concurrency must be auto or a positive integer") from error
    if workers < 1:
        raise ValueError("--max-concurrency must be auto or a positive integer")
    lanes = budget.get("concurrent_lanes")
    return min(workers, lanes) if isinstance(lanes, int) and lanes > 0 else workers


def cap_sources(remaining: int, search_credits: int, reader_cost: int, requested: int) -> int | None:
    if remaining < search_credits:
        return None
    return min(requested, (remaining - search_credits) // reader_cost)


def search(query: str, args: argparse.Namespace) -> dict[str, Any]:
    body = post("search", {"t": args.engine, "s": query, "country": args.country, "language": args.language, "d": args.timeout_ms}, timeout_seconds=args.client_timeout, retries=args.retries)
    return {"query": query, "request": request_metadata(body), "organic": normalize_organic(body.get("data") or {})[: args.max_candidates]}


def select_sources(searches: list[dict[str, Any]], file_urls: list[str], maximum: int) -> list[dict[str, Any]]:
    """Keep explicit file inputs, deduplicate URLs, then round-robin search domains."""
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    for url in file_urls:
        key = canonical_url(url)
        if key not in seen and len(chosen) < maximum:
            seen.add(key)
            chosen.append({"url": url, "kind": "file", "discovery": "explicit"})
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for search_result in searches:
        for item in search_result["organic"]:
            url = str(item.get("url", ""))
            key = canonical_url(url) if valid_url(url) else ""
            if not key or key in seen:
                continue
            source = {"url": url, "kind": "web", "discovery": "serp", "query": search_result["query"], "serp_title": item.get("title", ""), "serp_position": item.get("position")}
            grouped.setdefault(urlparse(url).netloc.lower(), []).append(source)
            seen.add(key)
    while grouped and len(chosen) < maximum:
        for domain in list(grouped):
            chosen.append(grouped[domain].pop(0))
            if not grouped[domain]:
                del grouped[domain]
            if len(chosen) == maximum:
                break
    return chosen


def fetch(source: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {"t": "url", "s": source["url"], "proxy": args.proxy, "d": args.timeout_ms}
    if source["kind"] == "file":
        payload["file"] = 1
    if args.headless and source["kind"] == "web":
        payload.update({"mode": 1, "w": args.wait_ms})
    if args.screenshot and source["kind"] == "web":
        payload["image"] = args.screenshot
    try:
        body = post("url", payload, timeout_seconds=args.client_timeout, retries=args.retries)
        data = body.get("data") or {}
        content = data.get("fileMarkdown") if source["kind"] == "file" else data.get("markdown")
        entry = {
            **source,
            "status": "ok" if content else "empty",
            "claim_ready": bool(content),
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "content_length": len(content or ""),
            "image_url": data.get("imageUrl"),
            "authority_assessment": "unassessed",
            "request": request_metadata(body),
        }
        if args.include_content:
            entry["content"] = content or ""
        return entry
    except SearchCansError as error:
        return {**source, "status": "error", "claim_ready": False, "authority_assessment": "unassessed", "error": str(error)}


def write_output(bundle: dict[str, Any], path: Path | None) -> None:
    encoded = json.dumps(bundle, ensure_ascii=False, indent=2)
    if path:
        path.write_text(encoded + "\n", encoding="utf-8")
        print(json.dumps({"status": bundle["status"], "output": str(path), "claim_ready_source_count": len(bundle["evidence_gate"]["claim_eligible_urls"])}, ensure_ascii=False, indent=2))
    else:
        print(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--query", action="append", default=[], help="Additional query; repeat for a bounded query set.")
    parser.add_argument("--engine", choices=["google", "bing"], default="google")
    parser.add_argument("--country", default="us")
    parser.add_argument("--language", default="en")
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--source-budget", type=int, default=4, help="Maximum combined web and file sources to fetch.")
    parser.add_argument("--file-url", action="append", default=[], help="Direct PDF/Office file URL to extract; repeat as needed.")
    parser.add_argument("--include-content", action="store_true", help="Include extracted Markdown in the output manifest; otherwise keep only metadata and length.")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--wait-ms", type=int, default=3000)
    parser.add_argument("--screenshot", type=int, choices=[1, 2], help="Optional viewport (1) or full-page (2) capture for selected web sources.")
    parser.add_argument("--proxy", type=int, choices=range(4), default=0)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--client-timeout", type=int, default=35)
    parser.add_argument("--retries", type=int, choices=range(1, 4), default=2)
    parser.add_argument("--account-mode", choices=["auto", "off", "warn", "enforce", "cap"], default="auto")
    parser.add_argument("--max-concurrency", default="auto")
    parser.add_argument("--min-claim-ready", type=int, default=2)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if min(args.max_candidates, args.source_budget, args.min_claim_ready) < 1:
        parser.error("--max-candidates, --source-budget, and --min-claim-ready must be positive")
    if any(not valid_url(url) for url in args.file_url):
        parser.error("every --file-url must be an absolute http or https URL")
    queries = list(dict.fromkeys([args.question, *args.query]))
    files = list(dict.fromkeys(args.file_url))
    search_credits, reader_cost = len(queries), reader_credit_cost(args.proxy)
    mode = "cap" if args.account_mode == "auto" else args.account_mode
    budget = account_guard(mode, search_credits + args.source_budget * reader_cost, timeout_seconds=args.client_timeout)
    budget.update({"search_credits": search_credits, "reader_credits_per_source": reader_cost, "requested_source_budget": args.source_budget})
    effective_budget = args.source_budget
    if budget["decision"] == "block":
        blocked = {"status": "blocked", "question": args.question, "queries": queries, "sources": [], "evidence_gate": {"claim_eligible_urls": []}, "account_guard": budget}
        write_output(blocked, args.out)
        return 2
    if mode == "cap" and budget["budget_status"] == "insufficient":
        effective_budget = cap_sources(budget["remaining_credits"], search_credits, reader_cost, args.source_budget) if isinstance(budget.get("remaining_credits"), int) else None
        if effective_budget is None:
            budget.update({"decision": "block", "effective_estimated_credits": 0})
            blocked = {"status": "blocked", "question": args.question, "queries": queries, "sources": [], "evidence_gate": {"claim_eligible_urls": []}, "account_guard": budget}
            write_output(blocked, args.out)
            return 2
        budget.update({"decision": "capped", "effective_estimated_credits": search_credits + effective_budget * reader_cost})
    try:
        workers = resolve_workers(args.max_concurrency, budget)
    except ValueError as error:
        parser.error(str(error))
    budget["effective_concurrency"] = workers
    searches = parallel_map(queries, lambda query: search(query, args), workers)
    selected = select_sources(searches, files, effective_budget)
    sources = parallel_map(selected, lambda source: fetch(source, args), workers)
    eligible = [source["url"] for source in sources if source.get("claim_ready")]
    bundle = {
        "status": "capped" if budget.get("decision") == "capped" else "ok",
        "question": args.question,
        "queries": queries,
        "market": {"country": args.country, "language": args.language},
        "searches": searches,
        "sources": sources,
        "evidence_gate": {
            "status": "passed" if len(eligible) >= args.min_claim_ready else "not_met",
            "minimum_claim_ready_sources": args.min_claim_ready,
            "claim_eligible_urls": eligible,
            "ineligible_sources": [{"url": item.get("url", ""), "status": item.get("status", "unknown")} for item in sources if not item.get("claim_ready")],
            "rule": "Only claim_eligible_urls may support consequential RAG answers. Authority remains unassessed until a human or policy-based evaluator classifies it.",
        },
        "limits": {"max_candidates_per_query": args.max_candidates, "requested_source_budget": args.source_budget, "effective_source_budget": effective_budget, "include_content": args.include_content},
        "account_guard": budget,
    }
    write_output(bundle, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
