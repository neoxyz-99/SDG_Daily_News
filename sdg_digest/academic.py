from __future__ import annotations

import html
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import date, timedelta
from urllib.parse import quote, urlencode
from urllib.error import HTTPError

from .http import fetch_text
from .models import Candidate, DeepRead, Source

CROSSREF_API = "https://api.crossref.org/v1"
DEFAULT_ACADEMIC_LOOKBACK_DAYS = 90
MIN_ABSTRACT_WORDS = 30
ACADEMIC_WORKERS = 2
CROSSREF_REQUEST_DELAY_SECONDS = 0.6
CROSSREF_MAX_ATTEMPTS = 3
MAX_QUERY_TERMS = 14

QUERY_STOPWORDS = {
    "about",
    "after",
    "against",
    "amid",
    "among",
    "from",
    "into",
    "over",
    "that",
    "their",
    "this",
    "through",
    "toward",
    "under",
    "what",
    "when",
    "where",
    "which",
    "with",
    "world",
}

TAG_QUERY_TERMS = {
    "#国际治理与多边主义": "global governance multilateralism international institutions",
    "#多边治理": "global governance multilateralism international institutions",
    "#发展与不平等": "development inequality Global South",
    "#发展不平等": "development inequality Global South",
    "#Global South": "Global South development inequality",
    "#环境治理与气候": "environmental governance climate policy",
    "#气候金融": "climate finance global governance",
    "#可持续金融与ESG": "sustainable finance ESG governance",
    "#地缘政治与治理": "geopolitics international relations governance",
}


def collect_academic_readings(
    sources: list[Source],
    candidates: list[Candidate],
    run_date: date,
    lookback_days: int = DEFAULT_ACADEMIC_LOOKBACK_DAYS,
    recent_per_journal: int = 3,
    classic_per_journal: int = 2,
) -> list[DeepRead]:
    """Trace both new and older topic-relevant papers in approved journals."""
    journal_sources = [source for source in sources if source.strategy == "crossref" and source.issn]
    if not journal_sources:
        return []

    query = _build_topic_query(candidates)
    results_by_source: dict[int, list[DeepRead]] = {}
    with ThreadPoolExecutor(max_workers=min(ACADEMIC_WORKERS, len(journal_sources))) as executor:
        futures = {
            executor.submit(
                _collect_journal,
                source,
                query,
                run_date,
                lookback_days,
                recent_per_journal,
                classic_per_journal,
            ): (index, source)
            for index, source in enumerate(journal_sources)
        }
        for future in as_completed(futures):
            index, source = futures[future]
            try:
                results_by_source[index] = future.result()
            except Exception as exc:
                print(f"Academic tracing fallback for {source.name}: {exc}")

    readings = [
        reading
        for index in range(len(journal_sources))
        for reading in results_by_source.get(index, [])
    ]

    unique: list[DeepRead] = []
    seen: set[str] = set()
    for reading in readings:
        identifier = _doi_key(reading.doi or reading.url)
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        unique.append(reading)
    print(
        f"Academic tracing found {len(unique)} paper(s) across {len(journal_sources)} approved journal(s): "
        f"{sum(reading.kind == 'tracked recent article' for reading in unique)} recent and "
        f"{sum(reading.kind == 'tracked classic article' for reading in unique)} historical."
    )
    return unique


def combine_academic_pool(
    tracked: list[DeepRead],
    samples: dict[str, list[DeepRead]],
) -> dict[str, list[DeepRead]]:
    """Keep the curated seven as examples, while making traced papers the open pool."""
    sample_by_doi = {
        _doi_key(reading.doi or reading.url): reading
        for readings in samples.values()
        for reading in readings
        if _doi_key(reading.doi or reading.url)
    }
    combined_tracked: list[DeepRead] = []
    traced_dois: set[str] = set()
    for reading in tracked:
        identifier = _doi_key(reading.doi or reading.url)
        traced_dois.add(identifier)
        sample = sample_by_doi.get(identifier)
        if sample:
            combined_tracked.append(
                replace(
                    sample,
                    published_date=reading.published_date,
                    abstract_en=reading.abstract_en,
                    discovery_score=reading.discovery_score,
                    kind=reading.kind,
                )
            )
        else:
            combined_tracked.append(reading)

    pool: dict[str, list[DeepRead]] = {"__tracked_journals__": combined_tracked}
    for tag, readings in samples.items():
        remaining = [reading for reading in readings if _doi_key(reading.doi or reading.url) not in traced_dois]
        if remaining:
            pool[tag] = remaining
    return pool


