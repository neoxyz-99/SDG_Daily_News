from __future__ import annotations

import html
import math
import re
from collections import Counter
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from xml.etree import ElementTree

from .http import fetch_text
from .models import Candidate, Source

MIN_FEED_WORDS = 50
TITLE_SIMILARITY_THRESHOLD = 0.85


def collect_candidates(
    sources: list[Source],
    run_date: date,
    lookback_days: int,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for source in sources:
        if source.strategy != "rss" or not source.url:
            print(f"Skipping source {source.name}: only RSS/Atom feeds are supported")
            continue
        try:
            candidates.extend(_collect_rss(source, run_date))
        except Exception as exc:
            print(f"Skipping source {source.name}: {exc}")

    since = run_date - timedelta(days=lookback_days)
    return [
        candidate
        for candidate in candidates
        if is_allowed_url(candidate.url, _source_domains(sources, candidate.source_org))
        and _within_lookback(candidate.published_date, since, run_date)
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
    for entry in entries[:40]:
        title = _xml_text(entry, ["title", "{http://www.w3.org/2005/Atom}title"])
        link = _entry_link(entry)
        published = _xml_text(
            entry,
            [
                "pubDate",
                "published",
                "updated",
                "{http://www.w3.org/2005/Atom}published",
                "{http://www.w3.org/2005/Atom}updated",
                "{http://purl.org/dc/elements/1.1/}date",
            ],
        )
        summary = _entry_summary(entry)
        if not title or not link:
            continue
        source_text = _clean_text(summary)
        if _word_count(source_text) < MIN_FEED_WORDS:
            continue
        candidates.append(
            Candidate(
                title=_clean_text(title),
                source_org=source.name,
                source_type=source.type,
                published_date=_normalize_date(published, run_date),
                url=link.strip(),
                summary_hint=source_text,
                tags=[],
                discovered_date=run_date.isoformat(),
            )
        )
    return candidates


def _entry_link(entry: ElementTree.Element) -> str:
    link = _xml_text(entry, ["link"])
    if link:
        return link
    for atom_link in entry.findall("{http://www.w3.org/2005/Atom}link"):
        rel = atom_link.attrib.get("rel", "alternate")
        href = atom_link.attrib.get("href", "")
        if href and rel in {"alternate", ""}:
            return href
    return _xml_text(entry, ["guid"])


def _entry_summary(entry: ElementTree.Element) -> str:
    return _xml_text(
        entry,
        [
            "description",
            "summary",
            "content",
            "{http://www.w3.org/2005/Atom}summary",
            "{http://www.w3.org/2005/Atom}content",
            "{http://purl.org/rss/1.0/modules/content/}encoded",
        ],
    )


def is_allowed_url(url: str, allowed_domains: list[str]) -> bool:
    host = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def deduplicate_candidates(candidates: list[Candidate]) -> list[Candidate]:
    unique: list[Candidate] = []
    seen_urls: set[str] = set()
    title_vectors: list[Counter[str]] = []
    for candidate in candidates:
        url_key = _canonical_url(candidate.url)
        if url_key in seen_urls:
            continue
        title_vector = _title_vector(candidate.title)
        if any(_cosine_similarity(title_vector, existing) > TITLE_SIMILARITY_THRESHOLD for existing in title_vectors):
            continue
        seen_urls.add(url_key)
        title_vectors.append(title_vector)
        unique.append(candidate)
    return unique


def rank_candidates(candidates: list[Candidate], max_items: int = 30) -> list[Candidate]:
    scored = sorted(candidates, key=_score_candidate, reverse=True)
    return scored[:max_items]


def _score_candidate(candidate: Candidate) -> tuple[int, str]:
    source_score = {"international_org": 3, "think_tank": 2, "journal": 1}.get(candidate.source_type, 1)
    text_score = min(_word_count(candidate.summary_hint), 300) // 25
    return (source_score + text_score, candidate.published_date)


def _within_lookback(published_date: str, since: date, run_date: date) -> bool:
    parsed = _parse_iso_date(published_date)
    return parsed is None or since <= parsed <= run_date


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
        return datetime.fromisoformat(value[:10].replace("Z", "+00:00")).date()
    except Exception:
        return None


def _xml_text(entry: ElementTree.Element, names: list[str]) -> str:
    for name in names:
        child = entry.find(name)
        if child is not None and child.text:
            return child.text
    return ""


def _clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return html.unescape(re.sub(r"\s+", " ", without_tags)).strip()


def _word_count(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value or ""))


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl().rstrip("/").lower()


def _title_vector(title: str) -> Counter[str]:
    return Counter(re.findall(r"[a-z0-9]+", title.lower()))


def _cosine_similarity(first: Counter[str], second: Counter[str]) -> float:
    if not first or not second:
        return 0.0
    common = set(first) & set(second)
    numerator = sum(first[token] * second[token] for token in common)
    first_norm = math.sqrt(sum(count * count for count in first.values()))
    second_norm = math.sqrt(sum(count * count for count in second.values()))
    if not first_norm or not second_norm:
        return 0.0
    return numerator / (first_norm * second_norm)
