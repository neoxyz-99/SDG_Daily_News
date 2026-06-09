from __future__ import annotations

import unittest

from sdg_digest.collect import _extract_page_summary, deduplicate_candidates, is_allowed_url, rank_candidates
from sdg_digest.models import Candidate


class CollectTests(unittest.TestCase):
    def test_allowed_url_accepts_subdomains(self) -> None:
        self.assertTrue(is_allowed_url("https://blogs.worldbank.org/en/post", ["worldbank.org"]))
        self.assertTrue(is_allowed_url("https://www.unfccc.int/news", ["unfccc.int"]))

    def test_allowed_url_rejects_unapproved_domain(self) -> None:
        self.assertFalse(is_allowed_url("https://example.com/climate-finance", ["worldbank.org"]))
        self.assertFalse(is_allowed_url("not-a-url", ["worldbank.org"]))

    def test_deduplicate_candidates_by_url_title_and_doi(self) -> None:
        first = _candidate("Climate finance for adaptation", "https://doi.org/10.123/a", doi="10.123/a")
        same_url = _candidate("Different title", "https://doi.org/10.123/a?utm=x")
        same_title = _candidate("Climate finance for adaptation!", "https://example.org/other")
        same_doi = _candidate("Another", "https://doi.org/10.123/a-alt", doi="10.123/a")
        unique = _candidate("Debt and climate risks", "https://example.org/debt")

        result = deduplicate_candidates([first, same_url, same_title, same_doi, unique])

        self.assertEqual([item.url for item in result], [first.url, unique.url])

    def test_rank_prefers_relevant_source_and_keywords(self) -> None:
        plain = _candidate("General update", "https://example.org/a", source_type="think_tank", tags=[])
        rich = _candidate(
            "Climate finance and NDC debt sustainability",
            "https://example.org/b",
            source_type="journal",
            tags=["#气候金融", "#NDC"],
        )

        result = rank_candidates([plain, rich], max_items=1)

        self.assertEqual(result[0].url, rich.url)

    def test_extract_page_summary_prefers_meta_description(self) -> None:
        html = """
        <html>
          <head>
            <meta name="description" content="A climate policy update with concrete finance and resilience implications for developing countries.">
          </head>
          <body><p>Fallback paragraph that should not be used first.</p></body>
        </html>
        """

        self.assertIn("climate policy update", _extract_page_summary(html))


def _candidate(
    title: str,
    url: str,
    doi: str | None = None,
    source_type: str = "journal",
    tags: list[str] | None = None,
) -> Candidate:
    return Candidate(
        title=title,
        source_org="Source",
        source_type=source_type,
        published_date="2026-06-09",
        url=url,
        summary_hint="",
        tags=tags or ["#气候金融"],
        discovered_date="2026-06-09",
        doi=doi,
    )


if __name__ == "__main__":
    unittest.main()
