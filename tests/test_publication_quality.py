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

    def test_phase_budget_exhaustion_does_not_cache_robots_denial(self):
        with tempfile.TemporaryDirectory() as directory:
            f = PublicFetcher(Path(directory))
            with patch.object(f, "_request", side_effect=FetchFailure("request_budget_exhausted")):
                with self.assertRaises(FetchFailure):
                    f._policy("https://example.org/article")
            self.assertEqual(f.robots, {})


if __name__ == "__main__":
    unittest.main()
