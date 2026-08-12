from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


SITE_NAME = "SDG Weekly Compass"
CONTACT_EMAIL = "xli91132@gmail.com"
SITE_URL = "https://neoxyz-99.github.io/SDG_Daily_News"
PUBLIC_ISSUE_COUNT = 5
MAX_READINGS_PER_ISSUE = 2

TOPIC_MAP = {
    "#环境治理与气候": "Climate & Environment",
    "#气候金融": "Sustainable Finance",
    "#可持续金融与ESG": "Sustainable Finance",
    "#多边治理": "Global Governance",
    "#国际治理与多边主义": "Global Governance",
    "#地缘政治与治理": "Global Governance",
    "#发展不平等": "Development & Inequality",
    "#发展与不平等": "Development & Inequality",
    "#Global South": "Development & Inequality",
    "#能源转型": "Energy Transition",
    "#绿色转型": "Energy Transition",
    "#水资源治理": "Water Governance",
    "#生物多样性": "Biodiversity",
    "#粮食与土地": "Food & Land",
    "#适应与韧性": "Adaptation & Resilience",
    "#SDG进展": "SDG Progress",
}


@dataclass(frozen=True)
class PublicItem:
    item_id: str
    issue_date: str
    item_type: str
    title: str
    source: str
    published_date: str
    url: str
    topics: tuple[str, ...]
    paragraphs: tuple[str, ...]
    paragraph_labels: tuple[str, ...]


@dataclass(frozen=True)
class PublicIssue:
    date: str
    subject: str
    editorial: str
    weekly_thread: str
    news: tuple[PublicItem, ...]
    signals: tuple[PublicItem, ...]
    readings: tuple[PublicItem, ...]

    @property
    def items(self) -> tuple[PublicItem, ...]:
        return self.news + self.signals + self.readings

    @property
    def topics(self) -> tuple[str, ...]:
        counts: dict[str, int] = {}
        for item in self.items:
            for topic in item.topics:
                counts[topic] = counts.get(topic, 0) + 1
        return tuple(sorted(counts, key=lambda topic: (-counts[topic], topic)))


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _topics(value: object) -> tuple[str, ...]:
    tags = value if isinstance(value, list) else []
    mapped = [TOPIC_MAP[tag] for tag in map(str, tags) if tag in TOPIC_MAP]
    return tuple(dict.fromkeys(mapped))


def _item_id(issue_date: str, item_type: str, index: int) -> str:
    return f"{issue_date}-{item_type.lower().replace(' ', '-')}-{index}"


def _news_item(issue_date: str, raw: dict, index: int) -> PublicItem:
    return PublicItem(
        item_id=_item_id(issue_date, "News", index),
        issue_date=issue_date,
        item_type="News",
        title=_text(raw.get("title_en")),
        source=_text(raw.get("source_org")),
        published_date=_text(raw.get("published_date")),
        url=_text(raw.get("url")),
        topics=_topics(raw.get("tags")),
        paragraphs=tuple(filter(None, [_text(raw.get("one_sentence_en"))])),
        paragraph_labels=("",),
    )


def _signal_item(issue_date: str, raw: dict, index: int) -> PublicItem:
    fields = [
        ("Core argument", _text(raw.get("core_argument_en") or raw.get("summary_en"))),
        ("Why now", _text(raw.get("why_now_en") or raw.get("why_it_matters_en"))),
        ("Agenda position", _text(raw.get("agenda_position_en"))),
    ]
    fields = [(label, value) for label, value in fields if value]
    return PublicItem(
        item_id=_item_id(issue_date, "Research Signal", index),
        issue_date=issue_date,
        item_type="Research Signal",
        title=_text(raw.get("title_en")),
        source=_text(raw.get("source_org")),
        published_date=_text(raw.get("published_date")),
        url=_text(raw.get("url")),
        topics=_topics(raw.get("tags")),
        paragraphs=tuple(value for _, value in fields),
        paragraph_labels=tuple(label for label, _ in fields),
    )


