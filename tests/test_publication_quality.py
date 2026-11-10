import json
import os
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sdg_digest.generate import generate_digest, validate_digest_payload, fallback_digest
from sdg_digest.quality import validate_publication
from sdg_digest.discovery import DiscoveryPipeline
from sdg_digest.discovery_config import DiscoveryConfig
from sdg_digest.discovery_http import PublicFetcher, FetchFailure
from sdg_digest.website import normalize_digest
from tests.test_generate import _candidate, _candidate_two, _payload


class PublicationQualityTests(unittest.TestCase):
    def test_exhausted_validation_never_silently_publishes_fallback(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test", "ALLOW_OPENAI_FALLBACK": "false"}), patch(
            "sdg_digest.generate._call_openai", return_value={}
        ) as api, patch("sdg_digest.generate.fallback_digest") as fallback:
            with self.assertRaisesRegex(RuntimeError, "refusing to publish"):
                generate_digest([_candidate()], {}, date(2026, 11, 9), 5)
            self.assertEqual(api.call_count, 2)
            fallback.assert_not_called()

    def test_even_opted_in_fallback_cannot_pass_publication_or_site(self):
        digest = fallback_digest([_candidate()], {}, date(2026, 11, 9))
        for check in (validate_publication, lambda d: normalize_digest(asdict(d))):
            with self.assertRaisesRegex(ValueError, "fallback blocked"):
                check(digest)

    def test_real_failed_edition_is_rejected_even_if_marked_reviewed(self):
        raw = json.loads(Path("archive/2026-11-09/digest.json").read_text())
        # The archived regression fixture must not be changed by regenerating the issue.
        raw.update(generation_mode="reviewed", issue_title_en="Climate Policy and Governance in This Week", issue_title_zh="本周气候政策与治理")
        raw["title_support"] = [{"url": row["url"], "angle_en": "This article supports the climate governance theme."}
                                for row in raw["recent_news"] + raw["research_signals"]]
        raw["recent_news"][0]["one_sentence_en"] = "Source reports a relevant development: An incomplete excerpt…"
        with self.assertRaisesRegex(ValueError, "Placeholder|report label"):
            validate_publication(raw)

    def test_tracking_variants_resolve_but_new_query_values_do_not(self):
        first = replace(_candidate(), url="https://example.org/article?doc=1&utm_source=rss", event_id="event:1")
        second = _candidate_two()
        payload = _payload(first, second)
        payload["items"][0]["url"] = "https://example.org/article?doc=1"
        payload["title_support"][0]["url"] = "https://example.org/article?doc=1#top"
        result = validate_digest_payload(payload, [first, second], {}, date(2026, 11, 9))
        self.assertEqual(result.research_signals[0].url, first.url)
        self.assertEqual(result.title_support[0].url, first.url)
        payload["items"][0]["url"] = "https://example.org/article?doc=2"
        result = validate_digest_payload(payload, [first, second], {}, date(2026, 11, 9), check_title=False)
        self.assertEqual(len(result.research_signals), 1)

    def test_generated_editorial_headline_is_not_overwritten_by_source_title(self):
        c = replace(_candidate(), title_en="Source teaser — report")
        payload = _payload(c)
        payload["items"][0]["title_en"] = "Public agencies struggle to turn climate pledges into projects"
        result = validate_digest_payload(payload, [c], {}, date(2026, 11, 9))
        self.assertEqual(result.research_signals[0].title_en, payload["items"][0]["title_en"])
        self.assertEqual(result.research_signals[0].title_original, c.title)

    def test_abstract_copy_and_false_method_disclaimer_are_rejected(self):
        raw = asdict(validate_digest_payload(_payload(_candidate()), [_candidate()], {}, date(2026, 11, 9)))
        abstract = "Using a comparative and critical method, the authors examine governance institutions. " + "They find that internal differences constrain cooperation across the participating states and their climate policy institutions."
        reading = {"note_en": abstract, "note_zh": "比较制度分析发现内部差异限制合作。", "abstract_en": abstract,
                   "method_en": "Comparative and critical analysis.", "methodology_zh": "比较与批判分析。"}
        raw["readings"] = [reading]
        with self.assertRaisesRegex(ValueError, "copies"):
            validate_publication(raw)
        reading.update(note_en="Internal institutional differences can limit collective climate action.",
                       method_en="The abstract does not specify the method.")
        with self.assertRaisesRegex(ValueError, "contradicts"):
            validate_publication(raw)

    def test_discovery_budget_cannot_consume_evidence_reserve(self):
        with tempfile.TemporaryDirectory() as directory:
            p = DiscoveryPipeline(DiscoveryConfig(max_requests=120, evidence_requests=30), date(2026, 11, 9), Path(directory))
            def exhaust(*args):
                p.fetcher.requests = 90
                with patch.object(p.fetcher, "validate_url"), self.assertRaisesRegex(FetchFailure, "budget"):
                    p.fetcher._request("https://example.org/article")
            with patch.object(p, "_discover", side_effect=exhaust):
                p.discover([])
            self.assertEqual(p.fetcher.max_requests - p.fetcher.requests, 30)
            self.assertEqual(p.fetcher.request_limit, 120)

    def test_editorial_context_cannot_reference_an_unselected_candidate(self):
        raw = asdict(validate_digest_payload(_payload(_candidate()), [_candidate()], {}, date(2026, 11, 9)))
        raw["editorial_context_urls"] = ["https://unselected.example/article"]
        with self.assertRaisesRegex(ValueError, "unselected article"):
            validate_publication(raw)

    def test_publisher_says_headlines_are_not_informative(self):
        raw = asdict(validate_digest_payload(_payload(_candidate()), [_candidate()], {}, date(2026, 11, 9)))
        raw["research_signals"][0].update(source_org="The Guardian Environment", title_en="Guardian says climate policy must change")
        with self.assertRaisesRegex(ValueError, "publisher-says"):
            validate_publication(raw)

    def test_failed_title_repair_does_not_regenerate_the_validated_body(self):
        first, second = _candidate(), _candidate_two()
        raw = _payload(first, second)
        raw["title_support"] = []
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test", "ALLOW_OPENAI_FALLBACK": "false"}), patch(
            "sdg_digest.generate._call_openai", return_value=raw
        ) as body, patch("sdg_digest.generate._repair_issue_title", return_value=raw):
            with self.assertRaisesRegex(RuntimeError, "Title repair failed"):
                generate_digest([first, second], {}, date(2026, 11, 9), 5)
            self.assertEqual(body.call_count, 1)

    def test_title_repair_counts_research_module_and_retries_only_title(self):
        from sdg_digest.generate import _repair_issue_title
        from sdg_digest.models import Digest
        from tests.test_issue_titles import article, title_payload
        news = [article(0), article(1)]
        signals = [article(2, True), article(3, True)]
        digest = Digest(date(2026, 11, 9), "Issue", "", signals, recent_news=news, research_signals=signals)
        bad, good = title_payload(news + signals[:1]), title_payload(signals + news[:1])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("sdg_digest.generate.post_json", side_effect=[
            {"output_text": json.dumps(bad)}, {"output_text": json.dumps(good)}
        ]) as api:
            result = _repair_issue_title(digest, "coverage")
        self.assertEqual(api.call_count, 2)
        self.assertEqual(result, good)
        messages = api.call_args.args[1]["input"]
        self.assertIn("at least 2 distinct URLs from selected_research", messages[0]["content"])
        self.assertEqual(json.loads(messages[-1]["content"])["actual_research_support_count"], 1)

    def test_fallback_cannot_reach_archive_or_email_transport(self):
        from sdg_digest.archive import write_archive
        from sdg_digest.emailer import send_email
        digest = fallback_digest([_candidate()], {}, date(2026, 11, 9))
        with tempfile.TemporaryDirectory() as directory, patch("sdg_digest.emailer.post_json") as transport:
            with self.assertRaises(ValueError):
                write_archive(digest, directory)
            self.assertEqual(list(Path(directory).iterdir()), [])
            with self.assertRaises(ValueError):
                send_email(digest, "irrelevant")
            transport.assert_not_called()

    def test_phase_budget_exhaustion_does_not_cache_robots_denial(self):
        with tempfile.TemporaryDirectory() as directory:
            f = PublicFetcher(Path(directory))
            with patch.object(f, "_request", side_effect=FetchFailure("request_budget_exhausted")):
                with self.assertRaises(FetchFailure):
                    f._policy("https://example.org/article")
            self.assertEqual(f.robots, {})


if __name__ == "__main__":
    unittest.main()
