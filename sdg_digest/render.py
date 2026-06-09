from __future__ import annotations

import html

from .models import Digest


def render_markdown(digest: Digest) -> str:
    lines = [
        f"# {digest.subject}",
        "",
        digest.overview_zh,
        "",
        "## 今日新闻",
        "",
    ]
    for index, item in enumerate(digest.items, start=1):
        lines.extend(
            [
                f"### {index}. {item.title_en}",
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
        lines.append("")
    if not digest.items:
        lines.append("今日没有符合筛选条件的新内容。")
        lines.append("")

    lines.extend(["## 今日深读", ""])
    if digest.readings:
        for reading in digest.readings:
            tags = f" [{' '.join(reading.tags)}]" if reading.tags else ""
            lines.extend(
                [
                    f"- {reading.authors} ({reading.year}). {reading.title}.{tags}",
                    f"  {reading.url}",
                    f"  {reading.note_zh}",
                ]
            )
    else:
        lines.append("今日没有匹配到白名单深读材料。")
    return "\n".join(lines).strip() + "\n"


def render_html(digest: Digest) -> str:
    items_html = "\n".join(_render_item_html(index, item) for index, item in enumerate(digest.items, start=1))
    if not items_html:
        items_html = "<p class=\"empty\">今日没有符合筛选条件的新内容。</p>"
    readings_html = "\n".join(_render_reading_html(reading) for reading in digest.readings)
    if not readings_html:
        readings_html = "<p class=\"empty\">今日没有匹配到白名单深读材料。</p>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(digest.subject)}</title>
  <style>
    body {{ margin: 0; background: #eef2ef; color: #1f2933; font-family: Arial, "Microsoft YaHei", sans-serif; }}
    .preheader {{ display: none; max-height: 0; overflow: hidden; opacity: 0; }}
    main {{ max-width: 760px; margin: 0 auto; padding: 24px 14px 42px; }}
    header {{ background: #123524; color: #f8faf7; border-radius: 8px; padding: 26px 24px; }}
    .eyebrow {{ margin: 0 0 10px; color: #b7d9c4; font-size: 13px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }}
    h1 {{ font-size: 28px; line-height: 1.22; margin: 0 0 14px; }}
    header p {{ font-size: 16px; line-height: 1.72; margin: 0; color: #edf7ef; }}
    .section-title {{ margin: 26px 0 12px; font-size: 18px; color: #123524; }}
    article {{ background: #fff; border: 1px solid #d8e0da; border-radius: 8px; padding: 20px; margin: 14px 0; }}
    .news h3 {{ font-size: 19px; line-height: 1.35; margin: 0 0 10px; }}
    .news h3 a {{ color: #0b5cad; text-decoration: none; }}
    .meta {{ font-size: 13px; color: #5f6b7a; margin: 0 0 12px; }}
    .tags {{ margin: 0 0 14px; }}
    .tag {{ display: inline-block; background: #edf7f1; color: #1f6a43; border: 1px solid #c9e3d1; border-radius: 999px; padding: 4px 8px; margin: 0 6px 6px 0; font-size: 12px; }}
    .summary {{ font-size: 15px; line-height: 1.75; margin: 0 0 14px; }}
    .terms {{ border-top: 1px solid #e5ebe6; padding-top: 12px; font-size: 13px; color: #425466; }}
    .terms ul {{ margin: 8px 0 0; padding-left: 18px; }}
    .reading {{ background: #fffaf0; border-color: #ead9a7; }}
    .reading h3 {{ font-size: 17px; line-height: 1.35; margin: 0 0 8px; }}
    .reading h3 a {{ color: #8a4b08; text-decoration: none; }}
    .reading .note {{ font-size: 14px; line-height: 1.68; color: #4b5563; margin: 10px 0 0; }}
    .empty {{ background: #fff; border: 1px dashed #c9d3cc; border-radius: 8px; padding: 18px; color: #617064; }}
    a {{ color: #0b5cad; }}
    @media (max-width: 520px) {{
      main {{ padding: 12px 10px 28px; }}
      header {{ padding: 22px 18px; }}
      h1 {{ font-size: 24px; }}
      article {{ padding: 16px; }}
    }}
  </style>
</head>
<body>
  <div class="preheader">{html.escape(digest.overview_zh[:120])}</div>
  <main>
    <header>
      <p class="eyebrow">SDG / ESG / Climate Finance</p>
      <h1>{html.escape(digest.subject)}</h1>
      <p>{html.escape(digest.overview_zh)}</p>
    </header>

    <h2 class="section-title">今日新闻 · {len(digest.items)} 条</h2>
    {items_html}

    <h2 class="section-title">今日深读 · {len(digest.readings)} 篇</h2>
    {readings_html}
  </main>
</body>
</html>
"""


def _render_item_html(index: int, item) -> str:
    terms = "".join(
        f"<li><strong>{html.escape(term.term_en)} / {html.escape(term.term_zh)}</strong>: {html.escape(term.explanation_zh)}</li>"
        for term in item.terms
    )
    tags = "".join(f"<span class=\"tag\">{html.escape(tag)}</span>" for tag in item.tags)
    return f"""<article class="news">
  <h3>{index}. <a href="{html.escape(item.url)}">{html.escape(item.title_en)}</a></h3>
  <p class="meta">来源机构: {html.escape(item.source_org)} | 发布日期: {html.escape(item.published_date)}</p>
  <p class="tags">{tags}</p>
  <p class="summary">{html.escape(item.summary_zh)}</p>
  <div class="terms"><strong>关键词/术语</strong><ul>{terms}</ul></div>
</article>"""


def _render_reading_html(reading) -> str:
    tags = "".join(f"<span class=\"tag\">{html.escape(tag)}</span>" for tag in reading.tags)
    note = f"<p class=\"note\">{html.escape(reading.note_zh)}</p>" if reading.note_zh else ""
    return f"""<article class="reading">
  <h3><a href="{html.escape(reading.url)}">{html.escape(reading.title)}</a></h3>
  <p class="meta">{html.escape(reading.authors)} · {reading.year} · {html.escape(reading.kind)}</p>
  <p class="tags">{tags}</p>
  {note}
</article>"""
