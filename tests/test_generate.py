from __future__ import annotations

from datetime import date
import unittest

from sdg_digest.generate import fallback_digest, validate_digest_payload
from sdg_digest.models import Candidate, DeepRead


class GenerateTests(unittest.TestCase):
    def test_validation_rejects_invented_url(self) -> None:
        candidate = _candidate()
        payload = {
            "overview_zh": "今日关注气候金融。",
            "items": [
                {
                    "title_en": "Climate Finance Update",
                    "source_org": "World Bank Climate",
                    "published_date": "2026-06-09",
                    "summary_zh": "这是一条关于气候金融政策含义的中文摘要。",
                    "terms": [],
                    "tags": ["#气候金融"],
                    "url": "https://invented.example/article",
                    "deep_reads": [],
                }
            ],
        }

        with self.assertRaises(ValueError):
            validate_digest_payload(payload, [candidate], {}, date(2026, 6, 9))

    def test_validation_rejects_unapproved_deep_read(self) -> None:
        candidate = _candidate()
        payload = {
            "overview_zh": "今日关注气候金融。",
            "items": [
                {
                    "title_en": candidate.title,
                    "source_org": candidate.source_org,
                    "published_date": candidate.published_date,
                    "summary_zh": "这是一条关于气候金融政策含义的中文摘要。",
                    "terms": [],
                    "tags": ["#气候金融"],
                    "url": candidate.url,
                    "deep_reads": [
                        {
                            "title": "Invented classic",
                            "authors": "Nobody",
                            "year": 2020,
                            "url": "https://example.org/invented",
                        }
                    ],
                }
            ],
        }

        with self.assertRaises(ValueError):
            validate_digest_payload(payload, [candidate], {}, date(2026, 6, 9))

    def test_fallback_uses_bibliography_for_deep_reads(self) -> None:
        candidate = _candidate()
        reading = DeepRead("A climate finance accounting framework", "Roberts et al.", 2021, "https://doi.org/x")

        digest = fallback_digest([candidate], {"#气候金融": [reading]}, date(2026, 6, 9))

        self.assertEqual(digest.items[0].deep_reads, [reading])


def _candidate() -> Candidate:
    return Candidate(
        title="Climate Finance Update",
        source_org="World Bank Climate",
        source_type="international_org",
        published_date="2026-06-09",
        url="https://worldbank.org/en/topic/climatechange",
        summary_hint="climate finance",
        tags=["#气候金融"],
        discovered_date="2026-06-09",
    )


if __name__ == "__main__":
    unittest.main()
