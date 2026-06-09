from __future__ import annotations

import html
from .models import Digest


def render_markdown(digest: Digest) -> str:
    lines = [
        f"# {digest.subject}",
        "",
        digest.overview_zh,
        "",
    ]
    for index, item in enumerate(digest.items, start=1):
        lines.extend(
            [
                f"## {index}. {item.title_en}",
                "",
                f"- 来源机构: {item.source_org}",
                f"- 发布日期: {item.published_date}",
                f"- 标签: {' '.join(item.tags)}",
                f"- 原文链接: {item.url}",
                "",
                item.summary_zh,
                "",
                "**关键词/术语**",
                "",
            ]
        )
        for term in item.terms:
            lines.append(f"- {term.term_en} / {term.term_zh}: {term.explanation_zh}")
        if item.deep_reads:
            lines.extend(["", "**可选深读**", ""])
            for reading in item.deep_reads:
                lines.append(f"- {reading.authors} ({reading.year}). {reading.title}. {reading.url}")
        lines.append("")
    if not digest.items:
        lines.append("今日没有符合筛选条件的新内容。")
    return "\n".join(lines).strip() + "\n"


def render_html(digest: Digest) -> str:
    items_html = "\n".join(_render_item_html(index, item) for index, item in enumerate(digest.items, start=1))
    if not items_html:
        items_html = "<p>今日没有符合筛选条件的新内容。</p>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(digest.subject)}</title>
  <style>
    body {{ margin: 0; background: #f6f7f4; color: #1f2933; font-family: Arial, "Microsoft YaHei", sans-serif; }}
    main {{ max-width: 820px; margin: 0 auto; padding: 28px 18px 42px; }}
    header {{ border-bottom: 2px solid #14532d; padding-bottom: 18px; margin-bottom: 22px; }}
    h1 {{ font-size: 28px; line-height: 1.2; margin: 0 0 12px; color: #123524; }}
    h2 {{ font-size: 20px; line-height: 1.35; margin: 0 0 10px; color: #132f43; }}
    article {{ background: #fff; border: 1px solid #d7ded4; border-radius: 8px; padding: 18px; margin: 18px 0; }}
    .meta, .tags, .terms, .deep {{ font-size: 14px; color: #4b5563; }}
    .summary {{ font-size: 16px; line-height: 1.72; }}
    a {{ color: #0f766e; }}
    ul {{ padding-left: 20px; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{html.escape(digest.subject)}</h1>
      <p>{html.escape(digest.overview_zh)}</p>
    </header>
    {items_html}
  </main>
</body>
</html>
"""


def _render_item_html(index: int, item) -> str:
    terms = "".join(
        f"<li><strong>{html.escape(term.term_en)} / {html.escape(term.term_zh)}</strong>: {html.escape(term.explanation_zh)}</li>"
        for term in item.terms
    )
    deep_reads = "".join(
        f"<li>{html.escape(reading.authors)} ({reading.year}). "
        f"<a href=\"{html.escape(reading.url)}\">{html.escape(reading.title)}</a></li>"
        for reading in item.deep_reads
    )
    deep_section = f"<div class=\"deep\"><strong>可选深读</strong><ul>{deep_reads}</ul></div>" if deep_reads else ""
    return f"""<article>
  <h2>{index}. <a href="{html.escape(item.url)}">{html.escape(item.title_en)}</a></h2>
  <p class="meta">来源机构: {html.escape(item.source_org)} | 发布日期: {html.escape(item.published_date)}</p>
  <p class="tags">{html.escape(" ".join(item.tags))}</p>
  <p class="summary">{html.escape(item.summary_zh)}</p>
  <div class="terms"><strong>关键词/术语</strong><ul>{terms}</ul></div>
  {deep_section}
</article>"""
