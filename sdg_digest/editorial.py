"""Small archive-derived memory for editorial selection across issues."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import DigestItem, NewsBrief, TitleSupport
from .titles import validate_english_title


def validate_issue_title(
    payload: dict, news: list[NewsBrief], signals: list[DigestItem],
) -> tuple[str, str, list[TitleSupport]]:
    """Check traceable coverage; semantic connections remain an editorial judgment."""
    selected = {item.url: item for item in [*news, *signals]}
    if len(selected) < 2:
        # Do not promote a lone article into an issue-wide thesis.
        return "", "", []
    title_en = validate_english_title(payload.get("issue_title_en", ""))
    title_zh = payload.get("issue_title_zh", "")
    if not isinstance(title_zh, str) or not title_zh.strip():
        raise ValueError("issue_title_zh is required")
    if not 6 <= len(title_en.split()) <= 16:
        raise ValueError("issue_title_en must be a concise 6–16 word issue title")
    normalize = lambda value: " ".join(value.casefold().split()).strip(".?!")
    if any(normalize(title_en) == normalize(item.title_en) for item in selected.values()):
        raise ValueError("An issue title must not copy an individual article title")
    rows = payload.get("title_support")
    if not isinstance(rows, list):
        raise ValueError("title_support must identify the selected articles behind the title")
    support: list[TitleSupport] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each title_support entry needs a selected URL and an angle_en")
        url, angle = row.get("url"), row.get("angle_en")
        if not isinstance(url, str) or url not in selected:
            raise ValueError("title_support may only cite articles actually selected for this issue")
        if url in seen:
            raise ValueError("title_support must cite distinct articles")
        if not isinstance(angle, str) or len(angle.split()) < 5:
            raise ValueError("title_support.angle_en must explain the article's connection to the title")
        seen.add(url)
        support.append(TitleSupport(url, angle.strip()))
    if len(seen) < 2:
        raise ValueError("The issue title must be supported by at least two distinct selected articles")
    research_urls = {item.url for item in signals}
    required_research = len(research_urls) // 2 + 1 if research_urls else 0
    if len(seen & research_urls) < required_research:
        raise ValueError("The issue title must cover a majority of the selected research signals")
    return title_en, title_zh.strip(), support


def load_editorial_history(archive_dir: str | Path, run_date: date, limit: int = 6) -> list[dict]:
    if limit <= 0:
        return []
    history = []
    for path in sorted(Path(archive_dir).glob("*/digest.json"), reverse=True):
        try:
            issue_date = date.fromisoformat(path.parent.name)
            if issue_date >= run_date:
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
            signals = raw.get("research_signals") or raw.get("items") or []
            items = (raw.get("recent_news") or []) + signals
            history.append({
                "date": issue_date.isoformat(),
                "issue_title": raw.get("issue_title_en") or raw.get("overview_en", ""),
                "editorial_note": raw.get("overview_en", ""),
                "weekly_thread": raw.get("weekly_thread_en", ""),
                "articles": [{
                    "title": item.get("title_en", ""),
                    "source": item.get("source_org", ""),
                    "angle": item.get("core_argument_en") or item.get("one_sentence_en", ""),
                } for item in items if isinstance(item, dict)],
            })
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        if len(history) >= limit:
            break
    return history