def _reading_item(issue_date: str, raw: dict, index: int) -> PublicItem:
    directions = raw.get("research_directions") if isinstance(raw.get("research_directions"), list) else []
    direction_text = " ".join(
        filter(
            None,
            (
                f"{_text(direction.get('question_en'))} {' '.join(map(str, direction.get('keywords') or []))}".strip()
                for direction in directions
                if isinstance(direction, dict)
            ),
        )
    )
    fields = [
        ("Reading note", _text(raw.get("note_en") or raw.get("abstract_en"))),
        ("Method", _text(raw.get("method_en"))),
        ("Today’s connection", _text(raw.get("today_connection_en"))),
        ("Research directions", direction_text),
    ]
    fields = [(label, value) for label, value in fields if value]
    return PublicItem(
        item_id=_item_id(issue_date, "Research Reading", index),
        issue_date=issue_date,
        item_type="Research Reading",
        title=_text(raw.get("title")),
        source=" · ".join(filter(None, [_text(raw.get("authors")), _text(raw.get("journal"))])),
        published_date=_text(raw.get("published_date") or raw.get("year")),
        url=_text(raw.get("url")),
        topics=_topics(raw.get("tags")),
        paragraphs=tuple(value for _, value in fields),
        paragraph_labels=tuple(label for label, _ in fields),
    )


def normalize_digest(raw: dict) -> PublicIssue:
    issue_date = _text(raw.get("digest_date"))
    signal_rows = raw.get("research_signals") or raw.get("items") or []
    reading_rows = raw.get("classic_readings") or raw.get("readings") or []
    news = tuple(
        item
        for index, row in enumerate(raw.get("recent_news") or [])
        if isinstance(row, dict)
        for item in [_news_item(issue_date, row, index)]
        if item.title and item.paragraphs
    )
    signals = tuple(
        item
        for index, row in enumerate(signal_rows)
        if isinstance(row, dict)
        for item in [_signal_item(issue_date, row, index)]
        if item.title and item.paragraphs
    )
    readings = tuple(
        item
        for index, row in enumerate(reading_rows[:MAX_READINGS_PER_ISSUE])
        if isinstance(row, dict)
        for item in [_reading_item(issue_date, row, index)]
        if item.title and item.paragraphs
    )
    return PublicIssue(
        date=issue_date,
        subject=_text(raw.get("subject")),
        editorial=_text(raw.get("overview_en")),
        weekly_thread=_text(raw.get("weekly_thread_en")),
        news=news,
        signals=signals,
        readings=readings,
    )


