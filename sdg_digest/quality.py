"""Publication checks shared by generation, archive, email and the public site."""
from dataclasses import asdict
import re


def clean_source_text(text: str) -> str:
    text = re.sub(r"^\s*(?:Abstract|Summary)\s*[:.\-]?\s+", "", text or "", flags=re.I)
    text = re.sub(r"^.*?Published online:\s*[^;]+;\s*doi:\S+\s*", "", text, flags=re.I)
    return text.strip()


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Publication requires {field}")
    if re.search(r"reports a relevant development|published a new item related to|"
                 r"agenda background is unclear|议程背景不明确|"
                 r"timing should be interpreted alongside|发布或转发的这条要闻显示|"
                 r"Published online:|\bdoi:\s*10\.|^\s*Abstract\b", value, re.I):
        raise ValueError(f"Placeholder or source metadata in {field}")
    if value.rstrip().endswith(("…", "...")):
        raise ValueError(f"Truncated source excerpt in {field}")


def validate_publication(digest, *, check_title=True):
    raw = digest if isinstance(digest, dict) else asdict(digest)
    if raw.get("generation_mode") not in {"ai", "reviewed"}:
        raise ValueError("Only validated editorial drafts can be published; preview/fallback blocked")
    news = raw.get("recent_news") or []
    signals = raw.get("research_signals") or raw.get("items") or []
    if not news and not signals:
        raise ValueError("Refusing to publish an empty edition")
    if check_title and len(news) + len(signals) >= 2:
        for field in ("issue_title_en", "issue_title_zh"):
            _text(raw.get(field), field)
    for item in news + signals:
        _text(item.get("title_en"), "article title")
        if re.search(r"[–—-]\s*report\s*$", item["title_en"], re.I):
            raise ValueError("Use an informative editorial headline, without a trailing report label")
    for item in news:
        for field in ("one_sentence_en", "one_sentence_zh"):
            _text(item.get(field), field)
    for item in signals:
        for field in ("core_argument_en", "core_argument_zh", "why_now_en", "why_now_zh",
                      "agenda_position_en", "agenda_position_zh"):
            _text(item.get(field), field)
    for reading in raw.get("classic_readings") or raw.get("readings") or []:
        for field in ("note_en", "note_zh", "method_en", "methodology_zh"):
            _text(reading.get(field), field)
        abstract = clean_source_text(reading.get("abstract_en", ""))
        note = clean_source_text(reading["note_en"])
        words = re.findall(r"\w+", abstract.lower())
        note_words = re.findall(r"\w+", note.lower())
        if len(words) >= 20:
            # A long verbatim span is an excerpt, not an editorial interpretation.
            source = " ".join(words)
            if any(" ".join(note_words[i:i+25]) in source for i in range(max(0, len(note_words)-24))):
                raise ValueError("Reading note copies the source abstract; write a concise interpretation")
        if re.search(r"comparative.*method|sociotechnical analysis|regression|interviews|randomi[sz]ed", abstract, re.I) and re.search(
                r"does not (?:provide|specify|identify)|not specified|no .*method", reading["method_en"], re.I):
            raise ValueError("Method disclaimer contradicts explicit method evidence in the abstract")
