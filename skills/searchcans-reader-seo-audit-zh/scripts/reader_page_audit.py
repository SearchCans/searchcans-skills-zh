#!/usr/bin/env python3
"""Extract a page with Reader API and report content plus SEO-ready HTML signals."""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from searchcans_v1 import account_guard, post, reader_credit_cost


class PageSignalsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonical = ""
        self.meta_description = ""
        self.h1s: list[str] = []
        self.jsonld_count = 0
        self.jsonld_invalid = 0
        self._in_h1 = False
        self._in_jsonld = False
        self._h1_parts: list[str] = []
        self._jsonld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): value or "" for name, value in attrs}
        if tag == "link" and attributes.get("rel", "").lower() == "canonical":
            self.canonical = attributes.get("href", "")
        if tag == "meta" and attributes.get("name", "").lower() == "description":
            self.meta_description = attributes.get("content", "")
        if tag == "h1":
            self._in_h1 = True
            self._h1_parts = []
        if tag == "script" and attributes.get("type", "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._jsonld_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_h1:
            self._h1_parts.append(data)
        if self._in_jsonld:
            self._jsonld_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1" and self._in_h1:
            value = " ".join("".join(self._h1_parts).split())
            if value:
                self.h1s.append(value)
            self._in_h1 = False
        if tag == "script" and self._in_jsonld:
            self.jsonld_count += 1
            try:
                json.loads("".join(self._jsonld_parts))
            except json.JSONDecodeError:
                self.jsonld_invalid += 1
            self._in_jsonld = False


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--headless", action="store_true", help="Render JavaScript before extraction.")
    parser.add_argument("--wait-ms", type=int, default=3000)
    parser.add_argument("--include-html", action="store_true", help="Request HTML to inspect page signals.")
    parser.add_argument("--file", action="store_true", help="Parse a PDF or Office document URL.")
    parser.add_argument("--screenshot", type=int, choices=[1, 2], help="Capture viewport (1) or full-page (2) screenshot.")
    parser.add_argument("--proxy", type=int, choices=range(4), default=0)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--client-timeout", type=int, default=35)
    parser.add_argument("--account-mode", choices=["auto", "off", "warn", "enforce", "cap"], default="auto", help="Account pre-flight policy. auto checks higher-cost proxy requests.")
    parser.add_argument("--out", type=Path, help="Write the full API body plus audit result to this file.")
    args = parser.parse_args()
    if not valid_url(args.url):
        parser.error("url must be an absolute http or https URL")

    mode = "enforce" if args.account_mode == "auto" and args.proxy > 0 else "off" if args.account_mode == "auto" else args.account_mode
    budget = account_guard(mode, estimated_credits=reader_credit_cost(args.proxy), timeout_seconds=args.client_timeout)
    if mode == "cap" and budget["budget_status"] == "insufficient":
        budget["decision"] = "block"
    if budget["decision"] == "block":
        result = {
            "status": "blocked",
            "url": args.url,
            "account_guard": budget,
        }
        encoded = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            args.out.write_text(json.dumps({"result": result}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(encoded)
        return 2

    payload: dict[str, Any] = {"t": "url", "s": args.url, "d": args.timeout_ms, "proxy": args.proxy}
    if args.headless:
        payload.update({"mode": 1, "w": args.wait_ms})
    if args.include_html:
        payload["html"] = 1
    if args.file:
        payload["file"] = 1
    if args.screenshot:
        payload["image"] = args.screenshot

    body = post("url", payload, timeout_seconds=args.client_timeout)
    data = body.get("data") or {}
    page_html = data.get("html") or ""
    parser_html = PageSignalsParser()
    if page_html:
        parser_html.feed(page_html)
        parser_html.close()

    result = {
        "status": "ok",
        "url": args.url,
        "account_guard": budget,
        "api_code": body.get("code"),
        "request_id": body.get("requestId"),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "markdown_length": len(data.get("markdown") or data.get("fileMarkdown") or ""),
        "image_url": data.get("imageUrl"),
        "html_length": len(page_html),
        "canonical": parser_html.canonical,
        "h1_count": len(parser_html.h1s),
        "h1s": parser_html.h1s,
        "meta_description_length": len(parser_html.meta_description),
        "jsonld_count": parser_html.jsonld_count,
        "jsonld_invalid": parser_html.jsonld_invalid,
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(json.dumps({"result": result, "body": body}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
