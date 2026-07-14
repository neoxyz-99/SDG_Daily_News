from __future__ import annotations

import html

from .models import DeepRead, Digest, DigestItem, NewsBrief


def render_markdown(digest: Digest) -> str:
    recent_news = digest.recent_news
    research_signals = digest.research_signals or digest.items
    readings = digest.classic_readings or digest.readings
    lines = [
        "# SDG Weekly Compass",
        "",
        f"Issue week: {digest.digest_date.isoformat()}",
        "",
    ]
    if digest.overview_zh:
        lines.extend(["## 本周导语 / Editorial Note", "", digest.overview_zh, ""])
        if digest.overview_en:
            lines.extend([digest.overview_en, ""])

    lines.extend(["## 近期要闻 / Recent News", ""])
    if recent_news:
        for index, item in enumerate(recent_news, start=1):
            lines.extend(
                [
                    f"### {index}. {item.title_en}",
                    "",
                    f"{item.source_org} · {item.published_date}",
                    "",
                    f"{item.one_sentence_zh}",
                    "",
                    f"{item.one_sentence_en}",
                    "",
                    f"Original: {item.url}",
                    "",
                ]
            )
    else:
        lines.extend(["本期没有新的要闻条目。", ""])

    lines.extend(["## 研究动向 / Research Signals", ""])
    if research_signals:
        for index, item in enumerate(research_signals, start=1):
            lines.extend(
                [
                    f"### {index}. {item.title_en}",
                    "",
                    f"{item.source_org} · {item.published_date}",
                    "",
                    f"Tags: {' '.join(item.tags)}",
                    "",
                    f"**核心论点 / Core Argument**: {item.core_argument_zh or item.summary_zh}",
                    "",
                    f"{item.core_argument_en or item.summary_en}",
                    "",
                    f"**为什么此刻重要 / Why Now**: {item.why_now_zh or item.why_it_matters_zh}",
                    "",
                    f"{item.why_now_en or item.why_it_matters_en}",
                    "",
                    f"**议程位置 / Agenda Position**: {item.agenda_position_zh or '议程背景不明确'}",
                    "",
                    f"{item.agenda_position_en or 'The agenda background is unclear.'}",
                    "",
                    f"Original: {item.url}",
                    "",
                ]
            )
    else:
        lines.extend(["本期没有新的研究动向条目。", ""])

    if digest.weekly_thread_zh:
        lines.extend(["## 本周议题线索 / Weekly Thread", "", digest.weekly_thread_zh, ""])
        if digest.weekly_thread_en:
            lines.extend([digest.weekly_thread_en, ""])

    lines.extend(["## 经典研读 / Classic Reading", ""])
    if readings:
        for reading in readings[:3]:
            lines.extend(
                [
                    f"### {reading.title}",
                    "",
                    f"{reading.authors} · {reading.year} · {reading.journal}",
                    "",
                    " ".join(reading.tags),
                    "",
                    reading.note_zh,
                    "",
                    reading.note_en,
                    "",
                ]
            )
            if reading.methodology_zh:
                lines.extend(["**方法论 / Methodology**", "", reading.methodology_zh, ""])
                if reading.method_en:
                    lines.extend([reading.method_en, ""])
            if reading.today_connection_zh:
                lines.extend(["**今日关联 / Today's Connection**", "", reading.today_connection_zh, ""])
                if reading.today_connection_en:
                    lines.extend([reading.today_connection_en, ""])
            if reading.research_directions:
                lines.extend(["**研究方向 / Research Directions**", ""])
                for direction in reading.research_directions:
                    lines.append(f"- {direction.question_zh} ({', '.join(direction.keywords)})")
                    if direction.question_en:
                        lines.append(f"  {direction.question_en}")
                lines.append("")
            lines.extend([f"DOI / 原文链接: {reading.url}", ""])
    else:
        lines.append("本期没有匹配到白名单经典研读材料。")

    return "\n".join(lines).strip() + "\n"


