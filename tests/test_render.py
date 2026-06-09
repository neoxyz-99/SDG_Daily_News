from __future__ import annotations

from datetime import date
import unittest

from sdg_digest.models import DeepRead, Digest, DigestItem, DigestTerm
from sdg_digest.render import render_html, render_markdown


class RenderTests(unittest.TestCase):
    def test_render_markdown_and_html_include_digest_fields(self) -> None:
        digest = Digest(
            digest_date=date(2026, 6, 9),
            subject="SDG Daily Digest - 2026-06-09",
            overview_zh="今日关注 NDC 与气候金融。",
            items=[
                DigestItem(
                    title_en="Climate finance update",
                    source_org="UNFCCC News",
                    published_date="2026-06-09",
                    summary_zh="该信息说明气候融资安排对发展中国家执行 NDC 的支持作用。",
                    terms=[
                        DigestTerm(
                            term_en="NDC",
                            term_zh="国家自主贡献",
                            explanation_zh="各国在巴黎协定下提交的减排和适应承诺。",
                        )
                    ],
                    tags=["#NDC", "#气候金融"],
                    url="https://unfccc.int/news/example",
                    deep_reads=[
                        DeepRead(
                            title="The Paris Agreement",
                            authors="Rogelj et al.",
                            year=2016,
                            url="https://doi.org/10.1038/nclimate3031",
                        )
                    ],
                )
            ],
        )

        markdown = render_markdown(digest)
        html = render_html(digest)

        self.assertIn("Climate finance update", markdown)
        self.assertIn("国家自主贡献", markdown)
        self.assertIn("Climate finance update", html)
        self.assertIn("#NDC #气候金融", html)


if __name__ == "__main__":
    unittest.main()
