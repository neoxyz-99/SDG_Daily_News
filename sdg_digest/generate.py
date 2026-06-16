from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from typing import Any

from .http import post_json
from .models import Candidate, DeepRead, Digest, DigestItem, DigestTerm, NewsBrief, ResearchDirection

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.4-mini"          # news analysis + research signals generation
DEFAULT_FILTER_MODEL = "gpt-4.1-mini"  # semantic relevance filtering (stage 2)
MODEL_CONFIG = {
    "generation": ("OPENAI_MODEL", DEFAULT_MODEL),
    "filter": ("OPENAI_FILTER_MODEL", DEFAULT_FILTER_MODEL),
}
DEFAULT_OPENAI_TIMEOUT_SECONDS = 180
OPENAI_MAX_ATTEMPTS = 2
MIN_RELEVANT_RESEARCH_CANDIDATES = 5
SEMANTIC_KEEP_THRESHOLD = 2
SEMANTIC_FALLBACK_MIN_COUNT = 5
SEMANTIC_FILTER_WORKERS = 8
EVENT_LAYERS = {"event", "news"}

EXCLUDE_PATTERNS = [
    "match result",
    "league table",
    "transfer fee",
    "world cup",
    "olympic",
    "nba",
    "nfl",
    "premier league",
    "box office",
    "album release",
    "oscars",
    "grammy",
    "celebrity",
    "kardashian",
    "product launch",
    "quarterly earnings",
    "stock price",
]

DOMAIN_TAGS = {
    "A": "#国际治理与多边主义",
    "B": "#发展与不平等",
    "C": "#环境治理与气候",
    "D": "#可持续金融与ESG",
    "E": "#地缘政治与治理",
    "mixed": "#综合治理议题",
}

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
    "#水资源治理",
    "#国际治理与多边主义",
    "#发展与不平等",
    "#环境治理与气候",
    "#可持续金融与ESG",
    "#地缘政治与治理",
    "#综合治理议题",
]

BANNED_EMPTY_PHRASES = ["至关重要", "意义深远", "备受关注", "在全球化背景下"]
BROAD_TAGS = {"#气候变化", "气候变化", "#可持续发展", "可持续发展"}
GENERIC_RESEARCH_KEYWORDS = {"climate change", "governance", "sustainable development", "policy"}

NEWSLETTER_NAME = "SDG Weekly Compass"

SEMANTIC_FILTER_PROMPT = """
You are screening policy research items for SDG Weekly Compass.

Return whether this research/policy item contains a substantive argument, policy finding, or research result related to any of:
sustainable development, climate policy, development finance, global governance, green transition, inequality, or multilateral institutions.

Score:
2 = clearly substantive
1 = borderline but relevant
0 = no clear policy/research substance

Output ONLY JSON:
{{"score": X, "domain": "A/B/C/D/E/mixed", "reason": "one sentence max"}}

Domain guide:
A international governance and multilateralism
B development and inequality
C environmental governance and climate
D sustainable finance and ESG
E geopolitics with governance implications

Title: {title}
Source: {source_name}
Content: {description}
"""


def is_recent_news_candidate(candidate: Candidate) -> bool:
    return candidate.layer in EVENT_LAYERS or candidate.source_type == "news"


def filter_relevant_candidates(
    candidates: list[Candidate],
    use_openai: bool = True,
) -> list[Candidate]:
    candidates = _exclude_noise_candidates(candidates)
    recent_news, research = _split_candidates(candidates)
    if not use_openai:
        print("AI relevance check skipped")
        return recent_news + research
    if not research:
        return recent_news
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set; cannot run research relevance scoring")

    with ThreadPoolExecutor(max_workers=SEMANTIC_FILTER_WORKERS) as executor:
        scored = list(executor.map(_score_candidate_semantically, research))

    clearly_relevant = [candidate for candidate in scored if (candidate.semantic_score or 0) >= SEMANTIC_KEEP_THRESHOLD]
    if len(clearly_relevant) < SEMANTIC_FALLBACK_MIN_COUNT:
        borderline = [candidate for candidate in scored if candidate.semantic_score == 1]
        relevant_research = clearly_relevant + borderline
    else:
        relevant_research = clearly_relevant

    if len(relevant_research) < MIN_RELEVANT_RESEARCH_CANDIDATES:
        print(
            f"Warning: only {len(relevant_research)} research candidate(s) passed AI relevance scoring; "
            "continuing with available material."
        )
    return recent_news + relevant_research


