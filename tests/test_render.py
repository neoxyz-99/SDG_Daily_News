from __future__ import annotations

from datetime import date
import unittest

from sdg_digest.models import DeepRead, Digest, DigestItem, DigestTerm
from sdg_digest.render import render_html, render_markdown


class RenderTests(unittest.TestCase):
    def test_render_markdown_and_html_include_news_and_redesigned_readings(self) -> None:
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
                    title="Climate Change and the Global South",
                    authors="Saleemul Huq and Hannah Reid",
                    year=2004,
                    url="https://doi.org/10.1080/14693062.2004.9685516",
                    note_zh="Huq 与 Reid 讨论全球南方为何在气候变化中处于高度脆弱的位置：这些国家历史排放较少，却更容易遭受农业、水资源、贫困和适应能力不足带来的复合风险。文章的贡献在于把气候政策从单纯减排议题拉回发展议题，强调适应、贫困削减和国际支持必须被放在同一分析框架中。",
                    journal="Climate Policy",
                    doi="10.1080/14693062.2004.9685516",
                    today_relevance_en="It matters today because disaster and adaptation news often reveal deeper development constraints.",
                    tags=["#Global South", "#发展不平等"],
                    kind="journal article",
                )
            ],
        )

        markdown = render_markdown(digest)
        html = render_html(digest)

        self.assertIn("今日新闻", markdown)
        self.assertIn("Climate finance update", markdown)
        self.assertIn("今日深读", markdown)
        self.assertIn("Climate Policy", markdown)
        self.assertIn("10.1080/14693062.2004.9685516", markdown)
        self.assertNotIn("Argument", markdown)
        self.assertNotIn("Method", markdown)
        self.assertIn("readings-band", html)
        self.assertIn("Climate Change and the Global South", html)
        self.assertIn("today-note", html)
        self.assertNotIn("reading-block", html)


if __name__ == "__main__":
    unittest.main()
