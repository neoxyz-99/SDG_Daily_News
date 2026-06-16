from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from sdg_digest.collect import CollectionStats, collect_candidates, deduplicate_candidates, is_allowed_url, rank_candidates
from sdg_digest.models import Candidate, Source


class CollectTests(unittest.TestCase):
    def test_allowed_url_accepts_subdomains(self) -> None:
        self.assertTrue(is_allowed_url("https://www.carbonbrief.org/post", ["carbonbrief.org"]))
        self.assertTrue(is_allowed_url("https://unfccc.int/news/example", ["unfccc.int"]))

    def test_allowed_url_rejects_unapproved_domain(self) -> None:
        self.assertFalse(is_allowed_url("https://example.com/climate-finance", ["carbonbrief.org"]))
        self.assertFalse(is_allowed_url("not-a-url", ["carbonbrief.org"]))

    def test_rss_collection_skips_short_feed_summaries(self) -> None:
        source = Source(
            name="Carbon Brief",
            type="think_tank",
            strategy="rss",
            allowed_domains=["carbonbrief.org"],
            default_tags=[],
            url="https://www.carbonbrief.org/feed/",
        )
        feed = """<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>Climate policy update</title>
            <link>https://www.carbonbrief.org/climate-policy-update</link>
            <pubDate>Tue, 09 Jun 2026 12:00:00 GMT</pubDate>
            <description>Too short.</description>
          </item>
          <item>
            <title>Detailed climate finance analysis</title>
            <link>https://www.carbonbrief.org/detailed-climate-finance-analysis</link>
            <pubDate>Tue, 09 Jun 2026 12:00:00 GMT</pubDate>
            <description>This analysis explains how public finance, development banks, debt pressure, project pipelines, policy credibility, private capital mobilization, adaptation needs, and institutional coordination shape the delivery of climate finance in developing economies over the next decade. It also reviews how national planning systems, concessional lending, risk guarantees, and multilateral institutions affect whether climate commitments become credible investment programmes.</description>
          </item>
        </channel></rss>
        """

        with patch("sdg_digest.collect.fetch_text", return_value=feed):
            result = collect_candidates([source], date(2026, 6, 9), lookback_days=3)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Detailed climate finance analysis")
        self.assertEqual(result[0].tags, [])

    def test_deduplicate_candidates_by_exact_url_then_title_similarity(self) -> None:
        first = _candidate("Climate finance for adaptation", "https://example.org/a")
        same_url = _candidate("Different title", "https://example.org/a?utm=x")
        same_title = _candidate("Climate finance for adaptation!", "https://example.org/other")
        unique = _candidate("Debt and climate risks", "https://example.org/debt")

        result = deduplicate_candidates([first, same_url, same_title, unique])

        self.assertEqual([item.url for item in result], [first.url, unique.url])

    def test_rank_prefers_richer_feed_summary(self) -> None:
        thin = _candidate("Climate finance update", "https://example.org/thin", summary_hint="Short update.")
        rich = _candidate(
            "Climate finance update",
            "https://example.org/rich",
            summary_hint=(
                "This update explains how a climate finance facility supports developing countries "
                "through concessional finance, technical assistance, results-based payments, and "
                "policy reforms that connect emissions reduction with resilience and fiscal capacity. "
                "It identifies implementing agencies, funding mechanisms, and implications for NDC delivery. "
                "It also describes how public institutions coordinate with private investors and local governments."
            ),
        )

        result = rank_candidates([thin, rich], max_items=1)

        self.assertEqual(result[0].url, rich.url)

    def test_rank_can_limit_items_per_source_for_diversity(self) -> None:
        first_guardian = _candidate(
            "Guardian rich climate item one",
            "https://example.org/guardian-1",
            source_org="The Guardian Environment",
            summary_hint=" ".join(["climate"] * 100),
        )
        second_guardian = _candidate(
            "Guardian rich climate item two",
            "https://example.org/guardian-2",
            source_org="The Guardian Environment",
            summary_hint=" ".join(["climate"] * 90),
        )
        third_guardian = _candidate(
            "Guardian rich climate item three",
            "https://example.org/guardian-3",
            source_org="The Guardian Environment",
            summary_hint=" ".join(["climate"] * 80),
        )
        ap_item = _candidate(
            "AP climate item",
            "https://example.org/ap",
            source_org="Associated Press Climate and Environment",
            summary_hint=" ".join(["climate"] * 20),
        )

        result = rank_candidates(
            [first_guardian, second_guardian, third_guardian, ap_item],
            max_items=3,
            max_per_source=2,
        )

        self.assertEqual(
            [item.source_org for item in result],
            ["The Guardian Environment", "The Guardian Environment", "Associated Press Climate and Environment"],
        )

    def test_rank_can_disable_same_source_backfill(self) -> None:
        candidates = [
            _candidate(
                f"Carbon Brief item {index}",
                f"https://example.org/carbon-{index}",
                source_org="Carbon Brief",
                summary_hint=" ".join(["climate"] * (100 - index)),
            )
            for index in range(5)
        ]

        result = rank_candidates(candidates, max_items=5, max_per_source=2, fill_to_max=False)

        self.assertEqual(len(result), 2)
        self.assertTrue(all(item.source_org == "Carbon Brief" for item in result))

    def test_whitelisted_source_attempts_full_text_extraction(self) -> None:
        source = Source(
            name="IISD SDG Knowledge Hub",
            type="think_tank",
            strategy="rss",
            allowed_domains=["sdg.iisd.org"],
            default_tags=[],
            url="https://sdg.iisd.org/feed/",
        )
        feed = """<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>Water finance policy update</title>
            <link>https://sdg.iisd.org/commentary/policy-briefs/water-finance-policy-update</link>
            <pubDate>Tue, 09 Jun 2026 12:00:00 GMT</pubDate>
            <description>This policy update explains how water finance gaps affect adaptation, public investment, project pipelines, institutional coordination, risk sharing, development planning, climate resilience, and multilateral finance. It reviews how public agencies and development partners connect infrastructure needs with financing instruments and policy implementation across sectors. The article also discusses implementation capacity, concessional resources, local planning systems, accountability, and the role of international institutions in translating commitments into practical investment programmes.</description>
          </item>
        </channel></rss>
        """
        stats = CollectionStats()

        with patch("sdg_digest.collect.fetch_text", return_value=feed), patch(
            "sdg_digest.collect.extract_full_text",
            return_value=(
                "Executive summary: the report argues that public agencies need stronger project "
                "pipelines, blended finance tools, and institutional coordination to close water "
                "finance gaps while protecting climate adaptation priorities. It describes how "
                "recipient governments, development banks, and local utilities can align concessional "
                "capital, guarantees, fiscal planning, and adaptation objectives so that water systems "
                "become investable without shifting all risks to vulnerable communities."
            ),
        ), patch("sdg_digest.collect.time.sleep"):
            result = collect_candidates([source], date(2026, 6, 9), lookback_days=3, stats=stats)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text_source, "full_text")
        self.assertIn("Executive summary", result[0].full_text)
        self.assertEqual(stats.full_text_sources, {"IISD SDG Knowledge Hub"})

    def test_short_research_rss_summary_can_be_rescued_by_full_text(self) -> None:
        source = Source(
            name="Climate Policy Initiative",
            type="think_tank",
            strategy="rss",
            allowed_domains=["climatepolicyinitiative.org"],
            default_tags=[],
            url="https://climatepolicyinitiative.org/feed/",
        )
        feed = """<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>Closing the water finance gap</title>
            <link>https://climatepolicyinitiative.org/publication/closing-the-water-finance-gap</link>
            <pubDate>Tue, 09 Jun 2026 12:00:00 GMT</pubDate>
            <description>Short summary.</description>
          </item>
        </channel></rss>
        """

        with patch("sdg_digest.collect.fetch_text", return_value=feed), patch(
            "sdg_digest.collect.extract_full_text",
            return_value=(
                "The report argues that water finance requires better institutional coordination, "
                "stronger project preparation, public risk sharing, and concessional instruments "
                "that can help recipient governments translate adaptation needs into investable "
                "pipelines without shifting costs to vulnerable communities. It also discusses "
                "how development banks, local utilities, fiscal authorities, and climate funds "
                "can align planning cycles, guarantees, revenue models, and adaptation objectives "
                "so that water infrastructure can attract capital while maintaining public accountability."
            ),
        ), patch("sdg_digest.collect.time.sleep"):
            result = collect_candidates([source], date(2026, 6, 9), lookback_days=7)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].text_source, "full_text")
        self.assertEqual(result[0].layer, "research")


def _candidate(title: str, url: str, summary_hint: str = "", source_org: str = "Source") -> Candidate:
    return Candidate(
        title=title,
        source_org=source_org,
        source_type="think_tank",
        published_date="2026-06-09",
        url=url,
        summary_hint=summary_hint,
        tags=[],
        discovered_date="2026-06-09",
    )


if __name__ == "__main__":
    unittest.main()
