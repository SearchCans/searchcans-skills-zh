from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class SearchCansScriptTests(unittest.TestCase):
    def test_normalizes_current_and_compatibility_serp_shapes(self) -> None:
        module = load_module("deep_client", "skills/searchcans-deep-research-zh/scripts/searchcans_v1.py")
        current = module.normalize_organic({"organic": [{"position": 2, "title": "Current", "link": "https://example.com", "snippet": "Text"}]})
        compatibility = module.normalize_organic([{"title": "Legacy", "url": "https://legacy.example", "content": "Body"}])
        self.assertEqual(current[0]["url"], "https://example.com")
        self.assertEqual(current[0]["snippet"], "Text")
        self.assertEqual(compatibility[0]["url"], "https://legacy.example")
        self.assertEqual(compatibility[0]["snippet"], "Body")
        self.assertTrue(module.is_success_code(-9999))

    def test_content_gap_labels_no_results_and_preserves_request_metadata(self) -> None:
        module = load_module("content_gap_client", "skills/searchcans-serp-content-gap-zh/scripts/searchcans_v1.py")
        body = module.with_request_metadata({"code": -9999, "msg": "No results", "data": {}}, attempts=1)
        metadata = module.request_metadata(body)
        self.assertEqual(metadata["status"], "no_results")
        self.assertEqual(metadata["api_code"], -9999)
        self.assertEqual(metadata["attempts"], 1)
        self.assertEqual(metadata["retry_count"], 0)

    def test_content_gap_retries_only_transient_api_errors(self) -> None:
        module = load_module("content_gap_retry_client", "skills/searchcans-serp-content-gap-zh/scripts/searchcans_v1.py")

        class Response:
            def __init__(self, body: dict[str, object]) -> None:
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback) -> bool:
                return False

            def read(self) -> bytes:
                import json

                return json.dumps(self.body).encode("utf-8")

        responses = iter([Response({"code": 1001, "msg": "Timeout"}), Response({"code": 0, "data": {}})])
        delays: list[float] = []
        original_urlopen = module.urlopen
        original_sleep = module.time.sleep
        original_api_key = module.api_key
        module.urlopen = lambda *args, **kwargs: next(responses)
        module.time.sleep = lambda delay: delays.append(delay)
        module.api_key = lambda: "test-key"
        try:
            body = module.post("search", {"t": "google", "s": "test"}, retries=2)
        finally:
            module.urlopen = original_urlopen
            module.time.sleep = original_sleep
            module.api_key = original_api_key

        self.assertEqual(body["_searchcans_client"]["status"], "ok")
        self.assertEqual(body["_searchcans_client"]["attempts"], 2)
        self.assertEqual(body["_searchcans_client"]["retry_count"], 1)
        self.assertEqual(delays, [0.3])

    def test_account_snapshot_is_sanitized_before_reporting(self) -> None:
        module = load_module("account_client", "skills/searchcans-deep-research-zh/scripts/searchcans_v1.py")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback) -> bool:
                return False

            def read(self) -> bytes:
                import json

                return json.dumps(
                    {
                        "code": 0,
                        "data": {
                            "email": "private@example.com",
                            "key": "secret-current-key",
                            "remain": 17,
                            "concurrent": 3,
                            "keys": [
                                {"key": "secret-current-key", "active": True},
                                {"key": "secret-other-key", "active": False},
                            ],
                        },
                    }
                ).encode("utf-8")

        original_urlopen = module.urlopen
        original_api_key = module.api_key
        module.urlopen = lambda *args, **kwargs: Response()
        module.api_key = lambda: "test-key"
        try:
            snapshot = module.account_snapshot()
        finally:
            module.urlopen = original_urlopen
            module.api_key = original_api_key

        self.assertEqual(
            snapshot,
            {"remaining_credits": 17, "concurrent_lanes": 3, "current_key_active": True, "attempts": 1},
        )
        self.assertNotIn("email", snapshot)
        self.assertNotIn("key", snapshot)

    def test_account_guard_blocks_an_insufficient_enforced_job(self) -> None:
        module = load_module("account_guard_client", "skills/searchcans-serp-content-gap-zh/scripts/searchcans_v1.py")
        original_snapshot = module.account_snapshot
        module.account_snapshot = lambda **kwargs: {"remaining_credits": 2, "concurrent_lanes": 1, "current_key_active": True, "attempts": 1}
        try:
            guard = module.account_guard("enforce", estimated_credits=3)
        finally:
            module.account_snapshot = original_snapshot

        self.assertEqual(guard["budget_status"], "insufficient")
        self.assertEqual(guard["decision"], "block")
        self.assertEqual(guard["remaining_credits"], 2)

    def test_reader_audit_blocks_before_the_business_request(self) -> None:
        module = load_module("reader_budget_block", "skills/searchcans-reader-seo-audit-zh/scripts/reader_page_audit.py")
        original_argv = sys.argv
        original_guard = module.account_guard
        original_post = module.post
        module.account_guard = lambda *args, **kwargs: {
            "mode": "enforce",
            "estimated_credits": 2,
            "effective_estimated_credits": 2,
            "budget_status": "insufficient",
            "decision": "block",
            "remaining_credits": 0,
            "concurrent_lanes": 1,
            "current_key_active": True,
        }

        def unexpected_request(*args, **kwargs):
            raise AssertionError("Reader API must not run after an enforced budget block")

        module.post = unexpected_request
        try:
            sys.argv = ["reader_page_audit.py", "https://example.com", "--account-mode", "enforce"]
            with redirect_stdout(io.StringIO()):
                exit_code = module.main()
        finally:
            sys.argv = original_argv
            module.account_guard = original_guard
            module.post = original_post

        self.assertEqual(exit_code, 2)

    def test_deep_research_evidence_gate_excludes_unread_sources(self) -> None:
        module = load_module("deep_research", "skills/searchcans-deep-research-zh/scripts/deep_research.py")
        gate = module.evidence_gate(
            [
                {"url": "https://evidence.example", "status": "ok", "claim_ready": True},
                {"url": "https://empty.example", "status": "empty", "claim_ready": False},
            ]
        )
        self.assertEqual(gate["claim_eligible_urls"], ["https://evidence.example"])
        self.assertEqual(gate["ineligible_sources"], [{"url": "https://empty.example", "status": "empty"}])

    def test_deep_research_caps_sources_and_concurrency_to_account_limits(self) -> None:
        module = load_module("deep_research_budget", "skills/searchcans-deep-research-zh/scripts/deep_research.py")
        self.assertEqual(module.cap_sources_for_budget(remaining_credits=12, search_credits=4, reader_credits=2, requested_sources=8), 4)
        self.assertIsNone(module.cap_sources_for_budget(remaining_credits=3, search_credits=4, reader_credits=2, requested_sources=8))
        self.assertEqual(module.resolve_workers("10", {"concurrent_lanes": 3}), 3)
        self.assertEqual(module.resolve_workers("auto", {"concurrent_lanes": 2}), 2)

    def test_extracts_page_signals(self) -> None:
        module = load_module("seo_audit", "skills/searchcans-reader-seo-audit-zh/scripts/reader_page_audit.py")
        parser = module.PageSignalsParser()
        parser.feed("<link rel='canonical' href='https://example.com/canonical'><meta name='description' content='Summary'><h1> One heading </h1><script type='application/ld+json'>{\"@type\":\"Article\"}</script>")
        parser.close()
        self.assertEqual(parser.canonical, "https://example.com/canonical")
        self.assertEqual(parser.meta_description, "Summary")
        self.assertEqual(parser.h1s, ["One heading"])
        self.assertEqual(parser.jsonld_count, 1)
        self.assertEqual(parser.jsonld_invalid, 0)

    def test_market_watch_selects_diverse_news_domains_and_budget_caps_reads(self) -> None:
        module = load_module("market_watch", "skills/searchcans-market-watch-zh/scripts/market_watch.py")
        selected = module.select_news_sources(
            [
                {"url": "https://one.example/a", "title": "A"},
                {"url": "https://one.example/b", "title": "B"},
                {"url": "https://two.example/c", "title": "C"},
            ],
            3,
        )
        self.assertEqual([item["url"] for item in selected], ["https://one.example/a", "https://two.example/c", "https://one.example/b"])
        self.assertEqual(module.cap_reads(5, search_credits=3, reader_credits=2, requested=4), 1)
        self.assertIsNone(module.cap_reads(2, search_credits=3, reader_credits=2, requested=4))

    def test_product_brief_normalizes_observed_price_without_price_claim(self) -> None:
        module = load_module("product_brief", "skills/searchcans-product-serp-brief-zh/scripts/product_serp_brief.py")
        original_post = module.post
        module.post = lambda *args, **kwargs: {
            "code": 0,
            "data": {"shopping_results": [{"position": 1, "title": "Example", "source": "Merchant", "price": "$19.99", "extracted_price": 19.99}]},
        }
        try:
            response = module.search("google_shopping", "example", SimpleNamespace(country="us", language="en", timeout_ms=30000, client_timeout=35, retries=1))
        finally:
            module.post = original_post
        self.assertEqual(response["results"][0]["merchant"], "Merchant")
        self.assertEqual(response["results"][0]["extracted_price"], 19.99)
        self.assertEqual(module.cap_reads(6, search_credits=3, reader_cost=2, requested=3), 1)
        self.assertTrue(module.valid_url("https://merchant.example/product"))

    def test_content_format_normalizes_video_and_short_video_shapes(self) -> None:
        module = load_module("format_brief", "skills/searchcans-content-format-brief-zh/scripts/content_format_brief.py")
        video = module.normalize_surface(
            "videos",
            {"code": 0, "data": {"video_results": [{"position": 1, "title": "Watch", "link": "https://video.example", "duration": "1:00", "channel": "Channel"}]}},
        )
        short_video = module.normalize_surface(
            "short-videos",
            {"code": 0, "data": {"short_video_results": [{"position": 1, "title": "Clip", "link": "https://clip.example", "source": "YouTube", "channel": "Creator", "duration": "0:30"}]}},
        )
        self.assertEqual(video["results"][0]["duration"], "1:00")
        self.assertEqual(short_video["results"][0]["channel"], "Creator")

    def test_rag_curator_preserves_explicit_files_and_diversifies_search_domains(self) -> None:
        module = load_module("rag_curator", "skills/searchcans-rag-source-curator-zh/scripts/rag_source_curator.py")
        sources = module.select_sources(
            [
                {"query": "question", "organic": [
                    {"url": "https://one.example/a", "title": "A", "position": 1},
                    {"url": "https://one.example/b", "title": "B", "position": 2},
                    {"url": "https://two.example/c", "title": "C", "position": 3},
                ]}
            ],
            ["https://files.example/document.pdf"],
            3,
        )
        self.assertEqual([item["kind"] for item in sources], ["file", "web", "web"])
        self.assertEqual([item["url"] for item in sources[1:]], ["https://one.example/a", "https://two.example/c"])
        self.assertEqual(module.canonical_url("HTTPS://Example.COM/a#fragment"), "https://example.com/a")


if __name__ == "__main__":
    unittest.main()
