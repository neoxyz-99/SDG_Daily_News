"""Small archive-derived memory for editorial selection across issues."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path


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
