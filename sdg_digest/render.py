from __future__ import annotations

import html

from .models import DeepRead, Digest


CONCEPT_LABELS = {
    "#NDC": "NDC / 国家自主贡献",
    "#气候金融": "climate finance / 气候金融",
    "#SDG进展": "SDG implementation / SDG 落实",
    "#绿色转型": "green transition / 绿色转型",
    "#债务可持续性": "debt sustainability / 债务可持续性",
    "#Global South": "Global South / 全球南方",
}


def render_markdown(digest: Digest) -> str:
    lines = [
        f"# {digest.subject}",
        "",
        digest.overview_zh,
        "",
        digest.overview_en,
        "",
        "## 今日新闻 / News",
        "",
    ]
    for index, item in enumerate(digest.items, start=1):
        lines.extend(
            [
                f"### {index}. {item.title_en}",
                "",
                f"- 来源 / Source: {item.source_org}",
                f"- 日期 / Date: {item.published_date}",
                f"- 标签 / Tags: {' '.join(item.tags)}",
                f"- SDG links: {', '.join(item.sdg_links)}",
                f"- 原文 / Original: {item.url}",
                "",
                f"**摘要**: {item.summary_zh}",
                "",
                f"**Brief**: {item.summary_en}",
                "",
                f"**为什么重要**: {item.why_it_matters_zh}",
                "",
                f"**Why it matters**: {item.why_it_matters_en}",
                "",
                "**关键词/术语 / Terms**",
                "",
            ]
        )
        for term in item.terms:
            lines.append(f"- {term.term_en} / {term.term_zh}: {term.explanation_zh}")
        lines.append("")
    if not digest.items:
        lines.append("今日没有符合筛选条件的新内容。")
        lines.append("")

    lines.extend(["## 今日深读 / Reading List", ""])
    if digest.readings:
        for reading in digest.readings:
            tags = f" [{' '.join(reading.tags)}]" if reading.tags else ""
            lines.extend(
                [
                    f"### {reading.title}{tags}",
                    "",
                    f"{reading.authors} ({reading.year}) · {reading.kind}",
                    "",
                    f"**阅读摘要 / Brief**: {reading.note_zh} / {reading.note_en}",
                    "",
                    f"- 核心观点 / Argument: {reading.argument_zh} / {reading.argument_en}",
                    f"- 方法 / Method: {reading.method_zh} / {reading.method_en}",
                    f"- 例证 / Evidence: {reading.evidence_zh} / {reading.evidence_en}",
                    f"- 今日关联 / Relevance: {reading.relevance_zh} / {reading.relevance_en}",
                    f"- Link: {reading.url}",
                    "",
                ]
            )
    else:
        lines.append("今日没有匹配到白名单深读材料。")
    return "\n".join(lines).strip() + "\n"


