from __future__ import annotations

from datetime import date
import unittest

from sdg_digest.models import DeepRead, Digest, DigestItem, DigestTerm
from sdg_digest.render import render_html, render_markdown


class RenderTests(unittest.TestCase):
    def test_render_markdown_and_html_include_news_and_readings(self) -> None:
        digest = Digest(
            digest_date=date(2026, 6, 9),
            subject="SDG Daily Digest - 2026-06-09",
            overview_zh="今日关注 NDC 与气候金融。",
            overview_en="Today's brief focuses on NDCs and climate finance.",
            items=[
                DigestItem(
                    title_en="Climate finance update",
                    source_org="UNFCCC News",
                    published_date="2026-06-09",
                    summary_zh="该信息说明气候融资安排对发展中国家执行 NDC 的支持作用。",
                    summary_en="The update highlights how climate finance arrangements support NDC implementation.",
                    why_it_matters_zh="它关系到发展中国家的融资能力与气候承诺执行。",
                    why_it_matters_en="It matters for developing countries' ability to finance and implement climate pledges.",
                    terms=[
                        DigestTerm(
                            term_en="NDC",
                            term_zh="国家自主贡献",
                            explanation_zh="各国在巴黎协定下提交的减排和适应承诺。",
                        )
                    ],
                    tags=["#NDC", "#气候金融"],
                    sdg_links=["SDG 13 Climate Action"],
                    url="https://unfccc.int/news/example",
                )
            ],
            readings=[
                DeepRead(
                    title="The Paris Agreement",
                    authors="Rogelj et al.",
                    year=2016,
                    url="https://doi.org/10.1038/nclimate3031",
                    note_zh="适合作为理解 NDC 与全球温控目标之间张力的基础读物。",
                    note_en="Useful background for understanding the tension between NDCs and global temperature goals.",
                    argument_zh="文章讨论全球目标与国家贡献之间的不一致。",
                    argument_en="The article discusses inconsistencies between global goals and national contributions.",
                    method_zh="采用情景分析和政策比较。",
                    method_en="It uses scenario analysis and policy comparison.",
                    evidence_zh="以巴黎协定目标和各国承诺为例。",
                    evidence_en="It uses Paris Agreement goals and national pledges as evidence.",
                    relevance_zh="有助于理解今日 NDC 新闻的治理背景。",
                    relevance_en="It helps interpret today's NDC news in a broader governance context.",
                    tags=["#NDC"],
                    kind="paper",
                )
            ],
        )

        markdown = render_markdown(digest)
        html = render_html(digest)

        self.assertIn("今日新闻", markdown)
        self.assertIn("Climate finance update", markdown)
        self.assertIn("今日深读", markdown)
        self.assertIn("English brief", markdown)
        self.assertIn("The Paris Agreement", markdown)
        self.assertIn("今日新闻", html)
        self.assertIn("今日深读", html)
        self.assertIn("Why it matters", html)
        self.assertIn("Argument", html)
        self.assertIn("#NDC", html)


if __name__ == "__main__":
    unittest.main()
