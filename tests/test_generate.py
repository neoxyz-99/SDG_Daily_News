from __future__ import annotations

from dataclasses import replace
from datetime import date
import os
import unittest
from unittest.mock import patch

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

    def test_stage_one_excludes_only_obvious_noise(self) -> None:
        noisy = replace(_candidate(), title="World Cup NBA match result")
        substantive = _candidate_two()

        result = filter_relevant_candidates([noisy, substantive], use_openai=False)

        self.assertEqual(result, [substantive])

    def test_semantic_filter_keeps_borderline_items_when_clear_passes_are_few(self) -> None:
        clear = _candidate()
        borderline = _candidate_two()
        rejected = replace(_candidate(), title="Lifestyle product launch", url="https://example.org/lifestyle")

        def score(candidate: Candidate) -> Candidate:
            if candidate is clear:
                return replace(candidate, semantic_score=2, semantic_domain="D", semantic_reason="Substantive finance item", tags=["#可持续金融与ESG"])
            if candidate is borderline:
                return replace(candidate, semantic_score=1, semantic_domain="B", semantic_reason="Thin but relevant", tags=["#发展与不平等"])
            return replace(candidate, semantic_score=0, semantic_domain="mixed", semantic_reason="Not relevant", tags=["#综合治理议题"])

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch(
            "sdg_digest.generate._score_candidate_semantically",
            side_effect=score,
        ):
            result = filter_relevant_candidates([clear, borderline, rejected], use_openai=True)

        self.assertEqual([candidate.title for candidate in result], [clear.title, borderline.title])
        self.assertEqual([candidate.semantic_score for candidate in result], [2, 1])
        self.assertEqual(result[0].tags[0], "#可持续金融与ESG")

    def test_validation_skips_invented_candidate_url_without_failing_issue(self) -> None:
        candidate = _candidate()
        payload = _payload(candidate)
        payload["items"][0]["url"] = "https://invented.example/article"

        digest = validate_digest_payload(payload, [candidate, _candidate_two()], {}, date(2026, 6, 9))

        self.assertEqual(digest.items, [])
        self.assertEqual(digest.overview_zh, "")

    def test_validation_filters_broad_tags_without_failing_issue(self) -> None:
        candidate = _candidate()
        payload = _payload(candidate)
        payload["items"][0]["tags"] = ["#气候变化"]

        digest = validate_digest_payload(payload, [candidate, _candidate_two()], {}, date(2026, 6, 9))

        self.assertNotIn("#气候变化", digest.items[0].tags)
        self.assertEqual(digest.items[0].tags, ["#综合治理议题"])

    def test_daily_note_is_omitted_when_only_one_news_item_is_selected(self) -> None:
        candidate = _candidate()
        payload = _payload(candidate)

        digest = validate_digest_payload(payload, [candidate], {}, date(2026, 6, 9))

        self.assertEqual(digest.overview_zh, "")
        self.assertEqual(len(digest.items), 1)

    def test_validation_includes_semantic_domain_tag(self) -> None:
        candidate = replace(_candidate(), tags=["#可持续金融与ESG"], semantic_score=2, semantic_domain="D")
        payload = _payload(candidate)
        payload["items"][0]["tags"] = ["#气候金融"]

        digest = validate_digest_payload(payload, [candidate], {}, date(2026, 6, 9))

        self.assertEqual(digest.items[0].tags[:2], ["#可持续金融与ESG", "#气候金融"])

    def test_validation_limits_research_signals_per_source(self) -> None:
        first = replace(_candidate(), title="Carbon Brief item one", source_org="Carbon Brief", url="https://www.carbonbrief.org/one")
        second = replace(_candidate(), title="Carbon Brief item two", source_org="Carbon Brief", url="https://www.carbonbrief.org/two")
        third = replace(_candidate(), title="Carbon Brief item three", source_org="Carbon Brief", url="https://www.carbonbrief.org/three")
        payload = _payload(first)
        payload["items"] = [_item(first), _item(second), _item(third)]

        digest = validate_digest_payload(payload, [first, second, third], {}, date(2026, 6, 9))

        self.assertEqual(len(digest.items), 2)
        self.assertEqual([item.source_org for item in digest.items], ["Carbon Brief", "Carbon Brief"])

    def test_validation_preserves_approved_reading_brief_and_adds_research_directions(self) -> None:
        first = _candidate()
        second = _candidate_two()
        reading = _reading()
        payload = _payload(first, second)
        payload["readings"] = [
            {
                "title": reading.title,
                "authors": reading.authors,
                "year": reading.year,
                "journal": reading.journal,
                "doi": reading.doi,
                "today_connection_zh": "这篇文献有助于理解 Climate Finance Update 中公共资金承诺与报告激励之间的张力。",
                "today_connection_en": "This reading helps interpret the tension between public finance pledges and reporting incentives in Climate Finance Update.",
                "research_directions": [
                    {
                        "question_zh": "气候资金如何被标记",
                        "question_en": "How is climate finance labeled?",
                        "keywords": ["climate finance", "aid reporting", "Rio markers"],
                    },
                    {
                        "question_zh": "承诺与拨付如何错位",
                        "question_en": "How do pledges and disbursement diverge?",
                        "keywords": ["pledges", "disbursement", "climate aid"],
                    },
                ],
            }
        ]

        digest = validate_digest_payload(payload, [first, second], {"#气候金融": [reading]}, date(2026, 6, 9))

        self.assertEqual(digest.readings[0].note_zh, reading.note_zh)
        self.assertEqual(digest.readings[0].journal, "World Development")
        self.assertIn("公共资金承诺", digest.readings[0].today_connection_zh)
        self.assertEqual(len(digest.readings[0].research_directions), 2)

    def test_fallback_uses_editorial_fields(self) -> None:
        candidate = _candidate()
        reading = _reading()

        digest = fallback_digest([candidate], {"#气候金融": [reading]}, date(2026, 6, 9))

        self.assertEqual(digest.readings[0].title, reading.title)
        self.assertEqual(digest.items[0].agenda_position_zh, "议程背景不明确")
        self.assertTrue(digest.items[0].core_argument_zh)
        self.assertEqual(digest.overview_zh, "")


