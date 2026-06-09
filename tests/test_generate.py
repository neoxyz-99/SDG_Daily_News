from __future__ import annotations

from datetime import date
import os
import unittest

from sdg_digest.generate import fallback_digest, filter_relevant_candidates, generate_digest, validate_digest_payload
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

    def test_relevance_filter_can_be_skipped_for_local_tests(self) -> None:
        candidate = _candidate()

        result = filter_relevant_candidates([candidate], use_openai=False)

        self.assertEqual(result, [candidate])

    def test_validation_rejects_invented_url(self) -> None:
        candidate = _candidate()
        payload = _payload(candidate)
        payload["items"][0]["url"] = "https://invented.example/article"

        with self.assertRaises(ValueError):
            validate_digest_payload(payload, [candidate], {}, date(2026, 6, 9))

    def test_validation_rejects_unapproved_reading(self) -> None:
        candidate = _candidate()
        payload = _payload(candidate)
        payload["readings"] = [
            {
                "title": "Invented classic",
                "authors": "Nobody",
                "year": 2020,
                "journal": "World Development",
                "doi": "10.0000/invented",
                "today_relevance_en": "It matters today.",
            }
        ]

        with self.assertRaises(ValueError):
            validate_digest_payload(payload, [candidate], {"#气候金融": [_reading()]}, date(2026, 6, 9))

    def test_validation_preserves_approved_reading_brief(self) -> None:
        candidate = _candidate()
        reading = _reading()
        payload = _payload(candidate)
        payload["readings"] = [
            {
                "title": reading.title,
                "authors": reading.authors,
                "year": reading.year,
                "journal": reading.journal,
                "doi": reading.doi,
                "today_relevance_en": "It matters today because climate finance claims still need careful accounting.",
            }
        ]

        digest = validate_digest_payload(payload, [candidate], {"#气候金融": [reading]}, date(2026, 6, 9))

        self.assertEqual(digest.readings[0].note_zh, reading.note_zh)
        self.assertEqual(digest.readings[0].journal, "World Development")
        self.assertIn("climate finance claims", digest.readings[0].today_relevance_en)

    def test_validation_allows_shorter_summary_when_candidate_pool_is_tiny(self) -> None:
        candidate = _candidate()
        payload = _payload(candidate)
        payload["items"][0]["summary_zh"] = (
            "这条更新讨论水资源融资缺口如何影响气候适应、公共投资和发展中国家的基础设施规划，"
            "并指出长期项目准备、风险分担和机构协调会影响资金能否真正落地，"
            "也提示多边开发机构需要改善项目管线和本地执行能力。"
        )
        payload["items"][0]["summary_en"] = (
            "This update examines how a water finance gap affects adaptation, public investment, "
            "project preparation, risk sharing, and institutional coordination in developing countries. "
            "It also shows why multilateral development banks and local agencies need stronger pipelines."
        )

        digest = validate_digest_payload(payload, [candidate], {}, date(2026, 6, 9))

        self.assertEqual(len(digest.items), 1)
        self.assertIn("水资源融资缺口", digest.items[0].summary_zh)

    def test_fallback_uses_bibliography_for_separate_readings(self) -> None:
        candidate = _candidate()
        reading = _reading()

        digest = fallback_digest([candidate], {"#气候金融": [reading]}, date(2026, 6, 9))

        self.assertEqual(digest.readings[0].title, reading.title)
        self.assertEqual(digest.items[0].deep_reads, [])
        self.assertIn("Climate Finance Update", digest.items[0].title_en)
        self.assertTrue(digest.items[0].why_it_matters_en)


def _payload(candidate: Candidate) -> dict:
    return {
        "overview_zh": "今日关注气候金融和发展政策。",
        "overview_en": "Today focuses on climate finance and development policy.",
        "items": [
            {
                "title_en": candidate.title,
                "source_org": candidate.source_org,
                "published_date": candidate.published_date,
                "summary_zh": "这条更新讨论气候金融工具如何影响发展中国家的项目融资、政策执行和长期财政空间，尤其强调公共资金、私营资本和多边机构之间的协调问题。它进一步说明，融资安排并不只是资金规模问题，也关系到项目准备、风险分担和多边机构能否把气候承诺转化为可执行投资。",
                "summary_en": "This update examines how climate finance tools affect project finance, policy implementation, and fiscal space in developing countries, with particular attention to the coordination between public funding, private capital, and multilateral institutions. It also shows why project preparation, risk sharing, and credible public institutions matter for turning climate commitments into investable programmes.",
                "why_it_matters_zh": "它关系到发展中国家能否把气候目标转化为可执行的投资计划。",
                "why_it_matters_en": "It matters because climate commitments depend on credible investment pipelines and institutions that can mobilize finance.",
                "terms": [],
                "tags": ["#气候金融"],
                "sdg_links": ["SDG 13 Climate Action"],
                "url": candidate.url,
            }
        ],
        "readings": [],
    }


def _candidate() -> Candidate:
    return Candidate(
        title="Climate Finance Update",
        source_org="Climate Policy Initiative",
        source_type="think_tank",
        published_date="2026-06-09",
        url="https://climatepolicyinitiative.org/example",
        summary_hint=(
            "The update discusses finance for low-carbon and climate-resilient development, including "
            "public funding, multilateral development banks, project pipelines, and private capital mobilization."
        ),
        tags=[],
        discovered_date="2026-06-09",
    )


def _reading() -> DeepRead:
    return DeepRead(
        title="Coding Error or Statistical Embellishment? The Political Economy of Reporting Climate Aid",
        authors="Axel Michaelowa and Katharina Michaelowa",
        year=2011,
        url="https://doi.org/10.1016/j.worlddev.2011.07.020",
        note_zh="这篇文章研究气候援助报告中的统计偏差，核心问题是捐助国如何在发展援助中标记、计算和呈现气候相关资金。作者指出，气候资金并非透明中性的数字，而是受到政治激励、报告规则和国际声誉竞争影响。它为判断气候金融承诺是否真实、额外和可追踪提供了重要背景。",
        journal="World Development",
        doi="10.1016/j.worlddev.2011.07.020",
        tags=["#气候金融"],
        kind="journal article",
    )


if __name__ == "__main__":
    unittest.main()
