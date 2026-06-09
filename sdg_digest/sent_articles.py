from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import Candidate, Digest

DEFAULT_SENT_ARTICLES = {"sent_urls": [], "last_updated": ""}
MAX_SENT_URLS = 500


def load_sent_articles(path: str | Path = "sent_articles.json") -> dict:
    record_path = Path(path)
    if not record_path.exists():
        record_path.write_text(json.dumps(DEFAULT_SENT_ARTICLES, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(DEFAULT_SENT_ARTICLES)
    with record_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    sent_urls = data.get("sent_urls", [])
    if not isinstance(sent_urls, list):
        sent_urls = []
    return {
        "sent_urls": [str(url) for url in sent_urls],
        "last_updated": str(data.get("last_updated", "")),
    }


def filter_sent_candidates(candidates: list[Candidate], record: dict) -> tuple[list[Candidate], int]:
    sent_urls = set(record.get("sent_urls", []))
    unseen = [candidate for candidate in candidates if candidate.url not in sent_urls]
    return unseen, len(candidates) - len(unseen)


def update_sent_articles(
    digest: Digest,
    run_date: date,
    path: str | Path = "sent_articles.json",
) -> dict:
    record = load_sent_articles(path)
    sent_urls = list(record.get("sent_urls", []))
    seen = set(sent_urls)
    for item in digest.items:
        if item.url not in seen:
            sent_urls.append(item.url)
            seen.add(item.url)
    record = {
        "sent_urls": sent_urls[-MAX_SENT_URLS:],
        "last_updated": run_date.isoformat(),
    }
    Path(path).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


# CHANGE 1 DONE: sent_articles.json is loaded, used for filtering, and updated after successful sends.
