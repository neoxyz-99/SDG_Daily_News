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
                _reading(
                    "The Paris Agreement",
                    "Rogelj et al.",
                    2016,
                    "https://doi.org/10.1038/nclimate3031",
                    ["#NDC"],
                ),
                _reading(
                    "A climate finance accounting framework",
                    "Roberts et al.",
                    2021,
                    "https://doi.org/10.1038/s41558-021-01041-6",
                    ["#气候金融"],
                ),
                _reading(
                    "Decolonizing climate policy",
                    "Sultana",
                    2022,
                    "https://doi.org/10.1177/03091325211017697",
                    ["#Global South"],
                ),
            ],
        )

        markdown = render_markdown(digest)
        html = render_html(digest)

        self.assertIn("今日新闻", markdown)
        self.assertIn("Climate finance update", markdown)
        self.assertIn("今日深读", markdown)
        self.assertIn("**摘要**", markdown)
        self.assertIn("**Brief**", markdown)
        self.assertIn("例证 / Evidence", markdown)
        self.assertIn("The Paris Agreement", markdown)
        self.assertIn("今日新闻", html)
        self.assertIn("今日深读", html)
        self.assertIn("Why it matters", html)
        self.assertIn("Reading Path", html)
        self.assertIn("推荐进一步了解的概念", html)
        self.assertIn("A climate finance accounting framework", html)


def _reading(title: str, authors: str, year: int, url: str, tags: list[str]) -> DeepRead:
    return DeepRead(
        title=title,
        authors=authors,
        year=year,
        url=url,
        note_zh="这是一段较长的阅读摘要，用来说明文章的主要问题意识、研究对象和对今日议题的参考价值。",
        note_en="This is a longer reading brief that explains the article's core question, object of analysis, and relevance for today's issue.",
        argument_zh="文章讨论全球目标、融资安排或气候治理之间的关键张力。",
        argument_en="The article discusses key tensions among global goals, finance arrangements, or climate governance.",
        method_zh="采用政策分析、文献讨论或案例比较的方法。",
        method_en="It uses policy analysis, literature discussion, or comparative cases.",
        evidence_zh="例证包括国家承诺、融资工具、制度安排或发展中国家的政策约束。",
        evidence_en="Evidence includes national pledges, finance instruments, institutional arrangements, or policy constraints.",
        relevance_zh="适合用来理解今日新闻背后的政策机制和融资含义。",
        relevance_en="Useful for interpreting the policy mechanism and finance implication behind today's news.",
        tags=tags,
        kind="paper",
    )


if __name__ == "__main__":
    unittest.main()
