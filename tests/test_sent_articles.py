from __future__ import annotations

from datetime import date
import json
import tempfile
import unittest
from pathlib import Path

from sdg_digest.models import Digest, DigestItem
from sdg_digest.sent_articles import filter_sent_candidates, load_sent_articles, update_sent_articles
from tests.test_generate import _candidate, _candidate_two


class SentArticlesTests(unittest.TestCase):
    def test_load_sent_articles_creates_file_if_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sent_articles.json"

            record = load_sent_articles(path)

            self.assertTrue(path.exists())
            self.assertEqual(
                record,
                {
                    "sent_urls": [],
                    "recent_news_urls": [],
                    "research_signal_urls": [],
                    "last_updated": "",
                },
            )

    def test_filter_sent_candidates_removes_previously_sent_urls(self) -> None:
        first = _candidate()
        second = _candidate_two()
        record = {"sent_urls": [first.url], "last_updated": "2026-06-09"}

        unseen, filtered = filter_sent_candidates([first, second], record)

        self.assertEqual(filtered, 1)
        self.assertEqual([candidate.url for candidate in unseen], [second.url])

    def test_update_sent_articles_appends_urls_and_keeps_rolling_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sent_articles.json"
            path.write_text(
                json.dumps({"sent_urls": [f"https://example.org/{i}" for i in range(499)], "last_updated": ""}),
                encoding="utf-8",
            )
            digest = Digest(
                digest_date=date(2026, 6, 9),
                subject="The Governance Brief - 2026-06-09",
                overview_zh="",
                items=[
                    DigestItem(
                        title_en="First",
                        source_org="Source",
                        published_date="2026-06-09",
                        summary_zh="",
                        terms=[],
                        tags=["#气候金融"],
                        url="https://example.org/499",
                    ),
                    DigestItem(
                        title_en="Second",
                        source_org="Source",
                        published_date="2026-06-09",
                        summary_zh="",
                        terms=[],
                        tags=["#气候金融"],
                        url="https://example.org/500",
                    ),
                ],
            )

            record = update_sent_articles(digest, date(2026, 6, 9), path)

            self.assertEqual(record["last_updated"], "2026-06-09")
            self.assertEqual(len(record["sent_urls"]), 500)
            self.assertNotIn("https://example.org/0", record["sent_urls"])
            self.assertIn("https://example.org/500", record["sent_urls"])


if __name__ == "__main__":
    unittest.main()
