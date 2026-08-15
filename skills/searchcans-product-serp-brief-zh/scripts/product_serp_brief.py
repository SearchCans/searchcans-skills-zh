#!/usr/bin/env python3
"""Build a localized Google Shopping, web, image, and Reader product evidence brief."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from searchcans_v1 import SearchCansError, account_guard, normalize_organic, post, reader_credit_cost, request_metadata


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


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
        requested = int(value)
    except ValueError as error:
        raise ValueError("--max-concurrency must be auto or a positive integer") from error
    if requested < 1:
        raise ValueError("--max-concurrency must be auto or a positive integer")
    lanes = budget.get("concurrent_lanes")
    return min(requested, lanes) if isinstance(lanes, int) and lanes > 0 else requested


def cap_reads(remaining: int, search_credits: int, reader_cost: int, requested: int) -> int | None:
    if remaining < search_credits:
        return None
    return min(requested, (remaining - search_credits) // reader_cost)


def search(surface: str, query: str, args: argparse.Namespace) -> dict[str, Any]:
    body = post("search", {"t": surface, "s": query, "country": args.country, "language": args.language, "d": args.timeout_ms}, timeout_seconds=args.client_timeout, retries=args.retries)
    data = body.get("data") or {}
    request = request_metadata(body)
    if surface == "google_shopping":
        raw = data.get("shopping_results", []) if isinstance(data, dict) else []
        products = [
            {
                "position": item.get("position", index), "title": item.get("title", ""), "product_id": item.get("product_id", ""),
                "product_link": item.get("product_link", ""), "merchant": item.get("source", ""), "price": item.get("price", ""),
                "extracted_price": item.get("extracted_price"), "rating": item.get("rating"), "reviews": item.get("reviews"),
                "thumbnail": item.get("thumbnail", ""), "multiple_sources": item.get("multiple_sources"), "delivery": item.get("delivery"),
            }
            for index, item in enumerate(raw if isinstance(raw, list) else [], start=1) if isinstance(item, dict)
        ]
        return {"surface": surface, "request": request, "results": products}
    if surface == "google_images":
        raw = data.get("images_results", []) if isinstance(data, dict) else []
        images = [
            {"position": item.get("position", index), "title": item.get("title", ""), "url": item.get("link", ""), "source": item.get("source", ""), "thumbnail": item.get("thumbnail", ""), "original": item.get("original", ""), "width": item.get("original_width"), "height": item.get("original_height"), "is_product": item.get("is_product")}
            for index, item in enumerate(raw if isinstance(raw, list) else [], start=1) if isinstance(item, dict)
        ]
        return {"surface": surface, "request": request, "results": images, "suggested_searches": data.get("suggestedSearches", []) if isinstance(data, dict) else []}
    return {"surface": surface, "request": request, "results": normalize_organic(data), "people_also_ask": data.get("peopleAlsoAsk", []) if isinstance(data, dict) else [], "related_searches": data.get("relatedSearches", []) if isinstance(data, dict) else []}


def read_url(url: str, args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {"t": "url", "s": url, "proxy": args.proxy, "d": args.timeout_ms}
    if args.headless:
        payload.update({"mode": 1, "w": args.wait_ms})
    try:
        body = post("url", payload, timeout_seconds=args.client_timeout, retries=args.retries)
        data, markdown = body.get("data") or {}, (body.get("data") or {}).get("markdown") or ""
        return {"url": url, "status": "ok" if markdown else "empty", "claim_ready": bool(markdown), "title": data.get("title", ""), "description": data.get("description", ""), "markdown": markdown, "request": request_metadata(body)}
    except SearchCansError as error:
        return {"url": url, "status": "error", "claim_ready": False, "error": str(error)}


def output(bundle: dict[str, Any], path: Path | None) -> None:
    encoded = json.dumps(bundle, ensure_ascii=False, indent=2)
    if path:
        path.write_text(encoded + "\n", encoding="utf-8")
        shopping = bundle.get("shopping", {})
        products = shopping.get("results", []) if isinstance(shopping, dict) else []
        print(json.dumps({"status": bundle["status"], "output": str(path), "product_count": len(products)}, ensure_ascii=False, indent=2))
    else:
        print(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--country", default="us")
    parser.add_argument("--language", default="en")
    parser.add_argument("--max-products", type=int, default=10)
    parser.add_argument("--max-web-results", type=int, default=5)
    parser.add_argument("--max-images", type=int, default=10)
    parser.add_argument("--read-url", action="append", default=[], help="A merchant or product URL you are permitted to fetch; repeat as needed.")
    parser.add_argument("--max-read-urls", type=int, default=2)
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
    if min(args.max_products, args.max_web_results, args.max_images) < 1 or args.max_read_urls < 0:
        parser.error("result limits must be positive and --max-read-urls cannot be negative")
    if any(not valid_url(url) for url in args.read_url):
        parser.error("every --read-url must be an absolute http or https URL")
    read_urls = list(dict.fromkeys(args.read_url))[: args.max_read_urls]
    search_credits, read_cost = 3, reader_credit_cost(args.proxy)
    mode = "cap" if args.account_mode == "auto" else args.account_mode
    budget = account_guard(mode, search_credits + len(read_urls) * read_cost, timeout_seconds=args.client_timeout)
    budget.update({"search_credits": search_credits, "reader_credits_per_source": read_cost, "requested_read_urls": len(read_urls)})
    effective_reads = len(read_urls)
    if budget["decision"] == "block":
        output({"status": "blocked", "query": args.query, "market": {"country": args.country, "language": args.language}, "account_guard": budget}, args.out)
        return 2
    if mode == "cap" and budget["budget_status"] == "insufficient":
        effective_reads = cap_reads(budget["remaining_credits"], search_credits, read_cost, len(read_urls)) if isinstance(budget.get("remaining_credits"), int) else None
        if effective_reads is None:
            budget.update({"decision": "block", "effective_estimated_credits": 0})
            output({"status": "blocked", "query": args.query, "market": {"country": args.country, "language": args.language}, "account_guard": budget}, args.out)
            return 2
        budget.update({"decision": "capped", "effective_estimated_credits": search_credits + effective_reads * read_cost})
    try:
        workers = resolve_workers(args.max_concurrency, budget)
    except ValueError as error:
        parser.error(str(error))
    budget["effective_concurrency"] = workers
    snapshots = parallel_map(["google_shopping", "google", "google_images"], lambda surface: search(surface, args.query, args), workers)
    by_surface = {item["surface"]: item for item in snapshots}
    by_surface["google_shopping"]["results"] = by_surface["google_shopping"]["results"][: args.max_products]
    by_surface["google"]["results"] = by_surface["google"]["results"][: args.max_web_results]
    by_surface["google_images"]["results"] = by_surface["google_images"]["results"][: args.max_images]
    reads = parallel_map(read_urls[:effective_reads], lambda url: read_url(url, args), workers)
    numeric_prices = [item["extracted_price"] for item in by_surface["google_shopping"]["results"] if isinstance(item.get("extracted_price"), (int, float))]
    merchants = sorted({item["merchant"] for item in by_surface["google_shopping"]["results"] if item.get("merchant")})
    bundle = {
        "status": "capped" if budget.get("decision") == "capped" else "ok",
        "query": args.query,
        "market": {"country": args.country, "language": args.language},
        "shopping": by_surface["google_shopping"],
        "google_web": by_surface["google"],
        "google_images": by_surface["google_images"],
        "merchant_observations": {"merchants": merchants, "observed_numeric_price_range": {"min": min(numeric_prices), "max": max(numeric_prices)} if numeric_prices else None, "warning": "Prices are a time-stamped Google Shopping SERP observation in the selected market. They are not a price guarantee and are not currency-normalized."},
        "read_sources": reads,
        "evidence_gate": {"claim_eligible_urls": [item["url"] for item in reads if item.get("claim_ready")], "rule": "Only successful Reader extracts support claims about a merchant or product page. Shopping and image results are discovery observations."},
        "limits": {"max_products": args.max_products, "max_web_results": args.max_web_results, "max_images": args.max_images, "requested_read_urls": len(read_urls), "effective_read_urls": effective_reads},
        "account_guard": budget,
    }
    output(bundle, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