def generate_digest(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    run_date: date,
    max_items: int,
    use_openai: bool = True,
    max_recent_news: int = 8,
    max_research_signals: int | None = None,
) -> Digest:
    max_research_signals = max_research_signals or max_items
    allow_fallback = os.getenv("ALLOW_OPENAI_FALLBACK", "").lower() == "true"
    if use_openai and candidates:
        if not os.getenv("OPENAI_API_KEY"):
            if allow_fallback:
                return fallback_digest(candidates, bibliography, run_date, max_recent_news, max_research_signals)
            raise RuntimeError("OPENAI_API_KEY is not set; refusing to publish fallback digest")

        feedback = ""
        last_exc: Exception | None = None
        for attempt in range(OPENAI_MAX_ATTEMPTS):
            try:
                raw = _call_openai(
                    candidates,
                    bibliography,
                    run_date,
                    max_recent_news=max_recent_news,
                    max_research_signals=max_research_signals,
                    feedback=feedback,
                )
                return validate_digest_payload(raw, candidates, bibliography, run_date)
            except ValueError as exc:
                last_exc = exc
                # Check if failure is caused by a banned phrase in a specific article field.
                # In that case, warn and retry with stricter instructions rather than crashing.
                exc_str = str(exc)
                if "contains banned empty phrase" in exc_str or "restates title" in exc_str:
                    print(f"Warning: validation issue in generated content (will retry): {exc_str}")
                feedback = (
                    f"The previous draft failed validation: {exc}. Rewrite the full JSON output. "
                    "Avoid ALL of these phrases in any field: 至关重要, 意义深远, 备受关注, 在全球化背景下. "
                    "Every core_argument_zh must name a specific actor and state a concrete argument. "
                    "Keep recent news short, keep research signals analytical, and preserve bibliography prose."
                )
                if attempt + 1 < OPENAI_MAX_ATTEMPTS:
                    print(f"OpenAI draft failed validation; retrying with stricter instructions: {exc}")
                    continue
                # All retries exhausted — fall back to deterministic digest rather than crashing.
                print(f"Warning: OpenAI generation failed after {OPENAI_MAX_ATTEMPTS} attempts: {exc}")
                print("Falling back to deterministic digest to avoid pipeline crash.")
                return fallback_digest(candidates, bibliography, run_date, max_recent_news, max_research_signals)
            except (TimeoutError, OSError) as exc:
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
            return fallback_digest(candidates, bibliography, run_date, max_recent_news, max_research_signals)
        # Only raise here for non-validation errors (network, auth, etc.)
        # Banned-phrase validation failures are handled above and never reach this line.
        raise RuntimeError(f"OpenAI generation failed; refusing to publish fallback digest: {exc}") from exc
    return fallback_digest(candidates, bibliography, run_date, max_recent_news, max_research_signals)


def _exclude_noise_candidates(candidates: list[Candidate]) -> list[Candidate]:
    kept: list[Candidate] = []
    excluded = 0
    for candidate in candidates:
        matches = _exclude_match_count(candidate.title)
        if matches >= 2:
            excluded += 1
            continue
        kept.append(candidate)
    if excluded:
        print(f"Noise exclusion removed {excluded} candidate(s)")
    return kept


def _exclude_match_count(title: str) -> int:
    title_lower = title.lower()
    return sum(1 for pattern in EXCLUDE_PATTERNS if re.search(rf"\b{re.escape(pattern)}\b", title_lower))


