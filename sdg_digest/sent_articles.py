from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import Candidate, Digest

DEFAULT_SENT_ARTICLES = {
    "sent_urls": [],
    "recent_news_urls": [],
    "research_signal_urls": [],
    "classic_reading_dois": [],
    "classic_reading_history": [],
    "last_updated": "",
}
MAX_SENT_URLS = 500
MAX_CLASSIC_READING_ISSUES = 24


def load_sent_articles(path: str | Path = "sent_articles.json") -> dict:
    record_path = Path(path)
    if not record_path.exists():
        record_path.write_text(json.dumps(DEFAULT_SENT_ARTICLES, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(DEFAULT_SENT_ARTICLES)
    with record_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    sent_urls = _as_url_list(data.get("sent_urls", []))
    recent_news_urls = _as_url_list(data.get("recent_news_urls", []))
    research_signal_urls = _as_url_list(data.get("research_signal_urls", []))
    classic_reading_dois = _as_url_list(data.get("classic_reading_dois", []))
    classic_reading_history = _as_reading_history(data.get("classic_reading_history", []))
    return {
        "sent_urls": sent_urls,
        "recent_news_urls": recent_news_urls,
        "research_signal_urls": research_signal_urls,
        "classic_reading_dois": classic_reading_dois,
        "classic_reading_history": classic_reading_history,
        "last_updated": str(data.get("last_updated", "")),
    }


def filter_sent_candidates(candidates: list[Candidate], record: dict) -> tuple[list[Candidate], int]:
    legacy_urls = set(record.get("sent_urls", []))
    recent_news_urls = set(record.get("recent_news_urls", []))
    research_signal_urls = set(record.get("research_signal_urls", []))
    unseen = [
        candidate
        for candidate in candidates
        if candidate.url not in legacy_urls
        and candidate.url not in (recent_news_urls if candidate.layer in {"event", "news"} else research_signal_urls)
    ]
    return unseen, len(candidates) - len(unseen)


def update_sent_articles(
    digest: Digest,
    run_date: date,
    path: str | Path = "sent_articles.json",
) -> dict:
    record = load_sent_articles(path)
    sent_urls = list(record.get("sent_urls", []))
    recent_news_urls = list(record.get("recent_news_urls", []))
    research_signal_urls = list(record.get("research_signal_urls", []))
    classic_reading_dois = list(record.get("classic_reading_dois", []))
    classic_reading_history = list(record.get("classic_reading_history", []))

    _append_unique(sent_urls, [item.url for item in [*digest.recent_news, *digest.research_signals, *digest.items]])
    _append_unique(recent_news_urls, [item.url for item in digest.recent_news])
    _append_unique(research_signal_urls, [item.url for item in [*digest.research_signals, *digest.items]])
    readings = digest.classic_readings or digest.readings
    issue_reading_dois = list(
        dict.fromkeys(_reading_identifier(reading.doi, reading.url) for reading in readings)
    )
    issue_reading_dois = [doi for doi in issue_reading_dois if doi]
    _append_unique(classic_reading_dois, issue_reading_dois)
    classic_reading_history = [
        issue for issue in classic_reading_history if issue.get("date") != run_date.isoformat()
    ]
    if issue_reading_dois:
        classic_reading_history.append({"date": run_date.isoformat(), "dois": issue_reading_dois})
    record = {
        "sent_urls": sent_urls[-MAX_SENT_URLS:],
        "recent_news_urls": recent_news_urls[-MAX_SENT_URLS:],
        "research_signal_urls": research_signal_urls[-MAX_SENT_URLS:],
        "classic_reading_dois": classic_reading_dois[-MAX_SENT_URLS:],
        "classic_reading_history": classic_reading_history[-MAX_CLASSIC_READING_ISSUES:],
        "last_updated": run_date.isoformat(),
    }
    Path(path).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


# CHANGE 1 DONE: sent_articles.json is loaded, used for filtering, and updated after successful sends.
# WEEKLY MODULE DEDUP DONE: sent history is stored separately for all three newsletter modules.


def _as_url_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(url) for url in value if str(url).strip()]


def _as_reading_history(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    history: list[dict[str, object]] = []
    for issue in value:
        if not isinstance(issue, dict):
            continue
        issue_date = str(issue.get("date", "")).strip()
        dois = [_reading_identifier(str(doi), "") for doi in _as_url_list(issue.get("dois", []))]
        dois = list(dict.fromkeys(doi for doi in dois if doi))
        if issue_date and dois:
            history.append({"date": issue_date, "dois": dois})
    return history[-MAX_CLASSIC_READING_ISSUES:]


def _reading_identifier(doi: str, url: str) -> str:
    value = (doi or url).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    return value


def _append_unique(target: list[str], urls: list[str]) -> None:
    seen = set(target)
    for url in urls:
        if url and url not in seen:
            target.append(url)
            seen.add(url)
