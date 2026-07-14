from __future__ import annotations

import json
from datetime import date
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from sdg_digest.academic import _fetch_crossref_works, collect_academic_readings, combine_academic_pool
from sdg_digest.models import Candidate, DeepRead, Source


class AcademicTracingTests(unittest.TestCase):
    def test_crossref_traces_recent_and_historical_papers_from_same_journal(self) -> None:
        source = Source(
            name="International Organization",
            type="journal",
            strategy="crossref",
            issn=["0020-8183"],
            allowed_domains=["api.crossref.org", "doi.org"],
            default_tags=["#国际治理与多边主义"],
            url="https://api.crossref.org",
            layer="academic",
        )
        recent = _work("10.1000/recent", "New Multilateral Bargains", [2026, 6, 12])
        classic = _work("10.1000/classic", "Institutions and Cooperation", [1984, 3, 1])

        def response(url: str) -> str:
            item = recent if "from-pub-date" in url else classic
            return json.dumps({"message": {"items": [item]}})

        with patch("sdg_digest.academic.fetch_text", side_effect=response), patch(
            "sdg_digest.academic.CROSSREF_REQUEST_DELAY_SECONDS",
            0,
        ):
            readings = collect_academic_readings(
                [source],
                [_candidate()],
                date(2026, 6, 16),
                lookback_days=90,
                recent_per_journal=1,
                classic_per_journal=1,
            )

        self.assertEqual([reading.doi for reading in readings], ["10.1000/recent", "10.1000/classic"])
        self.assertEqual(readings[0].kind, "tracked recent article")
        self.assertEqual(readings[0].published_date, "2026-06-12")
        self.assertEqual(readings[1].kind, "tracked classic article")
        self.assertEqual(readings[1].year, 1984)

    def test_curated_seven_are_samples_not_the_boundary(self) -> None:
        tracked = DeepRead(
            title="A newly discovered classic",
            authors="A. Scholar",
            year=1990,
            url="https://doi.org/10.1000/open-pool",
            doi="10.1000/open-pool",
            journal="World Politics",
            abstract_en="A sufficiently detailed abstract.",
            kind="tracked classic article",
        )
        sample = DeepRead(
            title="Seed example",
            authors="B. Scholar",
            year=1982,
            url="https://doi.org/10.1000/seed",
            doi="10.1000/seed",
            note_zh="人工核对过的样例解读。",
        )

        pool = combine_academic_pool([tracked], {"#多边治理": [sample]})
        all_dois = [reading.doi for readings in pool.values() for reading in readings]

        self.assertEqual(all_dois, ["10.1000/open-pool", "10.1000/seed"])

    def test_crossref_rate_limit_is_retried(self) -> None:
        rate_limit = HTTPError("https://api.crossref.org", 429, "Too Many Requests", None, None)
        success = json.dumps({"message": {"items": [{"DOI": "10.1000/retry"}]}})

        with patch("sdg_digest.academic.fetch_text", side_effect=[rate_limit, success]) as fetch, patch(
            "sdg_digest.academic.time.sleep"
        ):
            items = _fetch_crossref_works(
                "0020-8183",
                "global governance",
                "type:journal-article",
                1,
            )

        self.assertEqual(items[0]["DOI"], "10.1000/retry")
        self.assertEqual(fetch.call_count, 2)


def _work(doi: str, title: str, date_parts: list[int]) -> dict:
    return {
        "DOI": doi,
        "title": [title],
        "container-title": ["International Organization"],
        "published": {"date-parts": [date_parts]},
        "author": [{"given": "Alex", "family": "Scholar"}],
        "abstract": (
            "<jats:p>This article examines how international institutions organize bargaining, "
            "distribute authority, shape state preferences, and influence cooperation across policy areas. "
            "It develops a comparative argument about institutional design, political legitimacy, actor "
            "incentives, implementation constraints, and changes in the wider global governance order.</jats:p>"
        ),
    }


def _candidate() -> Candidate:
    return Candidate(
        title="Reforming multilateral development banks for climate finance",
        source_org="Policy source",
        source_type="think_tank",
        published_date="2026-06-15",
        url="https://example.org/item",
        summary_hint="A policy analysis of multilateral institutions and development finance.",
        tags=["#国际治理与多边主义", "#气候金融"],
        discovered_date="2026-06-16",
    )


if __name__ == "__main__":
    unittest.main()
