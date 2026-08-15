#!/usr/bin/env python3
"""Map localized Google web, image, video, and short-video content formats."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from searchcans_v1 import account_guard, normalize_organic, post, request_metadata


SURFACES = {
    "web": ("google", "organic"),
    "images": ("google_images", "images_results"),
    "videos": ("google_videos", "video_results"),
    "short-videos": ("google_short_videos", "short_video_results"),
}


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


def normalize_surface(name: str, body: dict[str, Any]) -> dict[str, Any]:
    data = body.get("data") or {}
    engine, data_key = SURFACES[name]
    if name == "web":
        return {
            "format": name,
            "engine": engine,
            "request": request_metadata(body),
            "results": normalize_organic(data),
            "people_also_ask": data.get("peopleAlsoAsk", []) if isinstance(data, dict) else [],
            "related_searches": data.get("relatedSearches", []) if isinstance(data, dict) else [],
        }
    raw = data.get(data_key, []) if isinstance(data, dict) else []
    results: list[dict[str, Any]] = []
    for index, item in enumerate(raw if isinstance(raw, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        record = {"position": item.get("position", index), "title": item.get("title", ""), "url": item.get("link", ""), "source": item.get("source", "")}
        if name == "images":
            record.update({"thumbnail": item.get("thumbnail", ""), "original": item.get("original", ""), "width": item.get("original_width"), "height": item.get("original_height"), "is_product": item.get("is_product")})
        elif name == "videos":
            record.update({"snippet": item.get("snippet", ""), "duration": item.get("duration", ""), "channel": item.get("channel", ""), "thumbnail": item.get("thumbnail", "")})
        else:
            record.update({"channel": item.get("channel", ""), "duration": item.get("duration", "")})
        results.append(record)
    output = {"format": name, "engine": engine, "request": request_metadata(body), "results": results}
    if name == "images" and isinstance(data, dict):
        output["suggested_searches"] = data.get("suggestedSearches", [])
    return output


def collect(name: str, query: str, args: argparse.Namespace) -> dict[str, Any]:
    engine, _ = SURFACES[name]
    body = post("search", {"t": engine, "s": query, "country": args.country, "language": args.language, "d": args.timeout_ms}, timeout_seconds=args.client_timeout, retries=args.retries)
    return normalize_surface(name, body)


def write_output(bundle: dict[str, Any], path: Path | None) -> None:
    encoded = json.dumps(bundle, ensure_ascii=False, indent=2)
    if path:
        path.write_text(encoded + "\n", encoding="utf-8")
        print(json.dumps({"status": bundle["status"], "output": str(path), "formats": list(bundle["formats"])}, ensure_ascii=False, indent=2))
    else:
        print(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--country", default="us")
    parser.add_argument("--language", default="en")
    parser.add_argument("--surface", action="append", choices=list(SURFACES), help="Repeat to request a subset; defaults to all four formats.")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--client-timeout", type=int, default=35)
    parser.add_argument("--retries", type=int, choices=range(1, 4), default=2)
    parser.add_argument("--account-mode", choices=["auto", "off", "warn", "enforce", "cap"], default="auto")
    parser.add_argument("--max-concurrency", default="auto")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.max_results < 1:
        parser.error("--max-results must be positive")
    requested = args.surface or list(SURFACES)
    selected = list(dict.fromkeys(requested))
    mode = "cap" if args.account_mode == "auto" else args.account_mode
    budget = account_guard(mode, estimated_credits=len(selected), timeout_seconds=args.client_timeout)
    budget.update({"requested_formats": selected, "search_credits_per_format": 1})
    if budget["decision"] == "block":
        write_output({"status": "blocked", "query": args.query, "market": {"country": args.country, "language": args.language}, "formats": {}, "account_guard": budget}, args.out)
        return 2
    if mode == "cap" and budget["budget_status"] == "insufficient":
        remaining = budget.get("remaining_credits")
        if not isinstance(remaining, int) or remaining < 1:
            budget.update({"decision": "block", "effective_estimated_credits": 0})
            write_output({"status": "blocked", "query": args.query, "market": {"country": args.country, "language": args.language}, "formats": {}, "account_guard": budget}, args.out)
            return 2
        selected = selected[:remaining]
        budget.update({"decision": "capped", "effective_estimated_credits": len(selected)})
    try:
        workers = resolve_workers(args.max_concurrency, budget)
    except ValueError as error:
        parser.error(str(error))
    budget["effective_concurrency"] = workers
    collected = parallel_map(selected, lambda name: collect(name, args.query, args), workers)
    formats = {item["format"]: item for item in collected}
    for item in formats.values():
        item["results"] = item["results"][: args.max_results]
    bundle = {
        "status": "capped" if budget.get("decision") == "capped" else "ok",
        "query": args.query,
        "market": {"country": args.country, "language": args.language},
        "formats": formats,
        "limits": {"max_results_per_format": args.max_results, "requested_formats": requested, "effective_formats": selected},
        "interpretation_bounds": [
            "This is a localized SERP-format snapshot, not an engagement, popularity, or ranking report.",
            "Image and video URLs are discovery references. Their appearance does not grant reuse, licensing, or ownership rights.",
            "Use the observed formats to form hypotheses; verify page-level claims with an appropriate Reader workflow before publishing them.",
        ],
        "account_guard": budget,
    }
    write_output(bundle, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
