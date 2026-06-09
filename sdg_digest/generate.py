from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from .http import post_json
from .models import Candidate, DeepRead, Digest, DigestItem, DigestTerm, ResearchDirection

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 180
OPENAI_MAX_ATTEMPTS = 2
MIN_NEWS_ITEMS = 3
MIN_RELEVANT_CANDIDATES = 10

TAG_REGISTRY = [
    "#气候金融",
    "#NDC",
    "#SDG进展",
    "#绿色转型",
    "#债务可持续性",
    "#Global South",
    "#发展不平等",
    "#多边治理",
    "#碳市场",
    "#粮食与土地",
    "#数字基础设施",
    "#主权债务",
    "#能源转型",
    "#生物多样性",
]

BANNED_EMPTY_PHRASES = ["至关重要", "意义深远", "备受关注", "在全球化背景下"]
BROAD_TAGS = {"#气候变化", "气候变化", "#可持续发展", "可持续发展"}

TERM_LIBRARY = {
    "#气候金融": DigestTerm(
        "climate finance",
        "气候金融",
        "用于减缓、适应、损失与损害等气候行动的公共或私人资金安排。",
    ),
    "#NDC": DigestTerm(
        "NDC",
        "国家自主贡献",
        "各国在《巴黎协定》下提交的减排、适应和支持目标，是观察气候治理雄心的重要入口。",
    ),
    "#SDG进展": DigestTerm(
        "SDG implementation",
        "SDG 落实",
        "将联合国可持续发展目标转化为国家政策、预算、项目和评估机制的过程。",
    ),
    "#绿色转型": DigestTerm(
        "green transition",
        "绿色转型",
        "经济结构、产业政策和投资方向向低碳、资源高效和韧性发展转变的过程。",
    ),
    "#债务可持续性": DigestTerm(
        "debt sustainability",
        "债务可持续性",
        "一国在不牺牲长期发展能力的情况下持续偿付债务并保持财政空间的能力。",
    ),
    "#Global South": DigestTerm(
        "Global South",
        "全球南方",
        "通常指在全球经济与气候治理中面临发展约束、融资缺口和规则不平等的国家和地区。",
    ),
    "#多边治理": DigestTerm(
        "multilateral governance",
        "多边治理",
        "国家、国际组织和非国家行为体围绕共同问题形成规则、协调行动和分配责任的机制。",
    ),
}


def filter_relevant_candidates(
    candidates: list[Candidate],
    use_openai: bool = True,
) -> list[Candidate]:
    if not use_openai:
        print("AI relevance check skipped")
        return candidates
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set; cannot run AI relevance check")

    relevant: list[Candidate] = []
    for candidate in candidates:
        if _candidate_is_relevant(candidate):
            relevant.append(candidate)
    if len(relevant) < MIN_RELEVANT_CANDIDATES:
        print(
            f"Warning: only {len(relevant)} candidate(s) passed AI relevance check; "
            f"continuing below the target of {MIN_RELEVANT_CANDIDATES}."
        )
    return relevant


def generate_digest(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    run_date: date,
    max_items: int,
    use_openai: bool = True,
) -> Digest:
    allow_fallback = os.getenv("ALLOW_OPENAI_FALLBACK", "").lower() == "true"
    if use_openai and candidates:
        if not os.getenv("OPENAI_API_KEY"):
            if allow_fallback:
                return fallback_digest(candidates[:max_items], bibliography, run_date)
            raise RuntimeError("OPENAI_API_KEY is not set; refusing to publish fallback digest")

        feedback = ""
        last_exc: Exception | None = None
        for attempt in range(OPENAI_MAX_ATTEMPTS):
            try:
                raw = _call_openai(candidates, bibliography, run_date, max_items, feedback=feedback)
                return validate_digest_payload(raw, candidates, bibliography, run_date)
            except ValueError as exc:
                last_exc = exc
                feedback = (
                    f"The previous draft failed validation: {exc}. Rewrite the full JSON output. "
                    "Use only the provided feed summaries as source material. Preserve bibliography prose. "
                    "Do not use empty rhetoric, invented agenda timing, or generated literature references."
                )
                if attempt + 1 < OPENAI_MAX_ATTEMPTS:
                    print(f"OpenAI draft failed validation; retrying with stricter instructions: {exc}")
                    continue
                break
            except TimeoutError as exc:
                last_exc = exc
                if attempt + 1 < OPENAI_MAX_ATTEMPTS:
                    print(f"OpenAI request timed out; retrying attempt {attempt + 2}/{OPENAI_MAX_ATTEMPTS}")
                    continue
                break
            except OSError as exc:
                last_exc = exc
                if _is_timeout_exception(exc) and attempt + 1 < OPENAI_MAX_ATTEMPTS:
                    print(f"OpenAI request timed out; retrying attempt {attempt + 2}/{OPENAI_MAX_ATTEMPTS}")
                    continue
                break
            except Exception as exc:
                last_exc = exc
                break

        exc = last_exc or RuntimeError("OpenAI generation failed for an unknown reason")
        if allow_fallback:
            print(f"OpenAI generation failed, using deterministic fallback: {exc}")
            return fallback_digest(candidates[:max_items], bibliography, run_date)
        raise RuntimeError(f"OpenAI generation failed; refusing to publish fallback digest: {exc}") from exc
    return fallback_digest(candidates[:max_items], bibliography, run_date)


