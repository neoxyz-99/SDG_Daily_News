from __future__ import annotations

from datetime import date
import unittest

from sdg_digest.models import DeepRead, Digest, DigestItem, ResearchDirection
from sdg_digest.render import render_html, render_markdown


class RenderTests(unittest.TestCase):
    def test_render_markdown_and_html_include_editorial_brief_structure(self) -> None:
        digest = Digest(
            digest_date=date(2026, 6, 9),
            subject="SDG Weekly Compass - 2026-06-09",
            overview_zh="公共资金承诺与执行能力之间的落差，正在重塑气候融资议程的责任边界。",
            overview_en="The gap between public finance pledges and implementation capacity is reshaping climate finance responsibility.",
            weekly_thread_zh="两条新闻共同指向气候融资从承诺规模转向执行能力的议题线索。",
            weekly_thread_en="The items point to a shift from pledge volume toward implementation capacity in climate finance.",
            items=[
                DigestItem(
                    title_en="Climate finance update",
                    source_org="Climate Policy Initiative",
                    published_date="2026-06-09",
                    summary_zh="",
                    terms=[],
                    tags=["#气候金融", "#多边治理"],
                    url="https://climatepolicyinitiative.org/example",
                    core_argument_zh="这篇文章主张，气候融资的关键矛盾不只是资金规模，而是公共机构能否把承诺转化为项目管线。",
                    core_argument_en="The article argues that climate finance depends not only on funding scale, but on public institutions turning pledges into project pipelines.",
                    why_now_zh="它回应了发展中国家在新一轮气候融资安排中对项目准备和风险分担的压力。",
                    why_now_en="It responds to pressure on developing countries to prepare projects and manage risk-sharing under new climate finance arrangements.",
                    agenda_position_zh="它更像是气候融资执行阶段的政策诊断，而不是谈判前的立场表态。",
                    agenda_position_en="It is a policy diagnosis for the implementation phase of climate finance rather than a pre-negotiation position statement.",
                )
            ],
            readings=[
                DeepRead(
                    title="Climate Change and the Global South",
                    authors="Saleemul Huq and Hannah Reid",
                    year=2004,
                    url="https://doi.org/10.1080/14693062.2004.9685516",
                    note_zh="Huq 与 Reid 讨论全球南方为何在气候变化中处于高度脆弱的位置：这些国家历史排放较少，却更容易遭受农业、水资源、贫困和适应能力不足带来的复合风险。文章的贡献在于把气候政策从单纯减排议题拉回发展议题，强调适应、贫困减缓和国际支持必须被放在同一分析框架中。",
                    note_en="Huq and Reid show that climate vulnerability in the Global South is produced through development constraints, fiscal capacity, and unequal responsibility.",
                    journal="Climate Policy",
                    doi="10.1080/14693062.2004.9685516",
                    methodology_zh="文章采用政策分析与发展研究综合讨论，结合脆弱性、适应能力和南北责任差异来解释气候风险分布；这种方法适合提出制度性判断，但不能替代量化因果识别。",
                    method_en="The article uses policy synthesis and vulnerability analysis to connect climate impacts with development constraints.",
                    today_connection_zh="这篇文献有助于理解 Climate finance update 中融资安排与发展能力之间的结构性张力。",
                    today_connection_en="This reading helps interpret the structural tension between finance arrangements and development capacity in Climate finance update.",
                    research_directions=[
                        ResearchDirection(
                            question_zh="适应资金如何分配",
                            keywords=["adaptation finance", "allocation", "vulnerability"],
                            question_en="How is adaptation finance allocated?",
                        ),
                        ResearchDirection(
                            question_zh="发展能力如何影响适应",
                            keywords=["development capacity", "adaptation", "institutions"],
                            question_en="How does development capacity shape adaptation?",
                        ),
                    ],
                    tags=["#Global South", "#发展不平等"],
                    kind="journal article",
                )
            ],
        )

        markdown = render_markdown(digest)
        html = render_html(digest)

        self.assertIn("SDG Weekly Compass", markdown)
        self.assertIn("本周导语", markdown)
        self.assertIn("近期要闻", markdown)
        self.assertIn("研究动向", markdown)
        self.assertIn("经典研读", markdown)
        self.assertIn("核心论点 / Core Argument", markdown)
        self.assertIn("为什么此刻重要 / Why Now", markdown)
        self.assertIn("议程位置 / Agenda Position", markdown)
        self.assertIn("本周议题线索", markdown)
        self.assertIn("今日关联 / Today's Connection", markdown)
        self.assertIn("研究方向 / Research Directions", markdown)
        self.assertIn("implementation capacity", markdown)
        self.assertIn("header-pattern", html)
        self.assertIn("recent-card", html)
        self.assertIn("research-card", html)
        self.assertIn("editorial-note", html)
        self.assertIn("weekly-thread", html)
        self.assertIn("研究动向", html)
        self.assertIn("核心论点 / Core Argument", html)
        self.assertIn("研究方向 / Research Directions", html)
        self.assertIn("The article argues that climate finance", html)
        self.assertNotIn("/ Recent News ·", html)
        self.assertNotIn("/ Research Signals ·", html)
        self.assertNotIn("/ Classic Reading ·", html)
        self.assertNotIn("SDG Daily Digest", html)
        self.assertNotIn("The Governance Brief", html)
        self.assertNotIn("English Brief", html)


if __name__ == "__main__":
    unittest.main()