def render_html(digest: Digest) -> str:
    items_html = "\n".join(_render_item_html(index, item) for index, item in enumerate(digest.items, start=1))
    if not items_html:
        items_html = '<p class="empty">今日没有符合筛选条件的新内容。<br>No eligible updates today.</p>'
    readings_html = "\n".join(
        _render_reading_html(index, reading, digest.readings) for index, reading in enumerate(digest.readings, start=1)
    )
    if not readings_html:
        readings_html = '<p class="empty">今日没有匹配到白名单深读材料。<br>No approved readings matched today\'s themes.</p>'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(digest.subject)}</title>
  <style>
    body {{ margin: 0; background: #f4f6f4; color: #1f2933; font-family: Arial, "Microsoft YaHei", sans-serif; }}
    .preheader {{ display: none; max-height: 0; overflow: hidden; opacity: 0; }}
    main {{ max-width: 820px; margin: 0 auto; padding: 22px 14px 44px; }}
    header {{ background: #103d2b; color: #f7fbf6; border-radius: 7px; padding: 28px 28px 24px; border-bottom: 4px solid #d7b65c; }}
    h1 {{ font-size: 28px; line-height: 1.2; margin: 0 0 16px; letter-spacing: 0; }}
    header p {{ font-size: 16px; line-height: 1.72; margin: 8px 0 0; color: #edf7ef; }}
    .en {{ color: #5d6e63; font-size: 14px; line-height: 1.72; }}
    header .en {{ color: #cde6d3; }}
    .section-title {{ margin: 30px 0 12px; font-size: 19px; color: #123524; }}
    .section-subtitle {{ color: #647067; font-weight: 400; }}
    article {{ background: #fff; border: 1px solid #d9e1d9; border-radius: 7px; padding: 20px; margin: 14px 0; }}
    .news h3 {{ font-size: 19px; line-height: 1.35; margin: 0 0 10px; }}
    .news h3 a {{ color: #0b5cad; text-decoration: none; }}
    .meta {{ font-size: 13px; color: #5f6b7a; margin: 0 0 12px; }}
    .tags {{ margin: 0 0 14px; }}
    .tag, .sdg, .concept {{ display: inline-block; border-radius: 999px; padding: 4px 8px; margin: 0 6px 6px 0; font-size: 12px; }}
    .tag {{ background: #edf7f1; color: #1f6a43; border: 1px solid #c9e3d1; }}
    .sdg {{ background: #eef4ff; color: #244f8f; border: 1px solid #c9daf8; }}
    .concept {{ background: #f4f0e7; color: #71511d; border: 1px solid #e0d3b9; }}
    .label {{ margin: 16px 0 6px; font-size: 12px; color: #356046; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }}
    .summary {{ font-size: 15px; line-height: 1.78; margin: 0; }}
    .impact {{ background: #f7faf7; border-left: 4px solid #9cc9a7; padding: 12px 14px; margin: 16px 0 0; }}
    .terms {{ border-top: 1px solid #e5ebe6; padding-top: 12px; margin-top: 14px; font-size: 13px; color: #425466; }}
    .terms ul {{ margin: 8px 0 0; padding-left: 18px; }}
    .reading {{ background: #fffdf8; border-color: #e5d5b0; padding: 0; overflow: hidden; }}
    .reading-head {{ padding: 20px 20px 14px; border-bottom: 1px solid #eadfc6; background: #fffaf0; }}
    .reading h3 {{ font-size: 18px; line-height: 1.35; margin: 0 0 8px; }}
    .reading h3 a {{ color: #7a4208; text-decoration: none; }}
    .reading-body {{ padding: 18px 20px 20px; }}
    .reading-brief {{ background: #ffffff; border: 1px solid #eee3c9; border-radius: 6px; padding: 14px; margin-bottom: 14px; }}
    .reading-grid {{ margin-top: 4px; }}
    .reading-block {{ border-left: 3px solid #d7b65c; padding: 0 0 0 12px; margin: 14px 0; }}
    .reading-block strong {{ color: #6f3f08; font-size: 13px; }}
    .reading-path {{ background: #f7faf7; border: 1px solid #dbe7dc; border-radius: 6px; padding: 14px; margin-top: 16px; }}
    .reading-path ul {{ margin: 8px 0 0; padding-left: 18px; }}
    .reading-path li {{ margin: 6px 0; line-height: 1.55; }}
    .empty {{ background: #fff; border: 1px dashed #c9d3cc; border-radius: 6px; padding: 18px; color: #617064; }}
    a {{ color: #0b5cad; }}
    @media (max-width: 520px) {{
      main {{ padding: 12px 10px 28px; }}
      header {{ padding: 22px 18px; }}
      h1 {{ font-size: 24px; }}
      article {{ padding: 16px; }}
      .reading {{ padding: 0; }}
      .reading-head, .reading-body {{ padding-left: 16px; padding-right: 16px; }}
    }}
  </style>
</head>
<body>
  <div class="preheader">{html.escape(digest.overview_zh[:120])}</div>
  <main>
    <header>
      <h1>{html.escape(digest.subject)}</h1>
      <p>{html.escape(digest.overview_zh)}</p>
      <p class="en">{html.escape(digest.overview_en)}</p>
    </header>

    <h2 class="section-title">今日新闻 <span class="section-subtitle">/ News · {len(digest.items)}</span></h2>
    {items_html}

    <h2 class="section-title">今日深读 <span class="section-subtitle">/ Reading List · {len(digest.readings)}</span></h2>
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
    tags = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in item.tags)
    sdg_links = "".join(f'<span class="sdg">{html.escape(link)}</span>' for link in item.sdg_links)
    return f"""<article class="news">
  <h3>{index}. <a href="{html.escape(item.url)}">{html.escape(item.title_en)}</a></h3>
  <p class="meta">来源 / Source: {html.escape(item.source_org)} · 日期 / Date: {html.escape(item.published_date)}</p>
  <p class="tags">{tags}{sdg_links}</p>
  <p class="label">摘要</p>
  <p class="summary">{html.escape(item.summary_zh)}</p>
  <p class="label">Brief</p>
  <p class="summary en">{html.escape(item.summary_en)}</p>
  <div class="impact">
    <p class="label">为什么重要</p>
    <p class="summary">{html.escape(item.why_it_matters_zh)}</p>
    <p class="label">Why it matters</p>
    <p class="summary en">{html.escape(item.why_it_matters_en)}</p>
  </div>
  <div class="terms"><strong>关键词/术语 / Terms</strong><ul>{terms}</ul></div>
</article>"""


def _render_reading_html(index: int, reading: DeepRead, all_readings: list[DeepRead]) -> str:
    tags = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in reading.tags)
    concepts = "".join(
        f'<span class="concept">{html.escape(CONCEPT_LABELS.get(tag, tag.lstrip("#")))}</span>'
        for tag in reading.tags[:4]
    )
    path = _reading_path(reading, all_readings)
    return f"""<article class="reading">
  <div class="reading-head">
    <h3>{index}. <a href="{html.escape(reading.url)}">{html.escape(reading.title)}</a></h3>
    <p class="meta">{html.escape(reading.authors)} · {reading.year} · {html.escape(reading.kind)}</p>
    <p class="tags">{tags}</p>
  </div>
  <div class="reading-body">
    <div class="reading-brief">
      <p class="label">阅读摘要 / Brief</p>
      <p class="summary">{html.escape(reading.note_zh)}</p>
      <p class="summary en">{html.escape(reading.note_en)}</p>
    </div>
    <div class="reading-grid">
      {_reading_block("核心观点 / Argument", reading.argument_zh, reading.argument_en)}
      {_reading_block("方法 / Method", reading.method_zh, reading.method_en)}
      {_reading_block("例证 / Evidence", reading.evidence_zh, reading.evidence_en)}
    </div>
    <div class="reading-path">
      <strong>今日关联 / Reading Path</strong>
      <p class="summary">{html.escape(reading.relevance_zh)}</p>
      <p class="summary en">{html.escape(reading.relevance_en)}</p>
      {path}
      <p class="label">推荐进一步了解的概念 / Concepts</p>
      <p>{concepts}</p>
    </div>
  </div>
</article>"""


def _reading_block(label: str, zh: str, en: str) -> str:
    return f"""<div class="reading-block">
  <strong>{html.escape(label)}</strong>
  <p class="summary">{html.escape(zh)}</p>
  <p class="summary en">{html.escape(en)}</p>
</div>"""


def _reading_path(reading: DeepRead, all_readings: list[DeepRead]) -> str:
    related = [item for item in all_readings if item.url != reading.url]
    if not related:
        return ""
    links = "".join(
        f'<li><a href="{html.escape(item.url)}">{html.escape(item.title)}</a> '
        f'<span class="en">({html.escape(item.authors)}, {item.year})</span></li>'
        for item in related[:2]
    )
    return f"<ul>{links}</ul>"