def _payload(first: Candidate, second: Candidate | None = None) -> dict:
    items = [_item(first)]
    if second:
        items.append(_item(second))
    return {
        "daily_editorial_note_zh": "公共资金承诺与执行能力之间的落差，正在重塑气候融资议程的责任边界。",
        "weekly_editorial_note_en": "The gap between public finance pledges and delivery capacity is reshaping responsibility in climate finance.",
        "weekly_thread_zh": "两条新闻共同指向气候融资从承诺规模转向执行能力的议题线索。",
        "weekly_thread_en": "The two items point to a shift in climate finance debates from pledge volume to implementation capacity.",
        "items": items,
        "readings": [],
    }


def _item(candidate: Candidate) -> dict:
    return {
        "title_en": candidate.title,
        "source_org": candidate.source_org,
        "published_date": candidate.published_date,
        "core_argument_zh": "这篇文章主张，气候融资的关键矛盾不只是资金规模，而是公共机构能否把承诺转化为可执行的项目管线。",
        "core_argument_en": "The article argues that the central climate finance problem is not only the scale of funding, but whether public institutions can turn pledges into executable project pipelines.",
        "why_now_zh": "它回应了发展中国家在新一轮气候融资安排中对项目准备和风险分担的压力，也挑战了只看承诺金额的评估方式。",
        "why_now_en": "It responds to pressure on developing countries to prepare projects and share risks under new climate finance arrangements, while challenging assessments focused only on pledged amounts.",
        "agenda_position_zh": "它更像是气候融资执行阶段的政策诊断，而不是谈判前的立场表态。",
        "agenda_position_en": "It functions more as a policy diagnosis for the implementation phase of climate finance than as a pre-negotiation position statement.",
        "tags": ["#气候金融", "#多边治理"],
        "url": candidate.url,
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


def _candidate_two() -> Candidate:
    return Candidate(
        title="Water finance and climate adaptation",
        source_org="IISD SDG Knowledge Hub",
        source_type="think_tank",
        published_date="2026-06-09",
        url="https://sdg.iisd.org/example",
        summary_hint=(
            "The article examines how water finance gaps affect climate adaptation, infrastructure planning, "
            "public investment, and development policy coordination across institutions."
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
        note_en="The article examines statistical bias in climate aid reporting and shows how donor governments label and present development assistance as climate-related finance.",
        journal="World Development",
        doi="10.1016/j.worlddev.2011.07.020",
        methodology_zh="文章采用政治经济学分析与报告制度比较，优势是揭示资金统计背后的激励结构，局限是难以直接估计每一笔资金的真实气候贡献。",
        method_en="The article combines political economy analysis with scrutiny of reporting rules, revealing incentives behind climate finance statistics.",
        tags=["#气候金融"],
        kind="journal article",
    )


if __name__ == "__main__":
    unittest.main()