def render_html(digest: Digest) -> str:
    recent_news = digest.recent_news
    research_signals = digest.research_signals or digest.items
    readings = digest.classic_readings or digest.readings
    recent_html = "\n".join(_render_recent_news_html(index, item) for index, item in enumerate(recent_news, start=1))
    if not recent_html:
        recent_html = '<p class="empty">本期没有新的要闻条目。</p>'

    research_html = "\n".join(
        _render_research_signal_html(index, item) for index, item in enumerate(research_signals, start=1)
    )
    if not research_html:
        research_html = '<p class="empty">本期没有新的研究动向条目。</p>'

    readings_html = "\n".join(_render_reading_html(reading) for reading in readings[:3])
    if not readings_html:
        readings_html = '<p class="empty">本期没有匹配到白名单经典研读材料。</p>'

    editorial_html = (
        f'<section class="editorial-note"><h2>本周导语 / Editorial Note</h2>'
        f'<p>{html.escape(digest.overview_zh)}</p>{_paragraph_en(digest.overview_en)}</section>'
        if digest.overview_zh
        else ""
    )
    weekly_html = (
        f'<section class="weekly-thread"><h2>本周议题线索 / Weekly Thread</h2>'
        f'<p>{html.escape(digest.weekly_thread_zh)}</p>{_paragraph_en(digest.weekly_thread_en)}</section>'
        if digest.weekly_thread_zh
        else ""
    )
    preheader = html.escape((digest.overview_zh or digest.subject)[:120])

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(digest.subject)}</title>
  <style>
    body {{ margin: 0; background: #f3f5f2; color: #202721; font-family: Arial, "Microsoft YaHei", sans-serif; }}
    .preheader {{ display: none; max-height: 0; overflow: hidden; opacity: 0; }}
    main {{ max-width: 880px; margin: 0 auto; padding: 22px 14px 44px; }}
    header {{ position: relative; overflow: hidden; background: #103d2b; color: #f7fbf6; border-radius: 8px; padding: 24px 28px 28px; border-bottom: 4px solid #d7b65c; }}
    .header-row {{ position: relative; z-index: 2; display: table; width: 100%; }}
    .issue-date {{ display: table-cell; vertical-align: top; color: rgba(255,255,255,.72); font-size: 13px; font-weight: 400; }}
    .masthead {{ display: table-cell; vertical-align: top; text-align: right; font-family: Georgia, "Times New Roman", "Microsoft YaHei", serif; font-size: 34px; line-height: 1.1; font-weight: 700; letter-spacing: 0; }}
    .header-pattern {{ position: absolute; right: -34px; top: -16px; width: 260px; height: 160px; opacity: 1; }}
    .editorial-note, .weekly-thread {{ background: #ffffff; border-left: 4px solid #d7b65c; border-radius: 8px; padding: 18px 22px; margin: 24px 0 8px; }}
    .editorial-note h2, .weekly-thread h2 {{ margin: 0 0 8px; font-size: 16px; color: #123524; }}
    .editorial-note p, .weekly-thread p {{ margin: 0; font-size: 15px; line-height: 1.78; }}
    .section-title {{ margin: 30px 0 12px; font-size: 19px; color: #123524; }}
    .section-subtitle {{ color: #66736a; font-weight: 400; }}
    article.card {{ border-radius: 8px; padding: 20px 24px; margin: 0 0 16px; box-shadow: none; }}
    .recent-card {{ background: #f2f7fd; border: 1px solid #d5e5f6; }}
    .research-card {{ background: #f7f9f7; border: 1px solid #dfe6df; }}
    .compact-card {{ padding: 16px 20px; }}
    .card h3 {{ font-size: 19px; line-height: 1.35; margin: 0 0 6px; }}
    .card h3 a {{ color: #0b5cad; text-decoration: none; }}
    .meta {{ font-size: 12px; color: #888; margin: 0 0 12px; }}
    .tags {{ margin: 0 0 14px; }}
    .tag {{ display: inline-block; border-radius: 999px; padding: 4px 8px; margin: 0 6px 6px 0; font-size: 12px; background: #edf7f1; color: #1f6a43; border: 1px solid #c9e3d1; }}
    .label {{ margin: 16px 0 6px; font-size: 12px; color: #356046; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }}
    .body-text {{ font-size: 15px; line-height: 1.78; margin: 0; }}
    .en-text {{ color: #5d6b63; font-size: 14px; line-height: 1.74; margin: 8px 0 0; }}
    .agenda {{ background: #ffffff; border-left: 4px solid #9cc9a7; padding: 12px 14px; margin: 16px 0 0; }}
    .readings-band {{ background: #faf8f4; border-radius: 8px; padding: 22px 24px 2px; }}
    article.reading {{ background: transparent; border: 0; padding: 0; margin: 0 0 28px; box-shadow: none; }}
    .reading h3 {{ font-family: Georgia, "Times New Roman", "Microsoft YaHei", serif; font-size: 19px; font-weight: 700; line-height: 1.35; margin: 0 0 7px; }}
    .reading h3 a {{ color: #5e4630; text-decoration: none; }}
    .reading .meta {{ color: #7a746c; font-size: 12px; }}
    .reading-text, .method-text, .connection-text {{ font-size: 15px; line-height: 1.82; margin: 8px 0 10px; color: #2f332f; }}
    .method-title, .connection-title, .research-title {{ margin: 16px 0 6px; font-size: 13px; color: #6f4a18; font-weight: 700; }}
    .connection-text {{ margin-left: 14px; color: #5d6e63; font-style: italic; }}
    .research-list {{ margin: 8px 0 0; padding-left: 18px; }}
    .research-list li {{ margin: 8px 0; line-height: 1.65; }}
    .keywords {{ color: #617064; font-size: 13px; }}
    .doi-link {{ display: inline-block; margin-top: 10px; font-size: 12px; color: #7a746c; text-decoration: none; }}
    .empty {{ background: #fff; border: 1px dashed #c9d3cc; border-radius: 6px; padding: 18px; color: #617064; }}
    a {{ color: #0b5cad; }}
    @media (max-width: 520px) {{
      main {{ padding: 12px 10px 28px; }}
      header {{ padding: 22px 18px 24px; }}
      .header-row, .issue-date, .masthead {{ display: block; text-align: left; }}
      .masthead {{ margin-top: 10px; font-size: 28px; }}
      article.card {{ padding: 18px; }}
      .readings-band {{ padding: 18px 18px 2px; }}
    }}
  </style>
</head>
<body>
  <div class="preheader">{preheader}</div>
  <main>
    <header>
      <svg class="header-pattern" viewBox="0 0 260 160" aria-hidden="true">
        <g fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="1">
          <path d="M20 20 C80 0 180 0 240 20" />
          <path d="M20 55 C80 35 180 35 240 55" />
          <path d="M20 90 C80 70 180 70 240 90" />
          <path d="M20 125 C80 105 180 105 240 125" />
          <path d="M40 8 C58 42 58 118 40 152" />
          <path d="M90 4 C112 44 112 116 90 156" />
          <path d="M140 2 C164 44 164 116 140 158" />
          <path d="M190 4 C212 44 212 116 190 156" />
          <path d="M238 8 C220 42 220 118 238 152" />
        </g>
      </svg>
      <div class="header-row">
        <div class="issue-date">{digest.digest_date.isoformat()}</div>
        <div class="masthead">SDG Weekly Compass</div>
      </div>
    </header>

    {editorial_html}

    <h2 class="section-title">近期要闻 <span class="section-subtitle">/ Recent News</span></h2>
    <section>{recent_html}</section>

    <h2 class="section-title">研究动向 <span class="section-subtitle">/ Research Signals</span></h2>
    <section>{research_html}</section>

    {weekly_html}

    <h2 class="section-title">经典研读 <span class="section-subtitle">/ Classic Reading</span></h2>
    <section class="readings-band">{readings_html}</section>
  </main>
</body>
</html>
"""


def _render_recent_news_html(index: int, item: NewsBrief) -> str:
    return f"""<article class="card compact-card recent-card">
  <h3>{index}. <a href="{html.escape(item.url)}">{html.escape(item.title_en)}</a></h3>
  <p class="meta">{html.escape(item.source_org)} · {html.escape(item.published_date)}</p>
  <p class="body-text">{html.escape(item.one_sentence_zh)}</p>
  {_paragraph_en(item.one_sentence_en)}
</article>"""


def _render_research_signal_html(index: int, item: DigestItem) -> str:
    tags = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in item.tags)
    return f"""<article class="card research-card">
  <h3>{index}. <a href="{html.escape(item.url)}">{html.escape(item.title_en)}</a></h3>
  <p class="meta">{html.escape(item.source_org)} · {html.escape(item.published_date)}</p>
  <p class="tags">{tags}</p>
  <p class="label">核心论点 / Core Argument</p>
  <p class="body-text">{html.escape(item.core_argument_zh or item.summary_zh)}</p>
  {_paragraph_en(item.core_argument_en or item.summary_en)}
  <p class="label">为什么此刻重要 / Why Now</p>
  <p class="body-text">{html.escape(item.why_now_zh or item.why_it_matters_zh)}</p>
  {_paragraph_en(item.why_now_en or item.why_it_matters_en)}
  <div class="agenda">
    <p class="label">议程位置 / Agenda Position</p>
    <p class="body-text">{html.escape(item.agenda_position_zh or "议程背景不明确")}</p>
    {_paragraph_en(item.agenda_position_en or "The agenda background is unclear.")}
  </div>
</article>"""


def _render_reading_html(reading: DeepRead) -> str:
    tags = "".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in reading.tags)
    methodology = (
        f"""<p class="method-title">方法论 / Methodology</p>
  <p class="method-text">{html.escape(reading.methodology_zh)}</p>
  {_paragraph_en(reading.method_en)}"""
        if reading.methodology_zh
        else ""
    )
    connection = (
        f"""<p class="connection-title">今日关联 / Today's Connection</p>
  <p class="connection-text">{html.escape(reading.today_connection_zh)}</p>
  {_paragraph_en(reading.today_connection_en)}"""
        if reading.today_connection_zh
        else ""
    )
    research = _render_research_directions(reading)
    return f"""<article class="reading">
  <h3><a href="{html.escape(reading.url)}">{html.escape(reading.title)}</a></h3>
  <p class="meta">{html.escape(reading.authors)} · {reading.year} · {html.escape(reading.journal)}</p>
  <p class="tags">{tags}</p>
  <p class="reading-text">{html.escape(reading.note_zh)}</p>
  {_paragraph_en(reading.note_en)}
  {methodology}
  {connection}
  {research}
  <a class="doi-link" href="{html.escape(reading.url)}">DOI / 原文链接</a>
</article>"""


def _render_research_directions(reading: DeepRead) -> str:
    if not reading.research_directions:
        return ""
    items = "".join(
        f"<li>{html.escape(direction.question_zh)} "
        f'<span class="keywords">({html.escape(", ".join(direction.keywords))})</span>'
        f'{_inline_en(direction.question_en)}</li>'
        for direction in reading.research_directions[:2]
    )
    return f"""<p class="research-title">研究方向 / Research Directions</p>
  <ul class="research-list">{items}</ul>"""


def _paragraph_en(value: str) -> str:
    if not value:
        return ""
    return f'<p class="en-text">{html.escape(value)}</p>'


def _inline_en(value: str) -> str:
    if not value:
        return ""
    return f'<br><span class="en-text">{html.escape(value)}</span>'


# WEEKLY VISUAL REDESIGN DONE: HTML and Markdown now render recent news, research signals, and classic readings as separate modules.