def _score_candidate_semantically(candidate: Candidate) -> Candidate:
    prompt = SEMANTIC_FILTER_PROMPT.format(
        title=candidate.title,
        source_name=candidate.source_org,
        description=candidate.full_text or candidate.summary_hint,
    )
    payload = {
        "model": _model_for("filter"),
        "messages": [
            {"role": "system", "content": "Return only the requested JSON object."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    response = post_json(
        OPENAI_CHAT_COMPLETIONS_URL,
        payload,
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        timeout=_openai_timeout_seconds(),
    )
    result = _parse_semantic_filter_response(response)
    domain = _normalize_domain(result.get("domain", "mixed"))
    domain_tag = DOMAIN_TAGS[domain]
    tags = list(dict.fromkeys([domain_tag, *candidate.tags]))
    return replace(
        candidate,
        semantic_score=int(result.get("score", 0)),
        semantic_domain=domain,
        semantic_reason=str(result.get("reason", "")).strip(),
        tags=tags,
    )


# WEEKLY LAYER FILTER DONE: event/news candidates bypass research semantic scoring; research candidates keep AI relevance checks.


def _call_openai(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    run_date: date,
    max_recent_news: int,
    max_research_signals: int,
    feedback: str = "",
) -> dict[str, Any]:
    recent_news, research = _split_candidates(candidates)
    prompt = {
        "run_date": run_date.isoformat(),
        "newsletter": NEWSLETTER_NAME,
        "format": "weekly",
        "reader_profile": (
            "Policy researchers and graduate students with background knowledge in global governance, "
            "climate finance, and sustainable development. They need analytical density, not basic definitions."
        ),
        "editorial_logic": [
            "The issue has three modules: 近期要闻, 研究动向, 经典研读.",
            "近期要闻 is low-density: tell the reader what happened using the title/source and one Chinese sentence; do not force topic tags into the visible copy.",
            "研究动向 is high-density: extract institutional arguments, policy timing, and agenda position.",
            "经典研读 comes only from the supplied bibliography.",
        ],
        "instructions": [
            "Return a JSON object that follows the schema.",
            "The newsletter is fully bilingual. Every Chinese analytical field must have a faithful English counterpart. English should be analytical and concise, not a word-for-word awkward translation.",
            "For recent_news and research_signals, every URL must be copied exactly from the supplied recent_news_candidates or research_candidates. Never use bibliography DOI links, paper URLs, or invented URLs as news/research item URLs.",
            "Source diversity is an editorial priority. Within recent_news and within research_signals, select from as many different source_org values as possible. If alternatives exist, do not select more than 2 items from the same source_org in the same module.",
            "weekly_editorial_note_zh: under 100 Chinese characters, only if at least 2 total news/research items are selected. It should raise a tension or open question across actor logics, not summarize. weekly_editorial_note_en should carry the same meaning in one concise English sentence.",
            "recent_news: select up to the requested maximum from recent_news_candidates using exclusion-only editorial judgment. Do not apply research relevance, domain relevance, or topic keyword gates. Write one_sentence_zh and one_sentence_en for each item; keep tags empty unless the source text gives a very specific archive label.",
            "research_signals: select up to the requested maximum from research_candidates. These require core_argument_zh/core_argument_en, why_now_zh/why_now_en, agenda_position_zh/agenda_position_en, and tags.",
            "Core Argument: write 1 dense Chinese sentence, 70-120 Chinese characters. It must name a specific actor, institution, policy instrument, or negotiating party; state the concrete problem or mechanism identified by the article; explain why that mechanism matters; and indicate what policy, financing, governance, or institutional change the article argues for or implies. Do not write vague sentences such as 'X is important' or 'cannot be ignored'. Do not restate the title or use statistics as the core of the argument.",
            "Why Now: 1-2 Chinese sentences with a temporal anchor: what this responds to, advances, or challenges. If timing is unclear, say so plainly.",
            "Agenda Position: one Chinese sentence explaining the item's place in a larger policy process, such as a negotiation, summit, institutional work program, actor timing, or challenge to a policy framework. If the source text does not support a specific agenda anchor, output exactly: 议程背景不明确. Do not use generic phrases such as 这是政策讨论的重要参考.",
            "Tags are post-selection labels only. Use 1-3 specific Chinese tags from the tag registry when possible, and avoid broad tags like 气候变化 or 可持续发展.",
            "weekly_thread_zh: only if at least 2 selected items share an issue line; 1-2 Chinese sentences explaining the shared agenda question or disagreement.",
            "Select up to 3 classic readings from bibliography. Preserve note_zh, note_en, methodology_zh, method_en, authors, year, journal, DOI, and URL exactly. The selected readings should be the ones whose preserved prose gives the most concrete analytical leverage for this issue.",
            "For each reading, generate today_connection_zh and today_connection_en as one sentence each that references a specific selected news/research title or source. If there is no genuine connection, output exactly in Chinese: 本期暂无直接关联，建议结合[填入议题方向，如气候融资谈判]阅读 and the equivalent English: No direct connection in this issue; read alongside [topic direction].",
            "For each reading, generate exactly 2 research_directions. Each direction has question_zh under 30 Chinese characters, question_en as a concise English research question, and 3-5 English search keywords. Do not cite literature, authors, or book titles.",
            "In reading generated fields, annotate key theoretical concepts on first mention with English in parentheses, such as 嵌入式自由主义（embedded liberalism） or 混合融资（blended finance）. Do not annotate common names such as 世界银行 or 联合国.",
            "Do not invent URLs, sources, readings, dates, authors, journals, DOIs, data, or literature.",
            "Avoid empty rhetoric including 至关重要, 意义深远, 备受关注, 在全球化背景下.",
        ],
        "tag_registry": TAG_REGISTRY,
        "max_recent_news": max_recent_news,
        "max_research_signals": max_research_signals,
        "recent_news_candidates": [_candidate_payload(candidate) for candidate in recent_news[:40]],
        "research_candidates": [_candidate_payload(candidate) for candidate in research[:40]],
        "selected_news_context": [
            {"title": candidate.title, "source": candidate.source_org, "layer": candidate.layer}
            for candidate in candidates[:60]
        ],
        "bibliography": [
            _reading_payload(reading)
            for readings in bibliography.values()
            for reading in readings
        ],
    }
    if feedback:
        prompt["validation_feedback"] = feedback
    payload = {
        "model": _model_for("generation"),
        "input": [
            {
                "role": "system",
                "content": (
                    "You are the editorial AI for SDG Weekly Compass. You separate low-density event awareness "
                    "from high-density policy/research analysis and preserve curated bibliography prose."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "governance_brief_weekly",
                "strict": True,
                "schema": _digest_schema(max_recent_news, max_research_signals),
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


# WEEKLY PROMPT DONE: generation prompt now produces recent news, research signals, and classic readings separately.


def _digest_schema(max_recent_news: int, max_research_signals: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "weekly_editorial_note_zh",
            "weekly_editorial_note_en",
            "weekly_thread_zh",
            "weekly_thread_en",
            "recent_news",
            "research_signals",
            "readings",
        ],
        "properties": {
            "weekly_editorial_note_zh": {"type": ["string", "null"]},
            "weekly_editorial_note_en": {"type": ["string", "null"]},
            "weekly_thread_zh": {"type": ["string", "null"]},
            "weekly_thread_en": {"type": ["string", "null"]},
            "recent_news": {
                "type": "array",
                "minItems": 0,
                "maxItems": max_recent_news,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title_en", "source_org", "published_date", "one_sentence_zh", "one_sentence_en", "tags", "url"],
                    "properties": {
                        "title_en": {"type": "string"},
                        "source_org": {"type": "string"},
                        "published_date": {"type": "string"},
                        "one_sentence_zh": {"type": "string"},
                        "one_sentence_en": {"type": "string"},
                        "tags": {"type": "array", "minItems": 0, "maxItems": 3, "items": {"type": "string"}},
                        "url": {"type": "string"},
                    },
                },
            },
            "research_signals": {
                "type": "array",
                "minItems": 0,
                "maxItems": max_research_signals,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "title_en",
                        "source_org",
                        "published_date",
                        "core_argument_zh",
                        "core_argument_en",
                        "why_now_zh",
                        "why_now_en",
                        "agenda_position_zh",
                        "agenda_position_en",
                        "tags",
                        "url",
                    ],
                    "properties": {
                        "title_en": {"type": "string"},
                        "source_org": {"type": "string"},
                        "published_date": {"type": "string"},
                        "core_argument_zh": {"type": "string"},
                        "core_argument_en": {"type": "string"},
                        "why_now_zh": {"type": "string"},
                        "why_now_en": {"type": "string"},
                        "agenda_position_zh": {"type": "string"},
                        "agenda_position_en": {"type": "string"},
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
                    "required": ["title", "authors", "year", "journal", "doi", "today_connection_zh", "today_connection_en", "research_directions"],
                    "properties": {
                        "title": {"type": "string"},
                        "authors": {"type": "string"},
                        "year": {"type": "integer"},
                        "journal": {"type": "string"},
                        "doi": {"type": "string"},
                        "today_connection_zh": {"type": "string"},
                        "today_connection_en": {"type": "string"},
                        "research_directions": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["question_zh", "question_en", "keywords"],
                                "properties": {
                                    "question_zh": {"type": "string"},
                                    "question_en": {"type": "string"},
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
    candidate_by_url = {candidate.url: candidate for candidate in candidates}
    approved_reads = {
        (reading.title, reading.authors, int(reading.year), reading.journal, reading.doi): reading
        for readings in bibliography.values()
        for reading in readings
    }

    recent_news: list[NewsBrief] = []
    for raw in payload.get("recent_news", []):
        url = str(raw.get("url", "")).strip()
        title = str(raw.get("title_en", "")).strip()
        source_org = str(raw.get("source_org", "")).strip()
        if not _is_approved_candidate_reference(url, source_org, candidate_urls, candidate_sources):
            print(f"Warning: skipped recent-news item with unapproved candidate reference: {title or url}")
            continue
        one_sentence_zh = str(raw.get("one_sentence_zh", "")).strip()
        _validate_required_text(one_sentence_zh, f"one_sentence_zh for {title}")
        recent_news.append(
            NewsBrief(
                title_en=title,
                source_org=source_org,
                published_date=str(raw["published_date"]).strip(),
                url=url,
                one_sentence_zh=one_sentence_zh,
                one_sentence_en=str(raw.get("one_sentence_en", "")).strip(),
                tags=_clean_tags(raw.get("tags", []), candidate_by_url[url].tags),
            )
        )

    research_signals: list[DigestItem] = []
    raw_research_signals = payload.get("research_signals", payload.get("items", []))
    for raw in raw_research_signals:
        url = str(raw.get("url", "")).strip()
        title = str(raw.get("title_en", "")).strip()
        source_org = str(raw.get("source_org", "")).strip()
        if not _is_approved_candidate_reference(url, source_org, candidate_urls, candidate_sources):
            print(f"Warning: skipped research signal with unapproved candidate reference: {title or url}")
            continue
        source_candidate = candidate_by_url[url]
        tags = _clean_tags(raw.get("tags", []), source_candidate.tags)
        if not tags:
            tags = ["#综合治理议题"]
        core_argument_zh = str(raw.get("core_argument_zh", "")).strip()
        core_argument_en = str(raw.get("core_argument_en", "")).strip()
        why_now_zh = str(raw.get("why_now_zh", "")).strip()
        why_now_en = str(raw.get("why_now_en", "")).strip()
        agenda_position_zh = str(raw.get("agenda_position_zh", "")).strip()
        agenda_position_en = str(raw.get("agenda_position_en", "")).strip()
        _validate_core_argument(core_argument_zh, title)
        _validate_required_text(core_argument_en, f"core_argument_en for {title}")
        _validate_required_text(why_now_zh, f"why_now_zh for {title}")
        _validate_required_text(why_now_en, f"why_now_en for {title}")
        _validate_required_text(agenda_position_zh, f"agenda_position_zh for {title}")
        _validate_required_text(agenda_position_en, f"agenda_position_en for {title}")
        research_signals.append(
            DigestItem(
                title_en=title,
                source_org=source_org,
                published_date=str(raw["published_date"]).strip(),
                summary_zh=core_argument_zh,
                terms=_terms_for_tags(tags),
                tags=tags,
                url=url,
                core_argument_zh=core_argument_zh,
                core_argument_en=core_argument_en,
                why_now_zh=why_now_zh,
                why_now_en=why_now_en,
                agenda_position_zh=agenda_position_zh,
                agenda_position_en=agenda_position_en,
                why_it_matters_zh=why_now_zh,
                why_it_matters_en=why_now_en,
            )
        )

    readings = _validate_readings(payload, approved_reads)
    editorial_note = _optional_text(payload.get("weekly_editorial_note_zh", payload.get("daily_editorial_note_zh")))
    editorial_note_en = _optional_text(payload.get("weekly_editorial_note_en"))
    weekly_thread_zh = _optional_text(payload.get("weekly_thread_zh"))
    weekly_thread_en = _optional_text(payload.get("weekly_thread_en"))
    selected_total = len(recent_news) + len(research_signals)
    if selected_total < 2:
        editorial_note = ""
        editorial_note_en = ""
    elif editorial_note:
        if _compact_len(editorial_note) > 100:
            raise ValueError("weekly_editorial_note_zh is longer than 100 Chinese characters")
        _validate_required_text(editorial_note, "weekly_editorial_note_zh")
        _validate_required_text(editorial_note_en, "weekly_editorial_note_en")
    if weekly_thread_zh:
        _validate_required_text(weekly_thread_zh, "weekly_thread_zh")
        _validate_required_text(weekly_thread_en, "weekly_thread_en")

    return Digest(
        digest_date=run_date,
        subject=f"{NEWSLETTER_NAME} - Week of {run_date.isoformat()}",
        overview_zh=editorial_note,
        overview_en=editorial_note_en,
        items=research_signals,
        readings=readings,
        weekly_thread_zh=weekly_thread_zh,
        weekly_thread_en=weekly_thread_en,
        recent_news=recent_news,
        research_signals=research_signals,
        classic_readings=readings,
    )


def fallback_digest(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    run_date: date,
    max_recent_news: int = 8,
    max_research_signals: int = 5,
) -> Digest:
    recent_candidates, research_candidates = _split_candidates(candidates)
    recent_news = [
        NewsBrief(
            title_en=candidate.title,
            source_org=candidate.source_org,
            published_date=candidate.published_date,
            url=candidate.url,
            one_sentence_zh=_fallback_news_sentence(candidate),
            one_sentence_en=_fallback_news_sentence_en(candidate),
            tags=_clean_tags(candidate.tags, ["#综合治理议题"]),
        )
        for candidate in recent_candidates[:max_recent_news]
    ]
    research_signals = [
        DigestItem(
            title_en=candidate.title,
            source_org=candidate.source_org,
            published_date=candidate.published_date,
            summary_zh=_fallback_core_argument(candidate),
            summary_en=_fallback_core_argument_en(candidate),
            terms=_terms_for_tags(candidate.tags),
            tags=_clean_tags(candidate.tags, ["#综合治理议题"]) or ["#综合治理议题"],
            url=candidate.url,
            core_argument_zh=_fallback_core_argument(candidate),
            core_argument_en=_fallback_core_argument_en(candidate),
            why_now_zh="这条材料提供了一个政策议程观察点，但发布时机需要结合原文和当周政策节点进一步判断。",
            why_now_en="This item offers a policy agenda signal, but its timing should be interpreted alongside the original text and the week's policy calendar.",
            agenda_position_zh="议程背景不明确",
            agenda_position_en="The agenda background is unclear.",
            why_it_matters_zh="这条材料提供了一个政策议程观察点，但发布时机需要结合原文和当周政策节点进一步判断。",
            why_it_matters_en="This item offers a policy agenda signal, but its timing should be interpreted alongside the original text and the week's policy calendar.",
        )
        for candidate in research_candidates[:max_research_signals]
    ]
    readings = _fallback_readings(candidates, bibliography)
    return Digest(
        digest_date=run_date,
        subject=f"{NEWSLETTER_NAME} - Week of {run_date.isoformat()}",
        overview_zh="",
        overview_en="",
        items=research_signals,
        readings=readings,
        weekly_thread_zh="",
        weekly_thread_en="",
        recent_news=recent_news,
        research_signals=research_signals,
        classic_readings=readings,
    )


def _split_candidates(candidates: list[Candidate]) -> tuple[list[Candidate], list[Candidate]]:
    recent_news = [candidate for candidate in candidates if is_recent_news_candidate(candidate)]
    research = [candidate for candidate in candidates if not is_recent_news_candidate(candidate)]
    return recent_news, research


def _candidate_payload(candidate: Candidate) -> dict[str, Any]:
    return {
        "title": candidate.title,
        "source_org": candidate.source_org,
        "source_type": candidate.source_type,
        "layer": candidate.layer,
        "published_date": candidate.published_date,
        "url": candidate.url,
        "rss_summary": candidate.summary_hint,
        "full_text": candidate.full_text,
        "article_content": candidate.full_text or candidate.summary_hint or candidate.title,
        "text_source": candidate.text_source,
        "semantic_score": candidate.semantic_score,
        "semantic_domain": candidate.semantic_domain,
        "semantic_reason": candidate.semantic_reason,
        "semantic_domain_tag": candidate.tags[0] if candidate.tags else "",
        "feed_summary_words": _word_count(candidate.summary_hint),
        "full_text_words": _word_count(candidate.full_text),
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
        "brief_en": reading.note_en,
        "methodology_zh": reading.methodology_zh,
        "methodology_en": reading.method_en,
        "tags": reading.tags,
    }


def _validate_candidate_reference(
    url: str,
    source_org: str,
    candidate_urls: set[str],
    candidate_sources: set[str],
) -> None:
    if not _is_approved_candidate_reference(url, source_org, candidate_urls, candidate_sources):
        if url not in candidate_urls:
            raise ValueError(f"Digest item has unapproved URL: {url}")
        raise ValueError(f"Digest item has unapproved source: {source_org}")


def _is_approved_candidate_reference(
    url: str,
    source_org: str,
    candidate_urls: set[str],
    candidate_sources: set[str],
) -> bool:
    return url in candidate_urls and source_org in candidate_sources


def _validate_readings(
    payload: dict[str, Any],
    approved_reads: dict[tuple[str, str, int, str, str], DeepRead],
) -> list[DeepRead]:
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
        today_connection_en = str(raw.get("today_connection_en", "")).strip()
        _validate_required_text(today_connection_zh, f"today_connection_zh for {approved.title}")
        _validate_required_text(today_connection_en, f"today_connection_en for {approved.title}")
        research_directions = [
            ResearchDirection(
                question_zh=str(direction.get("question_zh", "")).strip(),
                keywords=[str(keyword).strip() for keyword in direction.get("keywords", []) if str(keyword).strip()],
                question_en=str(direction.get("question_en", "")).strip(),
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
                today_connection_en=today_connection_en,
                research_directions=research_directions,
            )
        )
    return readings


def _extract_response_text(response: dict[str, Any]) -> str:
    if response.get("output_text"):
        return response["output_text"]
    for output in response.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                return content["text"]
    raise ValueError("OpenAI response did not include output text")


def _extract_chat_content(response: dict[str, Any]) -> str:
    choices = response.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        if content:
            return content
    raise ValueError("OpenAI chat response did not include message content")


def _parse_semantic_filter_response(response: dict[str, Any]) -> dict[str, Any]:
    raw = _extract_chat_content(response).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            raise ValueError(f"Research relevance scorer returned non-JSON content: {raw}")
        parsed = json.loads(match.group(0))
    score = int(parsed.get("score", 0))
    if score not in {0, 1, 2}:
        score = 0
    return {
        "score": score,
        "domain": _normalize_domain(parsed.get("domain", "mixed")),
        "reason": str(parsed.get("reason", "")).strip(),
    }


def _normalize_domain(value: Any) -> str:
    domain = str(value or "mixed").strip().upper()
    if domain in {"A", "B", "C", "D", "E"}:
        return domain
    return "mixed"


def _openai_timeout_seconds() -> int:
    raw = os.getenv("OPENAI_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_OPENAI_TIMEOUT_SECONDS
    try:
        return max(60, int(raw))
    except ValueError:
        return DEFAULT_OPENAI_TIMEOUT_SECONDS


def _model_for(task: str) -> str:
    env_name, fallback = MODEL_CONFIG[task]
    return os.getenv(env_name, fallback)


# MODEL CONFIG DONE: OpenAI model names are centralized and overridable by environment variables.


def _is_timeout_exception(exc: BaseException) -> bool:
    return "timed out" in str(exc).lower()


def _fallback_news_sentence(candidate: Candidate) -> str:
    source_text = _trim_sentence(candidate.summary_hint, 80)
    if source_text:
        return f"{candidate.source_org}发布或转发的这条要闻显示：{source_text}"
    return f"{candidate.source_org}发布了与全球治理、发展或气候议程相关的新动态。"


def _fallback_news_sentence_en(candidate: Candidate) -> str:
    source_text = _trim_sentence(candidate.summary_hint, 100)
    if source_text:
        return f"{candidate.source_org} reports a relevant development: {source_text}"
    return f"{candidate.source_org} published a new item related to global governance, development, or climate agendas."


def _fallback_core_argument(candidate: Candidate) -> str:
    source_text = _trim_sentence(candidate.full_text or candidate.summary_hint, 120)
    if source_text:
        return f"{candidate.source_org}这篇材料主张，{source_text}"
    return f"{candidate.source_org}这篇材料提出的政策论点需要结合原文进一步判断。"


def _fallback_core_argument_en(candidate: Candidate) -> str:
    source_text = _trim_sentence(candidate.full_text or candidate.summary_hint, 140)
    if source_text:
        return f"{candidate.source_org} argues that {source_text}"
    return f"The policy argument in this item from {candidate.source_org} should be assessed against the original text."


def _trim_sentence(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _compact_len(value: str) -> int:
    return len("".join((value or "").split()))


def _word_count(value: str) -> int:
    return len([word for word in (value or "").replace("…", " ").split() if word.strip()])


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


def _validate_core_argument(value: str, title: str) -> None:
    _validate_required_text(value, f"core_argument_zh for {title}")
    if _compact_len(value) < 45:
        print(f"Warning: core_argument_zh is short for {title}: {_compact_len(value)} chars")
    if _normalize_for_compare(value) == _normalize_for_compare(title):
        raise ValueError(f"core_argument_zh restates title for {title}")


def _clean_tags(raw_tags: list[str], fallback_tags: list[str] | None = None) -> list[str]:
    fallback_tags = fallback_tags or []
    tags = [
        str(tag).strip()
        for tag in [*fallback_tags, *raw_tags]
        if str(tag).strip() and str(tag).strip() not in BROAD_TAGS
    ]
    return list(dict.fromkeys(tags))[:3]


def _normalize_for_compare(value: str) -> str:
    return re.sub(r"\W+", "", value.lower())


def _validate_research_directions(directions: list[ResearchDirection], title: str) -> None:
    if len(directions) != 2:
        raise ValueError(f"Reading must have exactly 2 research directions: {title}")
    for direction in directions:
        if not direction.question_zh:
            raise ValueError(f"Reading research direction is empty: {title}")
        if not direction.question_en:
            raise ValueError(f"Reading research direction English question is empty: {title}")
        if _compact_len(direction.question_zh) > 30:
            raise ValueError(f"Reading research direction is too long: {title}")
        if not (3 <= len(direction.keywords) <= 5):
            raise ValueError(f"Reading research direction keywords must contain 3-5 terms: {title}")
        generic = [keyword for keyword in direction.keywords if keyword.lower() in GENERIC_RESEARCH_KEYWORDS]
        if generic:
            print(f"Warning: reading research direction has generic keyword(s) for {title}: {', '.join(generic)}")


def _terms_for_tags(tags: list[str]) -> list[DigestTerm]:
    library = {
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
        "#多边治理": DigestTerm(
            "multilateral governance",
            "多边治理",
            "国家、国际组织和非国家行为体围绕共同问题形成规则、协调行动和分配责任的机制。",
        ),
        "#Global South": DigestTerm(
            "Global South",
            "全球南方",
            "通常指在全球经济与气候治理中面临发展约束、融资缺口和规则不平等的国家和地区。",
        ),
    }
    terms = [library[tag] for tag in tags if tag in library]
    return terms[:2]


def _select_readings_for_candidates(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    target_count: int = 3,
) -> list[DeepRead]:
    selected: list[DeepRead] = []
    seen: set[tuple[str, str, int, str]] = set()
    candidate_tags = {tag for candidate in candidates for tag in candidate.tags}
    ordered_keys = [tag for tag in bibliography if tag in candidate_tags] + [tag for tag in bibliography if tag not in candidate_tags]
    for tag in ordered_keys:
        for reading in bibliography[tag]:
            key = (reading.title, reading.authors, int(reading.year), reading.doi)
            if key in seen:
                continue
            seen.add(key)
            selected.append(reading)
            if len(selected) >= target_count:
                return selected
    return selected


def _fallback_readings(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
) -> list[DeepRead]:
    if not candidates:
        return []
    readings: list[DeepRead] = []
    for reading in _select_readings_for_candidates(candidates, bibliography):
        readings.append(
            DeepRead(
                title=reading.title,
                authors=reading.authors,
                year=reading.year,
                url=reading.url,
                note_zh=reading.note_zh,
                note_en=reading.note_en,
                journal=reading.journal,
                doi=reading.doi,
                methodology_zh=reading.methodology_zh,
                further_reading=reading.further_reading,
                tags=reading.tags,
                kind=reading.kind,
                today_connection_zh="本期暂无直接关联，建议结合气候融资谈判阅读",
                today_connection_en="No direct connection in this issue; read alongside climate finance negotiations.",
                research_directions=[
                    ResearchDirection(
                        question_zh="制度设计如何影响融资",
                        keywords=["institutional design", "climate finance", "development banks"],
                        question_en="How does institutional design shape finance?",
                    ),
                    ResearchDirection(
                        question_zh="政策承诺如何转化",
                        keywords=["policy implementation", "pledge delivery", "public finance"],
                        question_en="How are policy pledges converted into delivery?",
                    ),
                ],
            )
        )
    return readings
