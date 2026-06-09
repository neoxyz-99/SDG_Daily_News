from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from .http import post_json
from .models import Candidate, DeepRead, Digest, DigestItem, DigestTerm

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-4o-mini"
MIN_NEWS_ITEMS = 3
MIN_SUMMARY_ZH_CHARS = 100
MIN_SUMMARY_EN_WORDS = 50
MIN_READING_ITEMS = 3
MIN_READING_NOTE_ZH_CHARS = 120
OPENAI_MAX_ATTEMPTS = 3
DEFAULT_OPENAI_TIMEOUT_SECONDS = 180

TERM_LIBRARY = {
    "#NDC": DigestTerm(
        "NDC",
        "国家自主贡献",
        "各国在《巴黎协定》下提交的减排、适应和支持目标，是观察气候治理雄心的重要入口。",
    ),
    "#气候金融": DigestTerm(
        "climate finance",
        "气候金融",
        "用于减缓、适应、损失与损害等气候行动的公共或私人资金安排。",
    ),
    "#SDG进展": DigestTerm(
        "SDG implementation",
        "可持续发展目标落实",
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
        "通常指在全球经济与气候治理中面临发展约束、融资缺口和不平等规则的国家和地区。",
    ),
}


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
                    "If a selected item has too little source detail to support a substantive brief, replace it with "
                    "a richer candidate from the list instead of padding generic text. Make every summary_zh at least "
                    "120 Chinese characters, every summary_en at least 60 words, select at least 3 news items when "
                    "3 credible candidates exist, and select 3 readings."
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
            "Climate-related policy, finance, transition, disaster risk, development finance, and SDG consequences.",
            "Include non-positive SDG-relevant events when they materially affect resilience, poverty, infrastructure, food, health, or climate adaptation.",
            "Avoid treating SDG only as success stories; analyze tradeoffs, risks, implementation gaps, and financing implications.",
        ],
        "instructions": [
            "Return a JSON object that follows the schema.",
            "Select the strongest 3-5 news items. Prefer 4-5 when enough credible candidates exist.",
            "Prioritize candidates with richer source detail and longer summary_hint fields. Avoid thin landing-page items when richer candidates are available.",
            "Write overview_zh and overview_en as reader-facing editorial summaries. Do not mention model, automation, fallback, or whitelist.",
            "For each item, write summary_zh as a substantive Chinese brief of 120-180 Chinese characters. It must explain what happened, who is involved, the mechanism or policy issue, and the concrete climate/SDG/finance implication. Do not use generic advice.",
            "For each item, write summary_en as a substantive English brief of 60-100 words. It must summarize the item itself, not tell readers to check the original.",
            "For each item, write why_it_matters_zh and why_it_matters_en explaining specific SDG, climate, finance, or resilience implications.",
            "Explain 1-2 professional terms per item.",
            "Select 3 readings from the bibliography when possible, using different tags or viewpoints when the candidate themes allow it.",
            "For each reading, write note_zh as a 160-240 Chinese character abstract-style brief and note_en as a 90-130 word brief.",
            "For each reading, summarize argument, method, evidence, and relevance in both Chinese and English with concrete article-level detail.",
            "Use only candidate URLs for item URLs.",
            "Use readings only from the provided bibliography entries.",
            "Do not invent authors, years, links, organizations, or dates.",
        ],
        "candidates": [_candidate_payload(candidate) for candidate in candidates[:30]],
        "bibliography": {
            tag: [reading.__dict__ for reading in readings]
            for tag, readings in bibliography.items()
        },
    }
    if feedback:
        prompt["validation_feedback"] = feedback
    payload = {
        "model": os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        "input": [
            {
                "role": "system",
                "content": (
                    "You are a bilingual policy research editor writing for readers who track "
                    "climate policy, SDG risk, sustainable finance, and Global South development."
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
    text = _extract_response_text(response)
    return json.loads(text)


def _candidate_payload(candidate: Candidate) -> dict[str, Any]:
    payload = candidate.__dict__.copy()
    payload["summary_hint_chars"] = _compact_len(candidate.summary_hint)
    payload["has_rich_source_detail"] = _compact_len(candidate.summary_hint) >= 160
    return payload


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


def _extract_response_text(response: dict[str, Any]) -> str:
    if response.get("output_text"):
        return response["output_text"]
    for output in response.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                return content["text"]
    raise ValueError("OpenAI response did not include output text")


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
                        "tags": {"type": "array", "items": {"type": "string"}},
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
                    "required": [
                        "title",
                        "authors",
                        "year",
                        "url",
                        "note_zh",
                        "note_en",
                        "argument_zh",
                        "argument_en",
                        "method_zh",
                        "method_en",
                        "evidence_zh",
                        "evidence_en",
                        "relevance_zh",
                        "relevance_en",
                        "tags",
                        "kind",
                    ],
                    "properties": {
                        "title": {"type": "string"},
                        "authors": {"type": "string"},
                        "year": {"type": "integer"},
                        "url": {"type": "string"},
                        "note_zh": {"type": "string"},
                        "note_en": {"type": "string"},
                        "argument_zh": {"type": "string"},
                        "argument_en": {"type": "string"},
                        "method_zh": {"type": "string"},
                        "method_en": {"type": "string"},
                        "evidence_zh": {"type": "string"},
                        "evidence_en": {"type": "string"},
                        "relevance_zh": {"type": "string"},
                        "relevance_en": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "kind": {"type": "string"},
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
        (reading.title, reading.authors, int(reading.year), reading.url)
        for readings in bibliography.values()
        for reading in readings
    }
    items = []
    for raw in payload.get("items", []):
        if raw.get("url") not in candidate_urls:
            raise ValueError(f"Digest item has unapproved URL: {raw.get('url')}")
        if raw.get("source_org") not in candidate_sources:
            raise ValueError(f"Digest item has unapproved source: {raw.get('source_org')}")
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
            tags=list(raw.get("tags", [])),
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

    readings = []
    for raw in payload.get("readings", []):
        key = (raw.get("title"), raw.get("authors"), int(raw.get("year", 0)), raw.get("url"))
        if key not in approved_reads:
            raise ValueError(f"Digest has unapproved reading: {key}")
        reading = DeepRead(
            title=raw["title"],
            authors=raw["authors"],
            year=int(raw["year"]),
            url=raw["url"],
            note_zh=str(raw.get("note_zh", "")).strip(),
            note_en=str(raw.get("note_en", "")).strip(),
            argument_zh=str(raw.get("argument_zh", "")).strip(),
            argument_en=str(raw.get("argument_en", "")).strip(),
            method_zh=str(raw.get("method_zh", "")).strip(),
            method_en=str(raw.get("method_en", "")).strip(),
            evidence_zh=str(raw.get("evidence_zh", "")).strip(),
            evidence_en=str(raw.get("evidence_en", "")).strip(),
            relevance_zh=str(raw.get("relevance_zh", "")).strip(),
            relevance_en=str(raw.get("relevance_en", "")).strip(),
            tags=list(raw.get("tags", [])),
            kind=str(raw.get("kind", "reading")).strip() or "reading",
        )
        if _compact_len(reading.note_zh) < MIN_READING_NOTE_ZH_CHARS:
            raise ValueError(
                f"Reading note_zh is too short for {reading.title}: "
                f"{_compact_len(reading.note_zh)} chars"
            )
        readings.append(reading)

    if len(candidates) >= MIN_NEWS_ITEMS and len(items) < MIN_NEWS_ITEMS:
        raise ValueError(f"Digest selected only {len(items)} news items from {len(candidates)} candidates")
    if len(approved_reads) >= MIN_READING_ITEMS and len(readings) < MIN_READING_ITEMS:
        raise ValueError(f"Digest selected only {len(readings)} readings from {len(approved_reads)} approved readings")

    return Digest(
        digest_date=run_date,
        subject=f"SDG Daily Digest - {run_date.isoformat()}",
        overview_zh=str(payload.get("overview_zh", "")).strip()
        or "今日摘要聚焦气候政策、可持续发展风险与转型金融的关键变化。",
        overview_en=str(payload.get("overview_en", "")).strip()
        or "Today's brief tracks key shifts in climate policy, SDG risk, and transition finance.",
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
        terms = _terms_for_tags(candidate.tags)
        items.append(
            DigestItem(
                title_en=candidate.title,
                source_org=candidate.source_org,
                published_date=candidate.published_date,
                summary_zh=_fallback_summary_zh(candidate),
                summary_en=_fallback_summary_en(candidate),
                why_it_matters_zh=_fallback_impact_zh(candidate),
                why_it_matters_en=_fallback_impact_en(candidate),
                terms=terms,
                tags=candidate.tags,
                sdg_links=_sdg_links(candidate.tags),
                url=candidate.url,
            )
        )
    readings = _select_readings_for_candidates(candidates, bibliography)
    overview_zh = "今日关注气候政策、转型金融与可持续发展风险中的关键变化。"
    overview_en = "Today's brief tracks climate policy, transition finance, and SDG-relevant risk signals."
    if not items:
        overview_zh = "今日未筛选到符合可信来源与时间窗口要求的新内容。"
        overview_en = "No eligible updates were found within the trusted-source window today."
    return Digest(
        digest_date=run_date,
        subject=f"SDG Daily Digest - {run_date.isoformat()}",
        overview_zh=overview_zh,
        overview_en=overview_en,
        items=items,
        readings=readings,
    )


def _fallback_summary_zh(candidate: Candidate) -> str:
    hint = _trim_sentence(candidate.summary_hint, 120)
    if hint:
        return f"这条更新聚焦《{candidate.title}》。来源摘要显示：{hint}"
    return f"这条更新聚焦《{candidate.title}》，来自{candidate.source_org}。当前来源提供的可抽取信息有限，需结合原文进一步判断具体内容。"


def _fallback_summary_en(candidate: Candidate) -> str:
    hint = _trim_sentence(candidate.summary_hint, 120)
    if hint:
        return f"This update focuses on \"{candidate.title}\". The source summary indicates: {hint}"
    return f"This update focuses on \"{candidate.title}\" from {candidate.source_org}. The source exposes limited extractable detail, so the original item should be checked for specifics."


def _fallback_impact_zh(candidate: Candidate) -> str:
    tags = "、".join(tag.lstrip("#") for tag in candidate.tags) or "可持续发展"
    return f"它与{tags}相关，可作为观察政策执行、资金流向、发展韧性或区域风险变化的线索。"


def _fallback_impact_en(candidate: Candidate) -> str:
    tags = ", ".join(tag.lstrip("#") for tag in candidate.tags) or "sustainable development"
    return f"It is relevant to {tags} and can be read as a signal for policy implementation, finance flows, resilience, or regional risk."


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
    if "#气候金融" in tags or "#NDC" in tags or "#绿色转型" in tags:
        links.extend(["SDG 13 Climate Action", "SDG 17 Partnerships"])
    if "#SDG进展" in tags:
        links.append("SDG implementation")
    if "#债务可持续性" in tags:
        links.extend(["SDG 8 Decent Work and Growth", "SDG 10 Reduced Inequalities"])
    if "#Global South" in tags:
        links.extend(["SDG 1 No Poverty", "SDG 10 Reduced Inequalities"])
    return list(dict.fromkeys(links))[:3]


def _select_readings_for_candidates(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    target_count: int = 3,
) -> list[DeepRead]:
    selected: list[DeepRead] = []
    seen: set[tuple[str, str, int, str]] = set()
    tags = []
    for candidate in candidates:
        tags.extend(candidate.tags)
    tags.extend(tag for tag in bibliography if tag not in tags)

    for tag in tags:
        for reading in bibliography.get(tag, []):
            key = (reading.title, reading.authors, int(reading.year), reading.url)
            if key in seen:
                continue
            seen.add(key)
            selected.append(_enrich_reading(reading, tag))
            if len(selected) >= target_count:
                return selected
    return selected


def _enrich_reading(reading: DeepRead, tag: str) -> DeepRead:
    defaults = _reading_defaults(tag)
    return DeepRead(
        title=reading.title,
        authors=reading.authors,
        year=reading.year,
        url=reading.url,
        note_zh=reading.note_zh or defaults["note_zh"],
        note_en=reading.note_en or defaults["note_en"],
        argument_zh=reading.argument_zh or defaults["argument_zh"],
        argument_en=reading.argument_en or defaults["argument_en"],
        method_zh=reading.method_zh or defaults["method_zh"],
        method_en=reading.method_en or defaults["method_en"],
        evidence_zh=reading.evidence_zh or defaults["evidence_zh"],
        evidence_en=reading.evidence_en or defaults["evidence_en"],
        relevance_zh=reading.relevance_zh or defaults["relevance_zh"],
        relevance_en=reading.relevance_en or defaults["relevance_en"],
        tags=reading.tags or [tag],
        kind=reading.kind,
    )


def _reading_defaults(tag: str) -> dict[str, str]:
    themes = {
        "#NDC": ("国家气候承诺与执行差距", "national climate pledges and implementation gaps"),
        "#气候金融": ("气候资金口径、核算边界与融资动员", "climate finance definitions, accounting boundaries, and mobilization"),
        "#SDG进展": ("SDG 治理、目标互动与执行评估", "SDG governance, goal interactions, and implementation assessment"),
        "#绿色转型": ("绿色产业政策、公共部门能力与低碳转型工具", "green industrial policy, public-sector capability, and transition tools"),
        "#债务可持续性": ("气候融资、财政空间与发展中国家债务压力", "climate finance, fiscal space, and debt stress in developing economies"),
        "#Global South": ("全球南方在气候治理与发展融资中的结构性处境", "the structural position of the Global South in climate governance and development finance"),
    }
    theme_zh, theme_en = themes.get(tag, ("今日议题的政策背景", "the policy context behind today's themes"))
    return {
        "note_zh": f"适合作为理解{theme_zh}的背景材料。",
        "note_en": f"Useful background for understanding {theme_en}.",
        "argument_zh": f"这篇材料帮助建立关于{theme_zh}的基本分析框架。",
        "argument_en": f"This reading helps frame {theme_en}.",
        "method_zh": "以政策分析、文献讨论或案例比较为主，适合作为概念和判断框架。",
        "method_en": "It mainly uses policy analysis, literature discussion, or comparative examples as a conceptual frame.",
        "evidence_zh": "可结合文中涉及的政策案例、制度设计或资金安排理解其论证。",
        "evidence_en": "Its argument can be read through the policy cases, institutional designs, or finance arrangements it discusses.",
        "relevance_zh": "可用来把今日新闻放进更长周期的政策、融资和发展议程中理解。",
        "relevance_en": "It helps place today's news in a longer policy, finance, and development agenda.",
    }