def _collect_journal(
    source: Source,
    query: str,
    run_date: date,
    lookback_days: int,
    recent_limit: int,
    classic_limit: int,
) -> list[DeepRead]:
    since = run_date - timedelta(days=lookback_days)
    before_since = since - timedelta(days=1)
    readings: list[DeepRead] = []
    for issn in source.issn:
        recent_filters = (
            f"from-pub-date:{since.isoformat()},until-pub-date:{run_date.isoformat()},"
            "type:journal-article,has-abstract:1"
        )
        recent_items = _fetch_crossref_works(
            issn,
            query,
            recent_filters,
            recent_limit,
            sort="published",
            order="desc",
        )
        readings.extend(_parse_works(recent_items, source, run_date, "tracked recent article"))

        classic_filters = (
            f"until-pub-date:{before_since.isoformat()},type:journal-article,has-abstract:1"
        )
        classic_items = _fetch_crossref_works(issn, query, classic_filters, classic_limit)
        readings.extend(_parse_works(classic_items, source, run_date, "tracked classic article"))
    return readings


def _fetch_crossref_works(
    issn: str,
    query: str,
    filters: str,
    rows: int,
    sort: str = "",
    order: str = "",
) -> list[dict]:
    params = {
        "filter": filters,
        "query.bibliographic": query,
        "rows": str(rows),
    }
    if sort:
        params["sort"] = sort
    if order:
        params["order"] = order
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto
    url = f"{CROSSREF_API}/journals/{quote(issn, safe='')}/works?{urlencode(params)}"
    payload: dict = {}
    for attempt in range(CROSSREF_MAX_ATTEMPTS):
        time.sleep(CROSSREF_REQUEST_DELAY_SECONDS if attempt == 0 else 2**attempt)
        try:
            payload = json.loads(fetch_text(url))
            break
        except HTTPError as exc:
            retryable = exc.code in {429, 500, 502, 503, 504}
            exc.close()
            if not retryable or attempt + 1 >= CROSSREF_MAX_ATTEMPTS:
                raise
    message = payload.get("message", {})
    items = message.get("items", []) if isinstance(message, dict) else []
    return [item for item in items if isinstance(item, dict)]


def _parse_works(
    works: list[dict],
    source: Source,
    run_date: date,
    kind: str,
) -> list[DeepRead]:
    readings: list[DeepRead] = []
    for work in works:
        doi = str(work.get("DOI", "")).strip()
        titles = work.get("title", [])
        title = _clean_markup(str(titles[0])) if isinstance(titles, list) and titles else ""
        abstract = _clean_markup(str(work.get("abstract", "")))
        published_date = _work_date(work)
        if not doi or not title or _word_count(abstract) < MIN_ABSTRACT_WORDS or not published_date:
            continue
        if published_date > run_date.isoformat():
            continue
        containers = work.get("container-title", [])
        journal = _clean_markup(str(containers[0])) if isinstance(containers, list) and containers else source.name
        authors = _authors(work.get("author", []))
        if not authors:
            continue
        readings.append(
            DeepRead(
                title=title,
                authors=authors,
                year=int(published_date[:4]),
                published_date=published_date,
                url=f"https://doi.org/{doi}",
                journal=journal or source.name,
                doi=doi,
                abstract_en=abstract,
                discovery_score=float(work.get("score", 0.0) or 0.0),
                tags=list(source.default_tags),
                kind=kind,
            )
        )
    return readings


def _build_topic_query(candidates: list[Candidate]) -> str:
    counts: Counter[str] = Counter()
    tag_terms: list[str] = []
    for candidate in candidates:
        for token in re.findall(r"[A-Za-z][A-Za-z-]{3,}", candidate.title.lower()):
            if token not in QUERY_STOPWORDS:
                counts[token] += 1
        for tag in candidate.tags:
            mapped = TAG_QUERY_TERMS.get(tag)
            if mapped:
                tag_terms.append(mapped)
    title_terms = [term for term, _ in counts.most_common(MAX_QUERY_TERMS)]
    context = " ".join(dict.fromkeys(tag_terms))
    return " ".join(
        part
        for part in [
            "global governance international relations political science",
            context,
            " ".join(title_terms),
        ]
        if part
    )


def _work_date(work: dict) -> str:
    for field in ("published-online", "published-print", "published", "issued", "created"):
        value = work.get(field, {})
        parts_rows = value.get("date-parts", []) if isinstance(value, dict) else []
        if not parts_rows or not isinstance(parts_rows[0], list) or not parts_rows[0]:
            continue
        parts = parts_rows[0]
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            continue
    return ""


def _authors(raw_authors: object) -> str:
    if not isinstance(raw_authors, list):
        return ""
    names: list[str] = []
    for author in raw_authors:
        if not isinstance(author, dict):
            continue
        name = " ".join(
            part.strip()
            for part in [str(author.get("given", "")), str(author.get("family", ""))]
            if part.strip()
        )
        if name:
            names.append(name)
    if len(names) > 6:
        return ", ".join(names[:6]) + ", et al."
    return ", ".join(names)


def _clean_markup(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _word_count(value: str) -> int:
    return len(re.findall(r"\b\w+\b", value))


def _doi_key(value: str) -> str:
    normalized = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :]
    return normalized