def load_public_issues(archive_dir: Path, limit: int = PUBLIC_ISSUE_COUNT) -> list[PublicIssue]:
    try:
        index = json.loads((archive_dir / "index.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read archive index: {exc}") from exc

    issues: list[PublicIssue] = []
    for entry in index.get("digests", []):
        issue_date = _text(entry.get("date")) if isinstance(entry, dict) else ""
        if not issue_date:
            continue
        try:
            raw = json.loads((archive_dir / issue_date / "digest.json").read_text(encoding="utf-8"))
            issue = normalize_digest(raw)
        except (OSError, json.JSONDecodeError):
            continue
        if issue.date and issue.items:
            issues.append(issue)
        if len(issues) == limit:
            break
    if not issues:
        raise RuntimeError("No valid English issues were found in the archive")
    return issues


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _format_date(value: str, short: bool = False) -> str:
    from datetime import date

    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%b %-d, %Y" if short else "%B %-d, %Y")


def _rel_prefix(depth: int) -> str:
    return "../" * depth


def _header(depth: int, active: str) -> str:
    prefix = _rel_prefix(depth)
    links = [("Latest", f"{prefix}index.html"), ("Archive", f"{prefix}archive/index.html"), ("Search", f"{prefix}search/index.html"), ("About", f"{prefix}about/index.html")]
    nav = "".join(f'<a href="{href}" class="{"active" if label == active else ""}">{label}</a>' for label, href in links)
    return f"""<div class="utility-bar"><span>Independent weekly intelligence</span><span>Climate · Development · Governance</span></div>
<header class="site-header">
  <a class="masthead" href="{prefix}index.html" aria-label="SDG Weekly Compass home"><span class="compass-mark">N</span><span>{SITE_NAME}</span></a>
  <nav aria-label="Primary navigation">{nav}</nav>
</header>"""


def _footer(depth: int) -> str:
    prefix = _rel_prefix(depth)
    return f"""<footer>
  <div class="footer-grid">
    <div><div class="footer-brand">{SITE_NAME}</div><p>Curated knowledge and information on sustainable development.</p></div>
    <div class="footer-links"><a href="{prefix}about/index.html">Editorial method</a><a href="{prefix}copyright/index.html">Copyright &amp; sources</a><a href="mailto:{CONTACT_EMAIL}">Contact</a></div>
  </div>
  <p class="copyright-line">A non-commercial knowledge-sharing project for learning, research, and public-interest discussion. Copyright in referenced works remains with the respective owners.</p>
</footer>"""


def _page(title: str, description: str, body: str, depth: int, active: str = "") -> str:
    prefix = _rel_prefix(depth)
    canonical_path = "" if title == SITE_NAME else f"{re.sub(r'[^a-z]+', '-', title.lower()).strip('-')}/"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{_e(description)}">
  <meta property="og:title" content="{_e(title)}">
  <meta property="og:description" content="{_e(description)}">
  <meta property="og:type" content="website">
  <meta property="og:image" content="{SITE_URL}/assets/og.png">
  <meta name="twitter:card" content="summary_large_image">
  <title>{_e(title)}</title>
  <link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="{prefix}assets/site.css">
  <script defer src="{prefix}assets/site.js"></script>
</head>
<body data-page="{_e(canonical_path)}">
  <div class="site-shell">{_header(depth, active)}<main>{body}</main>{_footer(depth)}</div>
</body>
</html>
"""


def _topic_tags(values: tuple[str, ...]) -> str:
    return "" if not values else f'<div class="topic-row">{"".join(f"<span>{_e(value)}</span>" for value in values)}</div>'


def _source_line(item: PublicItem) -> str:
    parts = [item.source, item.published_date]
    return f'<p class="source-line">{_e(" · ".join(filter(None, parts)) or "Independent analysis")}</p>'


def _original_link(item: PublicItem) -> str:
    return "" if not item.url else f'<a class="original-link" href="{_e(item.url)}" target="_blank" rel="noreferrer">Read the original <span aria-hidden="true">↗</span></a>'


def _section_title(eyebrow: str, title: str, count: int | None = None) -> str:
    count_html = "" if count is None else f"<span>{count} items</span>"
    return f'<div class="section-heading"><p>{_e(eyebrow)}</p><div><h2>{_e(title)}</h2>{count_html}</div></div>'


def _news_card(item: PublicItem, index: int) -> str:
    return f"""<article class="news-card"><span class="card-number">{index + 1:02d}</span><div><h3>{_e(item.title)}</h3>{_source_line(item)}<p>{_e(item.paragraphs[0])}</p>{_topic_tags(item.topics)}{_original_link(item)}</div></article>"""


def _signal_card(item: PublicItem) -> str:
    analysis = "".join(
        f'<div class="analysis-block"><h4>{_e(item.paragraph_labels[index])}</h4><p>{_e(paragraph)}</p></div>'
        for index, paragraph in enumerate(item.paragraphs)
    )
    return f"""<article class="signal-card">{_topic_tags(item.topics)}<h3>{_e(item.title)}</h3>{_source_line(item)}{analysis}{_original_link(item)}</article>"""


def _reading_card(item: PublicItem) -> str:
    paragraphs = ""
    for index, paragraph in enumerate(item.paragraphs):
        label = item.paragraph_labels[index]
        highlighted = label in {"Today’s connection", "Research directions"}
        heading = "" if label == "Reading note" else f"<h4>{_e(label)}</h4>"
        paragraphs += f'<div class="{"today-connection" if highlighted else "reading-copy"}">{heading}<p>{_e(paragraph)}</p></div>'
    return f"""<article class="reading-card"><p class="kicker">From the research shelf</p><h3>{_e(item.title)}</h3>{_source_line(item)}{_topic_tags(item.topics)}{paragraphs}{_original_link(item)}</article>"""


def _issue_content(issue: PublicIssue) -> str:
    sections: list[str] = []
    if issue.news:
        sections.append(f'<section class="issue-section">{_section_title("The immediate field", "Recent News", len(issue.news))}<div class="news-grid">{"".join(_news_card(item, index) for index, item in enumerate(issue.news))}</div></section>')
    if issue.signals:
        sections.append(f'<section class="issue-section signals-section">{_section_title("What the week is telling us", "Research Signals", len(issue.signals))}<div class="signals-grid">{"".join(_signal_card(item) for item in issue.signals)}</div></section>')
    if issue.weekly_thread:
        sections.append(f'<aside class="weekly-thread"><p class="kicker">Weekly thread</p><blockquote>{_e(issue.weekly_thread)}</blockquote></aside>')
    if issue.readings:
        sections.append(f'<section class="issue-section readings-section">{_section_title("Ideas with a longer half-life", "Research Reading", len(issue.readings))}<div class="readings-grid">{"".join(_reading_card(item) for item in issue.readings)}</div></section>')
    return "".join(sections)


def _archive_cards(issues: list[PublicIssue], depth: int) -> str:
    prefix = _rel_prefix(depth)
    cards: list[str] = []
    for index, issue in enumerate(issues):
        summary = issue.signals[0].paragraphs[0] if issue.signals else issue.news[0].paragraphs[0] if issue.news else "A curated weekly reading of policy change."
        href = f"{prefix}issues/{issue.date}/index.html"
        cards.append(f"""<article class="archive-card"><div class="archive-index">{index + 1:02d}</div><p class="kicker">Issue · {_e(_format_date(issue.date))}</p><h2><a href="{href}">{_e(issue.editorial or issue.subject)}</a></h2><p>{_e(summary)}</p>{_topic_tags(issue.topics[:3])}<div class="archive-meta"><span>{len(issue.items)} pieces</span><a href="{href}">Open issue →</a></div></article>""")
    return f'<div class="archive-grid">{"".join(cards)}</div>'


def _home(issues: list[PublicIssue]) -> str:
    latest = issues[0]
    lead = latest.signals[0] if latest.signals else latest.news[0] if latest.news else latest.readings[0]
    body = f"""<section class="lead-grid">
  <div class="issue-stamp"><span>Issue</span><strong>{_e(_format_date(latest.date, True))}</strong><span>{len(latest.items)} curated pieces</span></div>
  <div class="lead-story"><p class="kicker">Editorial note</p><h1>{_e(latest.editorial or lead.title)}</h1><p class="lead-deck">{_e(lead.paragraphs[0])}</p><a class="button-link" href="issues/{latest.date}/index.html">Read the full issue <span aria-hidden="true">→</span></a></div>
  <aside class="contents-note"><p class="kicker">In this issue</p><ul><li><strong>{len(latest.news)}</strong> news notes</li><li><strong>{len(latest.signals)}</strong> policy signals</li><li><strong>{len(latest.readings)}</strong> research readings</li></ul>{_topic_tags(latest.topics[:4])}</aside>
</section>"""
    body += _issue_content(latest)
    if len(issues) > 1:
        body += f'<section class="archive-preview">{_section_title("The record so far", "Previous Issues")}{_archive_cards(issues[1:], 0)}<a class="text-link" href="archive/index.html">Explore the complete archive →</a></section>'
    return _page(SITE_NAME, "An independent weekly briefing on climate, development finance, and global governance.", body, 0, "Latest")


def _archive(issues: list[PublicIssue]) -> str:
    body = '<div class="page-intro"><p class="kicker">The archive</p><h1>A weekly record of how policy change takes shape.</h1><p>Each edition connects immediate events, policy analysis, and useful research for a clearer view of sustainable development.</p></div>' + _archive_cards(issues, 1)
    return _page(f"Archive — {SITE_NAME}", "Browse past issues of SDG Weekly Compass.", body, 1, "Archive")


def _issue_page(issue: PublicIssue, issues: list[PublicIssue]) -> str:
    index = issues.index(issue)
    newer = issues[index - 1] if index > 0 else None
    older = issues[index + 1] if index < len(issues) - 1 else None
    older_link = "" if not older else f'<small>Previous issue</small><a href="../{older.date}/index.html">← {_e(_format_date(older.date, True))}</a>'
    newer_link = "" if not newer else f'<small>Next issue</small><a href="../{newer.date}/index.html">{_e(_format_date(newer.date, True))} →</a>'
    body = f'<div class="issue-hero"><p class="kicker">Issue · {_e(_format_date(issue.date))}</p><h1>{_e(issue.editorial or issue.subject)}</h1><div class="rule-and-topics"><span></span>{_topic_tags(issue.topics[:5])}</div></div>'
    body += _issue_content(issue)
    body += f'<nav class="issue-nav" aria-label="Issue navigation"><div>{older_link}</div><a href="../../archive/index.html">All issues</a><div class="next-issue">{newer_link}</div></nav>'
    return _page(f"{_format_date(issue.date)} — {SITE_NAME}", issue.editorial or issue.subject, body, 2)


def _search(issues: list[PublicIssue]) -> str:
    topic_options = sorted({topic for issue in issues for topic in issue.topics})
    options = "".join(f'<option value="{_e(topic)}">{_e(topic)}</option>' for topic in topic_options)
    body = f"""<div class="page-intro search-intro"><p class="kicker">Search the public record</p><h1>Follow an idea across weeks, sources, and forms.</h1></div>
<section class="search-panel">
  <label class="search-box"><span class="sr-only">Search archive</span><input id="search-input" type="search" placeholder="Search analysis, sources, authors…"><span aria-hidden="true">⌕</span></label>
  <div class="filter-row"><label>Format<select id="type-filter"><option>All</option><option>News</option><option>Research Signal</option><option>Research Reading</option></select></label><label>Topic<select id="topic-filter"><option>All topics</option>{options}</select></label><span id="result-count"></span></div>
</section>
<div id="search-results" class="search-results" aria-live="polite"></div>"""
    return _page(f"Search — {SITE_NAME}", "Search the English archive by topic, source, author, and analysis.", body, 1, "Search")


def _about() -> str:
    body = """<article class="prose-page"><header><p class="kicker">About the publication</p><h1>A compass, not a newswire.</h1></header>
<p class="standfirst">SDG Weekly Compass is an independent, non-commercial knowledge and information briefing connecting current events and policy research across climate, sustainable development, development finance, and global governance.</p>
<h2>Editorial method</h2><p>Each issue begins with updates from a defined list of institutional, research, journal, international-organization, and news sources. Items must have enough source text to evaluate. Obvious structural noise is excluded; relevant candidates are assessed semantically rather than admitted through keyword matching.</p><p>The final selection is intentionally short. We publish fewer items when the available material does not meet the editorial threshold. Previously covered URLs are excluded, and research-reading DOIs are not repeated merely to fill space.</p>
<h2>How AI is used</h2><p>AI assists with relevance screening, synthesis, and drafting structured editorial fields. It does not replace source attribution. Every external item links to the original publication, and research readings are restricted to approved journals or human-checked seed references.</p>
<h2>How to read the Compass</h2><div class="method-grid"><div><strong>Recent News</strong><p>Events whose immediate significance is worth recording.</p></div><div><strong>Research Signals</strong><p>Policy arguments interpreted through core claim, timing, and agenda position.</p></div><div><strong>Research Reading</strong><p>Selected research that supplies useful concepts and longer context.</p></div></div></article>"""
    return _page(f"About — {SITE_NAME}", "About SDG Weekly Compass and its editorial method.", body, 1, "About")


def _copyright() -> str:
    subject = quote("SDG Weekly Compass copyright or correction request")
    body = f"""<article class="prose-page"><header><p class="kicker">Copyright &amp; sources</p><h1>Original analysis, clear attribution.</h1></header>
<p class="standfirst">SDG Weekly Compass is a non-commercial knowledge-sharing project intended for learning, research, and public-interest discussion.</p>
<h2>Referenced works</h2><p>Article titles, source names, and linked materials remain the property of their respective owners. This site does not reproduce source articles or academic papers. It publishes original summaries and editorial analysis designed to guide readers to—not substitute for—the original works.</p><p>Every external entry identifies its source and publication date where available and provides a direct link to the original. Readers are encouraged to consult and support the original publishers.</p>
<h2>Corrections and removal</h2><p>If you are a rights holder or source representative and would like to request a correction, improved attribution, or removal of a public entry, please identify the article URL or DOI and the relevant issue date.</p>
<a class="contact-card" href="mailto:{CONTACT_EMAIL}?subject={subject}"><span>Copyright, attribution &amp; corrections</span><strong>{CONTACT_EMAIL}</strong><span aria-hidden="true">Write to us →</span></a>
<h2>Editorial independence</h2><p>The presence of a link does not imply endorsement by the original publisher, and SDG Weekly Compass is not affiliated with the institutions and publications it follows. The site makes no blanket claim that non-commercial status alone resolves copyright questions.</p></article>"""
    return _page(f"Copyright & Sources — {SITE_NAME}", "Copyright, source attribution, corrections, and removal policy.", body, 1)


def _search_index(issues: list[PublicIssue]) -> list[dict[str, object]]:
    return [
        {
            "id": item.item_id,
            "issueDate": item.issue_date,
            "type": item.item_type,
            "title": item.title,
            "source": item.source,
            "publishedDate": item.published_date,
            "url": item.url,
            "topics": item.topics,
            "text": "\n\n".join(item.paragraphs),
        }
        for issue in issues
        for item in issue.items
    ]


def build_site(archive_dir: Path, output_dir: Path, assets_dir: Path) -> list[PublicIssue]:
    issues = load_public_issues(archive_dir)
    staging_dir = output_dir.parent / f".{output_dir.name}-building"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)
    if output_dir.exists() and (output_dir / "CNAME").exists():
        shutil.copy2(output_dir / "CNAME", staging_dir / "CNAME")

    pages = {
        staging_dir / "index.html": _home(issues),
        staging_dir / "archive" / "index.html": _archive(issues),
        staging_dir / "search" / "index.html": _search(issues),
        staging_dir / "about" / "index.html": _about(),
        staging_dir / "copyright" / "index.html": _copyright(),
    }
    for issue in issues:
        pages[staging_dir / "issues" / issue.date / "index.html"] = _issue_page(issue, issues)
    for path, content in pages.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    output_assets = staging_dir / "assets"
    output_assets.mkdir(parents=True, exist_ok=True)
    for name in ("site.css", "site.js", "favicon.svg", "og.png"):
        source = assets_dir / name
        if source.exists():
            shutil.copy2(source, output_assets / name)
    (staging_dir / "search-index.json").write_text(json.dumps(_search_index(issues), ensure_ascii=False), encoding="utf-8")
    (staging_dir / ".nojekyll").write_text("", encoding="utf-8")
    backup_dir = output_dir.parent / f".{output_dir.name}-previous"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    if output_dir.exists():
        output_dir.replace(backup_dir)
    staging_dir.replace(output_dir)
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the public SDG Weekly Compass website")
    parser.add_argument("--archive", default="archive")
    parser.add_argument("--output", default="docs")
    parser.add_argument("--assets", default="website_assets")
    args = parser.parse_args()
    issues = build_site(Path(args.archive), Path(args.output), Path(args.assets))
    print(f"Built {len(issues)} public issues in {args.output}")


if __name__ == "__main__":
    main()
