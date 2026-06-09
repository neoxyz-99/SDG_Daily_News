from __future__ import annotations

from datetime import date
import unittest

from sdg_digest.models import DeepRead, Digest, DigestItem, DigestTerm, FurtherReading
from sdg_digest.render import render_html, render_markdown


class RenderTests(unittest.TestCase):
    def test_render_markdown_and_html_include_redesigned_sections(self) -> None:
        digest = Digest(
            digest_date=date(2026, 6, 9),
            subject="The Governance Brief - 2026-06-09",
            overview_zh="气候融资与治理议程同步推进。",
            overview_en="This line should not be displayed in the header.",
            items=[
                DigestItem(
                    title_en="Climate finance update",
                    source_org="UNFCCC News",
                    published_date="2026-06-09",
                    summary_zh="这条更新讨论气候融资工具如何影响发展中国家的项目融资、政策执行和长期财政空间，尤其强调公共资金、私人资本和多边机构之间的协调问题。",
                    summary_en="The update highlights how climate finance arrangements support NDC implementation, project preparation, and coordination between public finance and private capital.",
                    why_it_matters_zh="它关系到发展中国家能否把气候目标转化为可执行的投资计划。",
                    why_it_matters_en="It matters for developing countries' ability to finance and implement climate pledges.",
                    terms=[
                        DigestTerm(
                            term_en="NDC",
                            term_zh="国家自主贡献",
                            explanation_zh="各国在《巴黎协定》下提交的减排和适应承诺。",
                        )
                    ],
                    tags=["#NDC", "#气候金融"],
                    sdg_links=["SDG 13 Climate Action"],
                    url="https://unfccc.int/news/example",
                )
            ],
            readings=[
                DeepRead(
                    title="Climate Change and the Global South",
                    authors="Saleemul Huq and Hannah Reid",
                    year=2004,
                    url="https://doi.org/10.1080/14693062.2004.9685516",
                    note_zh="Huq 与 Reid 讨论全球南方为何在气候变化中处于高度脆弱的位置：这些国家历史排放较少，却更容易遭受农业、水资源、贫困和适应能力不足带来的复合风险。文章的贡献在于把气候政策从单纯减排议题拉回发展议题，强调适应、贫困减缓和国际支持必须被放在同一分析框架中。",
                    note_en="A classic climate and development reading.",
                    journal="Climate Policy",
                    doi="10.1080/14693062.2004.9685516",
                    methodology_zh="文章采用政策分析与发展研究综合讨论，结合脆弱性、适应能力和南北责任差异来解释气候风险分布；这种方法适合提出制度性判断，但不能替代量化因果识别。",
                    today_relevance_en="It matters today because adaptation news often reveals deeper development constraints.",
                    further_reading=[
                        FurtherReading(
                            title="Adaptation to climate change in the developing world",
                            authors="Huq et al.",
                            year=2003,
                            description_zh="这篇文章延伸了适应能力与发展约束之间的关系。",
                            url="https://doi.org/example",
                        )
                    ],
                    tags=["#Global South", "#发展不平等"],
                    kind="journal article",
                )
            ],
        )

        markdown = render_markdown(digest)
        html = render_html(digest)

        self.assertIn("The Governance Brief", markdown)
        self.assertIn("今日新闻", markdown)
        self.assertIn("摘要", markdown)
        self.assertIn("方法论 / Methodology", markdown)
        self.assertIn("延伸阅读 / Further Reading", markdown)
        self.assertIn("2026-06-09", html)
        self.assertIn("header-pattern", html)
        self.assertIn("The Governance Brief", html)
        self.assertIn("气候融资与治理议程同步推进。", html)
        self.assertIn("article.news", html)
        self.assertIn("#f7f9f7", html)
        self.assertIn("方法论 / Methodology", html)
        self.assertIn("延伸阅读 / Further Reading", html)
        self.assertIn("today-note", html)
        self.assertNotIn("SDG Daily Digest", html)
        self.assertNotIn("This line should not be displayed in the header", html)
        self.assertNotIn("Argument", html)


if __name__ == "__main__":
    unittest.main()
