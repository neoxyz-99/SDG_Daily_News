from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from .http import post_json
from .models import Candidate, DeepRead, Digest, DigestItem, DigestTerm

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 180
OPENAI_MAX_ATTEMPTS = 2
MIN_NEWS_ITEMS = 3
MIN_SUMMARY_ZH_CHARS = 100
MIN_SUMMARY_EN_WORDS = 45
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
    "#碳市场": DigestTerm(
        "carbon markets",
        "碳市场",
        "通过碳信用、排放配额或交易机制为减排行动定价和配置资源的政策工具。",
    ),
    "#能源转型": DigestTerm(
        "energy transition",
        "能源转型",
        "能源系统从高碳化石燃料向可再生、低碳和高效率结构转变的过程。",
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
                    "Use only the provided feed summaries as source material, keep tags to 1-3 per item, "
                    "and do not rewrite bibliography prose briefs."
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
        "editorial_scope": [
            "Climate policy, sustainable development, development finance, global governance, green transition, inequality, and multilateral institutions.",
            "The candidates already passed source whitelist and AI relevance checks.",
            "Use the feed_summary/source_excerpt field as the source text. Do not assume you have read the linked webpage.",
        ],
        "tag_registry": TAG_REGISTRY,
        "instructions": [
            "Return a JSON object that follows the schema.",
            "Select the strongest 3-5 news items. Prefer 4-5 when enough candidates exist.",
            "Write overview_zh as one Chinese sentence of at most 40 Chinese characters describing the connective thread across today's selected items. If there are no items, return an empty string.",
            "overview_en may be an empty string; it will not be displayed.",
            "For each selected item, write a substantive Chinese summary of 100-160 Chinese characters and an English brief of 50-90 words.",
            "Assign 1-3 tags per item from tag_registry after selection. Tags are archive labels and must not affect selection.",
            "If no existing tag fits, you may create one new tag beginning with #.",
            "Explain 1-2 professional terms per item.",
            "Select 2-3 deep reads from bibliography. Use only bibliography entries.",
            "For each selected deep read, output only its identity fields and one short English today_relevance_en sentence.",
            "Do not rewrite bibliography prose briefs, authors, years, journals, DOIs, or links.",
            "Do not invent URLs, sources, readings, dates, authors, journals, or DOIs.",
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
                    "You are a bilingual policy research editor. You summarize only provided feed text, "
                    "classify archive tags after selection, and preserve approved bibliography prose."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sdg_digest",
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
        "required": ["overview_zh", "overview_en", "items", "readings"],
        "properties": {
            "overview_zh": {"type": "string"},
            "overview_en": {"type": "string"},
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
                        "summary_zh",
                        "summary_en",
                        "why_it_matters_zh",
                        "why_it_matters_en",
                        "terms",
                        "tags",
                        "sdg_links",
                        "url",
                    ],
                    "properties": {
                        "title_en": {"type": "string"},
                        "source_org": {"type": "string"},
                        "published_date": {"type": "string"},
                        "summary_zh": {"type": "string"},
                        "summary_en": {"type": "string"},
                        "why_it_matters_zh": {"type": "string"},
                        "why_it_matters_en": {"type": "string"},
                        "terms": {
                            "type": "array",
                            "maxItems": 2,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["term_en", "term_zh", "explanation_zh"],
                                "properties": {
                                    "term_en": {"type": "string"},
                                    "term_zh": {"type": "string"},
                                    "explanation_zh": {"type": "string"},
                                },
                            },
                        },
                        "tags": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string"}},
                        "sdg_links": {"type": "array", "items": {"type": "string"}},
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
                    "required": ["title", "authors", "year", "journal", "doi", "today_relevance_en"],
                    "properties": {
                        "title": {"type": "string"},
                        "authors": {"type": "string"},
                        "year": {"type": "integer"},
                        "journal": {"type": "string"},
                        "doi": {"type": "string"},
                        "today_relevance_en": {"type": "string"},
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
        tags = [str(tag).strip() for tag in raw.get("tags", []) if str(tag).strip()]
        if not tags:
            raise ValueError(f"Digest item has no tags: {raw.get('title_en')}")
        if len(tags) > 3:
            raise ValueError(f"Digest item has too many tags: {raw.get('title_en')}")
        terms = [
            DigestTerm(
                term_en=str(term.get("term_en", "")).strip(),
                term_zh=str(term.get("term_zh", "")).strip(),
                explanation_zh=str(term.get("explanation_zh", "")).strip(),
            )
            for term in raw.get("terms", [])
        ]
        item = DigestItem(
            title_en=str(raw["title_en"]).strip(),
            source_org=str(raw["source_org"]).strip(),
            published_date=str(raw["published_date"]).strip(),
            summary_zh=str(raw["summary_zh"]).strip(),
            summary_en=str(raw.get("summary_en", "")).strip(),
            why_it_matters_zh=str(raw.get("why_it_matters_zh", "")).strip(),
            why_it_matters_en=str(raw.get("why_it_matters_en", "")).strip(),
            terms=terms,
            tags=tags,
            sdg_links=list(raw.get("sdg_links", [])),
            url=str(raw["url"]).strip(),
        )
        if _compact_len(item.summary_zh) < MIN_SUMMARY_ZH_CHARS:
            raise ValueError(
                f"Digest item summary_zh is too short for {item.title_en}: "
                f"{_compact_len(item.summary_zh)} chars"
            )
        if _word_count(item.summary_en) < MIN_SUMMARY_EN_WORDS:
            raise ValueError(
                f"Digest item summary_en is too short for {item.title_en}: "
                f"{_word_count(item.summary_en)} words"
            )
        items.append(item)

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
                today_relevance_en=str(raw.get("today_relevance_en", "")).strip(),
            )
        )

    if items and _compact_len(str(payload.get("overview_zh", ""))) > 40:
        raise ValueError("overview_zh theme sentence is longer than 40 Chinese characters")

    if len(candidates) >= MIN_NEWS_ITEMS and len(items) < MIN_NEWS_ITEMS:
        raise ValueError(f"Digest selected only {len(items)} news items from {len(candidates)} candidates")

    return Digest(
        digest_date=run_date,
        subject=f"The Governance Brief - {run_date.isoformat()}",
        overview_zh=str(payload.get("overview_zh", "")).strip() if items else "",
        overview_en=str(payload.get("overview_en", "")).strip(),
        items=items,
        readings=readings,
    )


def fallback_digest(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    run_date: date,
) -> Digest:
    items: list[DigestItem] = []
    for candidate in candidates:
        tags = candidate.tags or ["#多边治理"]
        items.append(
            DigestItem(
                title_en=candidate.title,
                source_org=candidate.source_org,
                published_date=candidate.published_date,
                summary_zh=_fallback_summary_zh(candidate),
                summary_en=_fallback_summary_en(candidate),
                why_it_matters_zh="这条信息可作为观察政策执行、资金安排或多边治理变化的线索。",
                why_it_matters_en="It can be read as a signal for policy implementation, finance arrangements, or multilateral governance.",
                terms=_terms_for_tags(tags),
                tags=tags[:3],
                sdg_links=_sdg_links(tags),
                url=candidate.url,
            )
        )
    readings = _select_readings_for_candidates(candidates, bibliography)
    return Digest(
        digest_date=run_date,
        subject=f"The Governance Brief - {run_date.isoformat()}",
        overview_zh="气候、融资与治理议程交织推进。" if items else "",
        overview_en="",
        items=items,
        readings=readings,
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


def _fallback_summary_zh(candidate: Candidate) -> str:
    return _trim_sentence(candidate.summary_hint, 180) or f"{candidate.title} 来自 {candidate.source_org}。"


def _fallback_summary_en(candidate: Candidate) -> str:
    return _trim_sentence(candidate.summary_hint, 420) or f"This item comes from {candidate.source_org}."


def _trim_sentence(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _compact_len(value: str) -> int:
    return len("".join((value or "").split()))


def _word_count(value: str) -> int:
    return len([word for word in (value or "").replace("—", " ").split() if word.strip()])


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


def _sdg_links(tags: list[str]) -> list[str]:
    links: list[str] = []
    if any(tag in tags for tag in ("#气候金融", "#NDC", "#绿色转型", "#碳市场", "#能源转型")):
        links.extend(["SDG 13 Climate Action", "SDG 17 Partnerships"])
    if any(tag in tags for tag in ("#SDG进展", "#发展不平等", "#粮食与土地")):
        links.extend(["SDG implementation", "SDG 10 Reduced Inequalities"])
    if any(tag in tags for tag in ("#债务可持续性", "#主权债务", "#Global South")):
        links.extend(["SDG 8 Decent Work and Growth", "SDG 10 Reduced Inequalities"])
    return list(dict.fromkeys(links))[:3]


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
