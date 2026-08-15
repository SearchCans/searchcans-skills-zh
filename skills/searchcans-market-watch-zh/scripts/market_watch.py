#!/usr/bin/env python3
"""Create a localized Google, Google News, Bing, and Reader market snapshot."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from searchcans_v1 import SearchCansError, account_guard, normalize_organic, post, reader_credit_cost, request_metadata


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


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


def parallel_map(items: list[Any], worker: Any, workers: int) -> list[Any]:
    if workers == 1:
        return [worker(item) for item in items]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(worker, items))


def cap_reads(remaining: int, search_credits: int, reader_credits: int, requested: int) -> int | None:
    if remaining < search_credits:
        return None
    return min(requested, (remaining - search_credits) // reader_credits)


def select_news_sources(items: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    """Take a domain-diverse, in-SERP-order selection of readable news URLs."""
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for item in items:
        url = str(item.get("url", ""))
        if valid_url(url):
            grouped.setdefault(urlparse(url).netloc.lower(), []).append(item)
    selected: list[dict[str, Any]] = []
    while grouped and len(selected) < maximum:
        for domain in list(grouped):
            selected.append(grouped[domain].pop(0))
            if not grouped[domain]:
                del grouped[domain]
            if len(selected) == maximum:
                break
    return selected


def search(surface: str, query: str, args: argparse.Namespace) -> dict[str, Any]:
    body = post(
        "search",
        {"t": surface, "s": query, "country": args.country, "language": args.language, "d": args.timeout_ms},
        timeout_seconds=args.client_timeout,
        retries=args.retries,
    )
    data = body.get("data") or {}
    if surface == "google_news":
        results = data.get("news_results", []) if isinstance(data, dict) else []
        news = [
            {
                "position": item.get("position", index),
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "publisher": (item.get("source") or {}).get("name", "") if isinstance(item.get("source"), dict) else "",
                "date": item.get("date", ""),
                "iso_date": item.get("iso_date", ""),
                "snippet": item.get("snippet", ""),
            }
            for index, item in enumerate(results if isinstance(results, list) else [], start=1)
            if isinstance(item, dict)
        ]
        return {"surface": surface, "request": request_metadata(body), "results": news}
    return {
        "surface": surface,
        "request": request_metadata(body),
        "results": normalize_organic(data),
        "people_also_ask": data.get("peopleAlsoAsk", []) if isinstance(data, dict) else [],
        "related_searches": data.get("relatedSearches", []) if isinstance(data, dict) else [],
    }


def read_source(source: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {"t": "url", "s": source["url"], "proxy": args.proxy, "d": args.timeout_ms}
    if args.headless:
        payload.update({"mode": 1, "w": args.wait_ms})
    try:
        body = post("url", payload, timeout_seconds=args.client_timeout, retries=args.retries)
        data = body.get("data") or {}
        markdown = data.get("markdown") or ""
        return {
            "url": source["url"],
            "serp_title": source.get("title", ""),
            "publisher": source.get("publisher", ""),
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "markdown": markdown,
            "status": "ok" if markdown else "empty",
            "claim_ready": bool(markdown),
            "request": request_metadata(body),
        }
    except SearchCansError as error:
        return {"url": source["url"], "serp_title": source.get("title", ""), "status": "error", "claim_ready": False, "error": str(error)}


def urls_from_previous(bundle: dict[str, Any]) -> set[str]:
    urls: set[str] = set()
    for section in ("google_web", "google_news", "bing_web"):
        for item in bundle.get(section, {}).get("results", []) if isinstance(bundle.get(section), dict) else []:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                urls.add(item["url"])
    return urls


def baseline_diff(path: Path | None, current: dict[str, Any]) -> dict[str, Any] | None:
    if not path:
        return None
    previous = json.loads(path.read_text(encoding="utf-8"))
    old_urls, new_urls = urls_from_previous(previous), urls_from_previous(current)
    return {"baseline": str(path), "new_urls": sorted(new_urls - old_urls), "removed_urls": sorted(old_urls - new_urls)}


def write_output(bundle: dict[str, Any], path: Path | None) -> None:
    encoded = json.dumps(bundle, ensure_ascii=False, indent=2)
    if path:
        path.write_text(encoded + "\n", encoding="utf-8")
        print(json.dumps({"status": bundle["status"], "output": str(path), "read_source_count": len(bundle["read_sources"])}, ensure_ascii=False, indent=2))
    else:
        print(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--country", default="us")
    parser.add_argument("--language", default="en")
    parser.add_argument("--without-bing", action="store_true", help="Skip the Bing corroboration snapshot.")
    parser.add_argument("--max-news-results", type=int, default=10)
    parser.add_argument("--max-web-results", type=int, default=5)
    parser.add_argument("--max-source-reads", type=int, default=3)
    parser.add_argument("--baseline", type=Path, help="Prior market-watch JSON for URL-level change detection.")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--wait-ms", type=int, default=3000)
    parser.add_argument("--proxy", type=int, choices=range(4), default=0)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--client-timeout", type=int, default=35)
    parser.add_argument("--retries", type=int, choices=range(1, 4), default=2)
    parser.add_argument("--account-mode", choices=["auto", "off", "warn", "enforce", "cap"], default="auto")
    parser.add_argument("--max-concurrency", default="auto")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if min(args.max_news_results, args.max_web_results) < 1 or args.max_source_reads < 0:
        parser.error("result limits must be positive and --max-source-reads cannot be negative")
    if args.baseline and not args.baseline.is_file():
        parser.error("--baseline must point to an existing market-watch JSON file")

    surfaces = ["google", "google_news"] + ([] if args.without_bing else ["bing"])
    search_credits, read_cost = len(surfaces), reader_credit_cost(args.proxy)
    mode = "cap" if args.account_mode == "auto" else args.account_mode
    budget = account_guard(mode, search_credits + args.max_source_reads * read_cost, timeout_seconds=args.client_timeout)
    budget.update({"search_credits": search_credits, "reader_credits_per_source": read_cost, "requested_source_reads": args.max_source_reads})
    effective_reads = args.max_source_reads
    if budget["decision"] == "block":
        bundle = {"status": "blocked", "query": args.query, "market": {"country": args.country, "language": args.language}, "read_sources": [], "account_guard": budget}
        write_output(bundle, args.out)
        return 2
    if mode == "cap" and budget["budget_status"] == "insufficient":
        effective_reads = cap_reads(budget["remaining_credits"], search_credits, read_cost, args.max_source_reads) if isinstance(budget.get("remaining_credits"), int) else None
        if effective_reads is None:
            budget.update({"decision": "block", "effective_estimated_credits": 0})
            bundle = {"status": "blocked", "query": args.query, "market": {"country": args.country, "language": args.language}, "read_sources": [], "account_guard": budget}
            write_output(bundle, args.out)
            return 2
        budget.update({"decision": "capped", "effective_estimated_credits": search_credits + effective_reads * read_cost})
    try:
        workers = resolve_workers(args.max_concurrency, budget)
    except ValueError as error:
        parser.error(str(error))
    budget["effective_concurrency"] = workers
    snapshots = parallel_map(surfaces, lambda surface: search(surface, args.query, args), workers)
    by_surface = {snapshot["surface"]: snapshot for snapshot in snapshots}
    news = by_surface["google_news"]
    news["results"] = news["results"][: args.max_news_results]
    for key in ("google", "bing"):
        if key in by_surface:
            by_surface[key]["results"] = by_surface[key]["results"][: args.max_web_results]
    selected = select_news_sources(news["results"], effective_reads)
    reads = parallel_map(selected, lambda source: read_source(source, args), workers)
    bundle: dict[str, Any] = {
        "status": "capped" if budget.get("decision") == "capped" else "ok",
        "query": args.query,
        "market": {"country": args.country, "language": args.language},
        "google_web": by_surface["google"],
        "google_news": news,
        "bing_web": by_surface.get("bing"),
        "read_sources": reads,
        "evidence_gate": {
            "claim_eligible_urls": [item["url"] for item in reads if item.get("claim_ready")],
            "rule": "Use successful Reader extracts for consequential claims; SERP titles and snippets are discovery evidence only.",
        },
        "limits": {"max_web_results": args.max_web_results, "max_news_results": args.max_news_results, "requested_source_reads": args.max_source_reads, "effective_source_reads": effective_reads},
        "account_guard": budget,
    }
    bundle["baseline_diff"] = baseline_diff(args.baseline, bundle)
    write_output(bundle, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
