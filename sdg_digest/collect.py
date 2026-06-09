from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urljoin, urlparse
from xml.etree import ElementTree

from .http import fetch_text
from .models import Candidate, Source

KEYWORDS = (
    "sdg",
    "sustainable development",
    "climate finance",
    "loss and damage",
    "adaptation finance",
    "mitigation",
    "green transition",
    "ndc",
    "debt",
    "global south",
    "esg",
    "carbon",
    "net zero",
    "development finance",
    "disaster",
    "disaster risk",
    "earthquake",
    "flood",
    "typhoon",
    "drought",
    "resilience",
    "food security",
    "humanitarian",
    "infrastructure",
)


def collect_candidates(
    sources: list[Source],
    run_date: date,
    lookback_days: int,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for source in sources:
        try:
            if source.strategy == "rss" and source.url:
                candidates.extend(_collect_rss(source, run_date))
            elif source.strategy == "page" and source.url:
                candidates.extend(_collect_page(source, run_date, lookback_days))
            elif source.strategy == "crossref":
                candidates.extend(_collect_crossref(source, run_date, lookback_days))
        except Exception as exc:
            print(f"Skipping source {source.name}: {exc}")

    since = run_date - timedelta(days=lookback_days)
    return [
        candidate
        for candidate in candidates
        if is_allowed_url(candidate.url, _source_domains(sources, candidate.source_org))
        and _within_lookback(candidate.published_date, since, run_date)
        and _is_relevant(candidate)
    ]


def _source_domains(sources: list[Source], source_name: str) -> list[str]:
    for source in sources:
        if source.name == source_name:
            return source.allowed_domains
    return []


def _collect_rss(source: Source, run_date: date) -> list[Candidate]:
    text = fetch_text(source.url or "")
    root = ElementTree.fromstring(text)
    entries = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    candidates: list[Candidate] = []
    for entry in entries[:30]:
        title = _xml_text(entry, ["title", "{http://www.w3.org/2005/Atom}title"])
        link = _xml_text(entry, ["link"])
        if not link:
            atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
            link = atom_link.attrib.get("href", "") if atom_link is not None else ""
        published = _xml_text(
            entry,
            [
                "pubDate",
                "published",
                "updated",
                "{http://www.w3.org/2005/Atom}published",
                "{http://www.w3.org/2005/Atom}updated",
            ],
        )
        summary = _xml_text(
            entry,
            [
                "description",
                "summary",
                "{http://www.w3.org/2005/Atom}summary",
                "{http://www.w3.org/2005/Atom}content",
            ],
        )
        if title and link:
            candidates.append(
                Candidate(
                    title=_clean_text(title),
                    source_org=source.name,
                    source_type=source.type,
                    published_date=_normalize_date(published, run_date),
                    url=link.strip(),
                    summary_hint=_clean_text(summary),
                    tags=source.default_tags,
                    discovered_date=run_date.isoformat(),
                )
            )
    return candidates


def _collect_page(source: Source, run_date: date, lookback_days: int) -> list[Candidate]:
    text = fetch_text(source.url or "")
    anchors = re.findall(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", text, re.I | re.S)
    candidates: list[Candidate] = []
    seen: set[str] = set()
    since = run_date - timedelta(days=lookback_days)
    for href, raw_title in anchors:
        title = _clean_text(re.sub(r"<[^>]+>", " ", raw_title))
        if len(title) < 18 or title.startswith(("http://", "https://")):
            continue
        link = urljoin(source.url or "", html.unescape(href))
        if (
            link in seen
            or not is_allowed_url(link, source.allowed_domains)
            or _url_has_outdated_year(link, since, run_date)
        ):
            continue
        seen.add(link)
        summary_hint = _fetch_page_summary(link)
        candidates.append(
            Candidate(
                title=title,
                source_org=source.name,
                source_type=source.type,
                published_date=run_date.isoformat(),
                url=link,
                summary_hint=summary_hint,
                tags=source.default_tags,
                discovered_date=run_date.isoformat(),
            )
        )
        if len(candidates) >= 20:
            break
    return candidates


def _collect_crossref(source: Source, run_date: date, lookback_days: int) -> list[Candidate]:
    candidates: list[Candidate] = []
    from_date = (run_date - timedelta(days=lookback_days)).isoformat()
    for issn in source.issn:
        url = (
            f"https://api.crossref.org/journals/{quote(issn)}/works"
            f"?filter=from-pub-date:{from_date},type:journal-article"
            "&sort=published&order=desc&rows=15"
        )
        data = json.loads(fetch_text(url))
        for item in data.get("message", {}).get("items", []):
            title = " ".join(item.get("title") or [])
            doi = item.get("DOI")
            link = f"https://doi.org/{doi}" if doi else item.get("URL", "")
            published = _crossref_date(item) or run_date.isoformat()
            abstract = _clean_text(re.sub(r"<[^>]+>", " ", item.get("abstract", "")))
            if title and link:
                candidates.append(
                    Candidate(
                        title=_clean_text(title),
                        source_org=source.name,
                        source_type=source.type,
                        published_date=published,
                        url=link,
                        summary_hint=abstract,
                        tags=source.default_tags,
                        discovered_date=run_date.isoformat(),
                        doi=doi,
                    )
                )
    return candidates


def is_allowed_url(url: str, allowed_domains: list[str]) -> bool:
    host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def deduplicate_candidates(candidates: list[Candidate]) -> list[Candidate]:
    unique: list[Candidate] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    seen_dois: set[str] = set()
    for candidate in candidates:
        url_key = _canonical_url(candidate.url)
        title_key = _title_key(candidate.title)
        doi_key = candidate.doi.lower() if candidate.doi else ""
        if url_key in seen_urls or title_key in seen_titles or (doi_key and doi_key in seen_dois):
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        if doi_key:
            seen_dois.add(doi_key)
        unique.append(candidate)
    return unique


def rank_candidates(candidates: list[Candidate], max_items: int = 8) -> list[Candidate]:
    scored = sorted(candidates, key=_score_candidate, reverse=True)
    return scored[:max_items]


def _score_candidate(candidate: Candidate) -> tuple[int, str]:
    text = f"{candidate.title} {candidate.summary_hint}".lower()
    keyword_score = sum(2 for keyword in KEYWORDS if keyword in text)
    tag_score = len(candidate.tags)
    source_score = {"journal": 4, "international_org": 3, "think_tank": 2}.get(candidate.source_type, 1)
    hint_score = _source_excerpt_score(candidate.summary_hint)
    return (keyword_score + tag_score + source_score + hint_score, candidate.published_date)


def _source_excerpt_score(source_excerpt: str) -> int:
    length = len(" ".join((source_excerpt or "").split()))
    if length >= 500:
        return 5
    if length >= 300:
        return 4
    if length >= 160:
        return 3
    if length >= 80:
        return 2
    if length > 0:
        return 1
    return 0


def _is_relevant(candidate: Candidate) -> bool:
    text = f"{candidate.title} {candidate.summary_hint} {' '.join(candidate.tags)}".lower()
    return any(keyword in text for keyword in KEYWORDS) or any(
        tag in candidate.tags for tag in ("#NDC", "#气候金融", "#SDG进展", "#绿色转型", "#债务可持续性", "#Global South")
    )


def _within_lookback(published_date: str, since: date, run_date: date) -> bool:
    parsed = _parse_iso_date(published_date)
    return parsed is None or since <= parsed <= run_date


def _url_has_outdated_year(url: str, since: date, run_date: date) -> bool:
    years = {int(value) for value in re.findall(r"/(20\d{2})(?:/|-)", url)}
    if not years:
        return False
    allowed_years = set(range(since.year, run_date.year + 1))
    return not any(year in allowed_years for year in years)


def _normalize_date(value: str, fallback: date) -> str:
    value = (value or "").strip()
    if not value:
        return fallback.isoformat()
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except Exception:
        parsed = _parse_iso_date(value)
        return parsed.isoformat() if parsed else fallback.isoformat()


def _parse_iso_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value[:10]).date()
    except Exception:
        return None


def _crossref_date(item: dict) -> str | None:
    for key in ("published-print", "published-online", "published", "issued"):
        parts = item.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            year, month, day = (parts[0] + [1, 1])[:3]
            return date(int(year), int(month), int(day)).isoformat()
    return None


def _xml_text(entry: ElementTree.Element, names: list[str]) -> str:
    for name in names:
        child = entry.find(name)
        if child is not None and child.text:
            return child.text
    return ""


def _clean_text(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", value or "")).strip()


def _fetch_page_summary(url: str) -> str:
    try:
        text = fetch_text(url, timeout=12)
    except Exception:
        return ""
    return _extract_page_summary(text)


def _extract_page_summary(text: str, max_chars: int = 1800) -> str:
    clean_html = re.sub(r"<(script|style|noscript)\b[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
    paragraphs = []
    article_matches = re.findall(r"<article\b[^>]*>(.*?)</article>", clean_html, re.I | re.S)
    paragraph_sources = article_matches or [clean_html]
    for source in paragraph_sources:
        for raw in re.findall(r"<p\b[^>]*>(.*?)</p>", source, re.I | re.S):
            paragraph = _clean_text(re.sub(r"<[^>]+>", " ", raw))
            lower = paragraph.lower()
            if len(paragraph) >= 50 and not lower.startswith(("cookie", "subscribe", "sign up", "share this")):
                paragraphs.append(paragraph)
            if len(" ".join(paragraphs)) >= max_chars:
                break
        if paragraphs:
            break

    body_excerpt = " ".join(paragraphs)
    meta_excerpt = ""
    for pattern in (
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
    ):
        match = re.search(pattern, text, re.I | re.S)
        if match:
            meta_excerpt = _clean_text(match.group(1))
            break

    if body_excerpt and meta_excerpt and meta_excerpt not in body_excerpt:
        return f"{meta_excerpt} {body_excerpt}"[:max_chars]
    return (body_excerpt or meta_excerpt)[:max_chars]


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl().rstrip("/").lower()


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())[:120]