def _candidate_is_relevant(candidate: Candidate) -> bool:
    prompt = {
        "question": (
            "Does this item contain a substantive argument, policy finding, or research result related to any "
            "of the following domains: sustainable development, climate policy, development finance, global "
            "governance, green transition, inequality, or multilateral institutions?"
        ),
        "reject_if": "cultural events, sports, or purely human-interest stories with no policy substance",
        "title": candidate.title,
        "source": candidate.source_org,
        "feed_summary": candidate.summary_hint,
        "answer_format": "Return only yes or no.",
    }
    payload = {
        "model": os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        "input": [
            {
                "role": "system",
                "content": "You are a strict policy-news relevance classifier. Return only yes or no.",
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    }
    response = post_json(
        OPENAI_RESPONSES_URL,
        payload,
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        timeout=_openai_timeout_seconds(),
    )
    answer = _extract_response_text(response).strip().lower()
    return answer.startswith("yes")


def _call_openai(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    run_date: date,
    max_items: int,
    feedback: str = "",
) -> dict[str, Any]:
    prompt = {
        "run_date": run_date.isoformat(),
        "editorial_role": (
            "You are the editorial AI for The Governance Brief, a daily newsletter serving policy researchers "
            "and graduate students working on global governance, climate finance, and sustainable development."
        ),
        "reader_profile": (
            "Readers understand multilateral governance, climate finance, and SDG frameworks. Do not explain "
            "basic concepts; provide analytical density."
        ),
        "editorial_scope": [
            "Climate policy, sustainable development, development finance, global governance, green transition, inequality, and multilateral institutions.",
            "The candidates already passed source whitelist and AI relevance checks.",
            "Use the feed_summary field as the source text. Do not assume you have read the linked webpage.",
        ],
        "tag_registry": TAG_REGISTRY,
        "instructions": [
            "Return a JSON object that follows the schema.",
            "Your role is not to summarize information; help readers understand what is happening, why it matters now, and how theoretical frameworks explain underlying tensions.",
            "Select the strongest 3-5 news items. Prefer 4-5 when enough candidates exist. If fewer than 3 candidates are provided, select every usable candidate instead of padding or inventing items.",
            "daily_editorial_note_zh must be under 100 Chinese characters, raise a core tension or open question across selected news, and name conflicts or convergence among actor logics. If fewer than 2 news items are selected, return null.",
            "weekly_thread_zh should be 1-2 Chinese sentences only when at least 2 selected news items share a related issue; otherwise return null.",
            "For each selected item, write core_argument_zh as one Chinese sentence describing what the article argues, not what it covers. Do not make a statistic the core argument and do not restate the title.",
            "For each selected item, write why_now_zh in 1-2 Chinese sentences with an explicit temporal anchor: what it responds to, advances, or challenges. If timing cannot be inferred from the provided feed text, say so rather than guessing.",
            "For each selected item, write agenda_position_zh as one Chinese sentence. If the agenda background is unclear, write exactly: 议程背景不明确.",
            "Assign 1-3 Chinese tags after selection. Tags must be specific to the article content; avoid broad tags such as 气候变化 or 可持续发展.",
            "Select 2-3 deep reads from bibliography. Use only bibliography entries.",
            "For each selected deep read, output only its identity fields, today_connection_zh, and two research_directions.",
            "today_connection_zh must explicitly connect the theoretical frame to one selected news item. If no real connection exists, write: 本期暂无直接关联，建议结合[议题方向]阅读",
            "Each research direction must include one Chinese research-question direction under 30 Chinese characters and 3-5 English search keywords. Do not cite any specific literature title, author, or publication.",
            "Do not rewrite bibliography prose briefs, methodology notes, authors, years, journals, DOIs, or links.",
            "Do not invent URLs, sources, readings, dates, authors, journals, DOIs, data, or literature.",
            "Avoid empty rhetoric including 至关重要, 意义深远, 备受关注, and 在全球化背景下.",
        ],
        "candidates": [_candidate_payload(candidate) for candidate in candidates[:30]],
        "bibliography": [
            _reading_payload(reading)
            for readings in bibliography.values()
            for reading in readings
        ],
    }
    if feedback:
        prompt["validation_feedback"] = feedback
    payload = {
        "model": os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        "input": [
            {
                "role": "system",
                "content": (
                    "You are a bilingual policy research editor for The Governance Brief. You write analytical "
                    "editorial fields from provided feed text, classify tags after selection, and preserve approved bibliography prose."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "governance_brief",
                "strict": True,
                "schema": _digest_schema(max_items),
            }
        },
    }
    response = post_json(
        OPENAI_RESPONSES_URL,
        payload,
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        timeout=_openai_timeout_seconds(),
    )
    return json.loads(_extract_response_text(response))


def _digest_schema(max_items: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["daily_editorial_note_zh", "weekly_thread_zh", "items", "readings"],
        "properties": {
            "daily_editorial_note_zh": {"type": ["string", "null"]},
            "weekly_thread_zh": {"type": ["string", "null"]},
            "items": {
                "type": "array",
                "minItems": 0,
                "maxItems": max_items,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "title_en",
                        "source_org",
                        "published_date",
                        "core_argument_zh",
                        "why_now_zh",
                        "agenda_position_zh",
                        "tags",
                        "url",
                    ],
                    "properties": {
                        "title_en": {"type": "string"},
                        "source_org": {"type": "string"},
                        "published_date": {"type": "string"},
                        "core_argument_zh": {"type": "string"},
                        "why_now_zh": {"type": "string"},
                        "agenda_position_zh": {"type": "string"},
                        "tags": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string"}},
                        "url": {"type": "string"},
                    },
                },
            },
            "readings": {
                "type": "array",
                "minItems": 0,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "authors", "year", "journal", "doi", "today_connection_zh", "research_directions"],
                    "properties": {
                        "title": {"type": "string"},
                        "authors": {"type": "string"},
                        "year": {"type": "integer"},
                        "journal": {"type": "string"},
                        "doi": {"type": "string"},
                        "today_connection_zh": {"type": "string"},
                        "research_directions": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["question_zh", "keywords"],
                                "properties": {
                                    "question_zh": {"type": "string"},
                                    "keywords": {
                                        "type": "array",
                                        "minItems": 3,
                                        "maxItems": 5,
                                        "items": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def validate_digest_payload(
    payload: dict[str, Any],
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    run_date: date,
) -> Digest:
    candidate_urls = {candidate.url for candidate in candidates}
    candidate_sources = {candidate.source_org for candidate in candidates}
    approved_reads = {
        (reading.title, reading.authors, int(reading.year), reading.journal, reading.doi): reading
        for readings in bibliography.values()
        for reading in readings
    }

    items: list[DigestItem] = []
    for raw in payload.get("items", []):
        if raw.get("url") not in candidate_urls:
            raise ValueError(f"Digest item has unapproved URL: {raw.get('url')}")
        if raw.get("source_org") not in candidate_sources:
            raise ValueError(f"Digest item has unapproved source: {raw.get('source_org')}")

        title = str(raw["title_en"]).strip()
        tags = [str(tag).strip() for tag in raw.get("tags", []) if str(tag).strip()]
        _validate_tags(tags, title)

        core_argument_zh = str(raw.get("core_argument_zh", "")).strip()
        why_now_zh = str(raw.get("why_now_zh", "")).strip()
        agenda_position_zh = str(raw.get("agenda_position_zh", "")).strip()
        _validate_required_text(core_argument_zh, f"core_argument_zh for {title}")
        _validate_required_text(why_now_zh, f"why_now_zh for {title}")
        _validate_required_text(agenda_position_zh, f"agenda_position_zh for {title}")

        items.append(
            DigestItem(
                title_en=title,
                source_org=str(raw["source_org"]).strip(),
                published_date=str(raw["published_date"]).strip(),
                summary_zh=core_argument_zh,
                terms=[],
                tags=tags,
                url=str(raw["url"]).strip(),
                core_argument_zh=core_argument_zh,
                why_now_zh=why_now_zh,
                agenda_position_zh=agenda_position_zh,
                why_it_matters_zh=why_now_zh,
            )
        )

    readings: list[DeepRead] = []
    for raw in payload.get("readings", []):
        key = (
            raw.get("title"),
            raw.get("authors"),
            int(raw.get("year", 0)),
            raw.get("journal"),
            raw.get("doi"),
        )
        approved = approved_reads.get(key)
        if not approved:
            raise ValueError(f"Digest has unapproved reading: {key}")

        today_connection_zh = str(raw.get("today_connection_zh", "")).strip()
        _validate_required_text(today_connection_zh, f"today_connection_zh for {approved.title}")
        research_directions = [
            ResearchDirection(
                question_zh=str(direction.get("question_zh", "")).strip(),
                keywords=[str(keyword).strip() for keyword in direction.get("keywords", []) if str(keyword).strip()],
            )
            for direction in raw.get("research_directions", [])
        ]
        _validate_research_directions(research_directions, approved.title)

        readings.append(
            DeepRead(
                title=approved.title,
                authors=approved.authors,
                year=approved.year,
                url=approved.url,
                note_zh=approved.note_zh,
                note_en=approved.note_en,
                journal=approved.journal,
                doi=approved.doi,
                methodology_zh=approved.methodology_zh,
                further_reading=approved.further_reading,
                tags=approved.tags,
                kind=approved.kind,
                today_connection_zh=today_connection_zh,
                research_directions=research_directions,
            )
        )

    daily_editorial_note_zh = _optional_text(payload.get("daily_editorial_note_zh"))
    weekly_thread_zh = _optional_text(payload.get("weekly_thread_zh"))
    if len(items) < 2:
        daily_editorial_note_zh = ""
    elif not daily_editorial_note_zh:
        raise ValueError("daily_editorial_note_zh is required when at least 2 news items are selected")
    if daily_editorial_note_zh:
        if _compact_len(daily_editorial_note_zh) > 100:
            raise ValueError("daily_editorial_note_zh is longer than 100 Chinese characters")
        _validate_required_text(daily_editorial_note_zh, "daily_editorial_note_zh")
    if weekly_thread_zh:
        _validate_required_text(weekly_thread_zh, "weekly_thread_zh")

    if len(candidates) >= MIN_NEWS_ITEMS and len(items) < MIN_NEWS_ITEMS:
        raise ValueError(f"Digest selected only {len(items)} news items from {len(candidates)} candidates")

    return Digest(
        digest_date=run_date,
        subject=f"The Governance Brief - {run_date.isoformat()}",
        overview_zh=daily_editorial_note_zh,
        overview_en="",
        items=items,
        readings=readings,
        weekly_thread_zh=weekly_thread_zh,
    )


def fallback_digest(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    run_date: date,
) -> Digest:
    items: list[DigestItem] = []
    for candidate in candidates:
        tags = candidate.tags or ["#多边治理"]
        core_argument_zh = _fallback_core_argument(candidate)
        why_now_zh = "这条信息提供了一个政策议程观察点，但需要结合原文判断其回应的具体政策节点。"
        items.append(
            DigestItem(
                title_en=candidate.title,
                source_org=candidate.source_org,
                published_date=candidate.published_date,
                summary_zh=core_argument_zh,
                terms=_terms_for_tags(tags),
                tags=tags[:3],
                url=candidate.url,
                core_argument_zh=core_argument_zh,
                why_now_zh=why_now_zh,
                agenda_position_zh="议程背景不明确",
                why_it_matters_zh=why_now_zh,
            )
        )
    return Digest(
        digest_date=run_date,
        subject=f"The Governance Brief - {run_date.isoformat()}",
        overview_zh="",
        overview_en="",
        items=items,
        readings=_select_readings_for_candidates(candidates, bibliography),
        weekly_thread_zh="",
    )


def _candidate_payload(candidate: Candidate) -> dict[str, Any]:
    return {
        "title": candidate.title,
        "source_org": candidate.source_org,
        "published_date": candidate.published_date,
        "url": candidate.url,
        "feed_summary": candidate.summary_hint,
        "feed_summary_words": _word_count(candidate.summary_hint),
    }


def _reading_payload(reading: DeepRead) -> dict[str, Any]:
    return {
        "title": reading.title,
        "authors": reading.authors,
        "year": reading.year,
        "journal": reading.journal,
        "doi": reading.doi,
        "url": reading.url,
        "brief_zh": reading.note_zh,
        "methodology_zh": reading.methodology_zh,
        "tags": reading.tags,
    }


def _extract_response_text(response: dict[str, Any]) -> str:
    if response.get("output_text"):
        return response["output_text"]
    for output in response.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                return content["text"]
    raise ValueError("OpenAI response did not include output text")


def _openai_timeout_seconds() -> int:
    raw = os.getenv("OPENAI_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_OPENAI_TIMEOUT_SECONDS
    try:
        return max(60, int(raw))
    except ValueError:
        return DEFAULT_OPENAI_TIMEOUT_SECONDS


def _is_timeout_exception(exc: BaseException) -> bool:
    return "timed out" in str(exc).lower()


def _fallback_core_argument(candidate: Candidate) -> str:
    source_text = _trim_sentence(candidate.summary_hint, 120)
    if source_text:
        return f"这篇材料主张，{source_text}"
    return f"这篇材料来自 {candidate.source_org}，其政策论点需要结合原文进一步判断。"


def _trim_sentence(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _compact_len(value: str) -> int:
    return len("".join((value or "").split()))


def _word_count(value: str) -> int:
    return len([word for word in (value or "").replace("—", " ").split() if word.strip()])


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _validate_required_text(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} is empty")
    for phrase in BANNED_EMPTY_PHRASES:
        if phrase in value:
            raise ValueError(f"{field_name} contains banned empty phrase: {phrase}")


def _validate_tags(tags: list[str], title: str) -> None:
    if not tags:
        raise ValueError(f"Digest item has no tags: {title}")
    if len(tags) > 3:
        raise ValueError(f"Digest item has too many tags: {title}")
    broad = [tag for tag in tags if tag in BROAD_TAGS]
    if broad:
        raise ValueError(f"Digest item uses broad tag(s) for {title}: {', '.join(broad)}")


def _validate_research_directions(directions: list[ResearchDirection], title: str) -> None:
    if len(directions) != 2:
        raise ValueError(f"Reading must have exactly 2 research directions: {title}")
    for direction in directions:
        if not direction.question_zh:
            raise ValueError(f"Reading research direction is empty: {title}")
        if _compact_len(direction.question_zh) > 30:
            raise ValueError(f"Reading research direction is too long: {title}")
        if not (3 <= len(direction.keywords) <= 5):
            raise ValueError(f"Reading research direction keywords must contain 3-5 terms: {title}")


def _terms_for_tags(tags: list[str]) -> list[DigestTerm]:
    terms = [TERM_LIBRARY[tag] for tag in tags if tag in TERM_LIBRARY]
    if terms:
        return terms[:2]
    return [
        DigestTerm(
            "policy implication",
            "政策含义",
            "信息对政策设计、执行、融资安排或评估框架可能带来的具体影响。",
        )
    ]


def _select_readings_for_candidates(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    target_count: int = 3,
) -> list[DeepRead]:
    selected: list[DeepRead] = []
    seen: set[tuple[str, str, int, str]] = set()
    for readings in bibliography.values():
        for reading in readings:
            key = (reading.title, reading.authors, int(reading.year), reading.doi)
            if key in seen:
                continue
            seen.add(key)
            selected.append(reading)
            if len(selected) >= target_count:
                return selected
    return selected
