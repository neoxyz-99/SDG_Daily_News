from __future__ import annotations

from datetime import date
import os
import unittest

from sdg_digest.generate import fallback_digest, generate_digest, validate_digest_payload
from sdg_digest.models import Candidate, DeepRead


class GenerateTests(unittest.TestCase):
    def test_generate_requires_openai_key_when_not_skipping(self) -> None:
        candidate = _candidate()
        original_key = os.environ.pop("OPENAI_API_KEY", None)
        original_fallback = os.environ.pop("ALLOW_OPENAI_FALLBACK", None)
        try:
            with self.assertRaises(RuntimeError):
                generate_digest([candidate], {}, date(2026, 6, 9), max_items=5, use_openai=True)
        finally:
            if original_key is not None:
                os.environ["OPENAI_API_KEY"] = original_key
            if original_fallback is not None:
                os.environ["ALLOW_OPENAI_FALLBACK"] = original_fallback

    def test_validation_rejects_invented_url(self) -> None:
        candidate = _candidate()
        payload = {
            "overview_zh": "今日关注气候金融。",
            "overview_en": "Today focuses on climate finance.",
            "items": [
                {
                    "title_en": "Climate Finance Update",
                    "source_org": "World Bank Climate",
                    "published_date": "2026-06-09",
                    "summary_zh": "这是一条关于气候金融政策含义的中文摘要。",
                    "summary_en": "This is an English brief on climate finance policy.",
                    "why_it_matters_zh": "它影响气候资金安排。",
                    "why_it_matters_en": "It matters for climate finance arrangements.",
                    "terms": [],
                    "tags": ["#气候金融"],
                    "sdg_links": ["SDG 13 Climate Action"],
                    "url": "https://invented.example/article",
                }
            ],
            "readings": [],
        }

        with self.assertRaises(ValueError):
            validate_digest_payload(payload, [candidate], {}, date(2026, 6, 9))

    def test_validation_rejects_unapproved_reading(self) -> None:
        candidate = _candidate()
        payload = {
            "overview_zh": "今日关注气候金融。",
            "overview_en": "Today focuses on climate finance.",
            "items": [
                {
                    "title_en": candidate.title,
                    "source_org": candidate.source_org,
                    "published_date": candidate.published_date,
                    "summary_zh": "这是一条关于气候金融政策含义的中文摘要。",
                    "summary_en": "This is an English brief on climate finance policy.",
                    "why_it_matters_zh": "它影响气候资金安排。",
                    "why_it_matters_en": "It matters for climate finance arrangements.",
                    "terms": [],
                    "tags": ["#气候金融"],
                    "sdg_links": ["SDG 13 Climate Action"],
                    "url": candidate.url,
                }
            ],
            "readings": [
                {
                    "title": "Invented classic",
                    "authors": "Nobody",
                    "year": 2020,
                    "url": "https://example.org/invented",
                    "note_zh": "这不是白名单材料。",
                    "note_en": "This is not approved.",
                    "argument_zh": "未知。",
                    "argument_en": "Unknown.",
                    "method_zh": "未知。",
                    "method_en": "Unknown.",
                    "evidence_zh": "未知。",
                    "evidence_en": "Unknown.",
                    "relevance_zh": "未知。",
                    "relevance_en": "Unknown.",
                    "tags": ["#气候金融"],
                    "kind": "paper",
                }
            ],
        }

        with self.assertRaises(ValueError):
            validate_digest_payload(payload, [candidate], {}, date(2026, 6, 9))

    def test_fallback_uses_bibliography_for_separate_readings(self) -> None:
        candidate = _candidate()
        reading = DeepRead(
            "A climate finance accounting framework",
            "Roberts et al.",
            2021,
            "https://doi.org/x",
            tags=["#气候金融"],
            kind="paper",
        )

        digest = fallback_digest([candidate], {"#气候金融": [reading]}, date(2026, 6, 9))

        self.assertEqual(digest.readings[0].title, reading.title)
        self.assertEqual(digest.items[0].deep_reads, [])
        self.assertIn("Climate Finance Update", digest.items[0].summary_zh)
        self.assertIn("Climate Finance Update", digest.items[0].summary_en)
        self.assertTrue(digest.items[0].why_it_matters_en)
        self.assertTrue(digest.readings[0].argument_en)


def _candidate() -> Candidate:
    return Candidate(
        title="Climate Finance Update",
        source_org="World Bank Climate",
        source_type="international_org",
        published_date="2026-06-09",
        url="https://worldbank.org/en/topic/climatechange",
        summary_hint="The update discusses finance for low-carbon and climate-resilient development.",
        tags=["#气候金融"],
        discovered_date="2026-06-09",
    )


if __name__ == "__main__":
    unittest.main()
