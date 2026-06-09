from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from .http import post_json
from .models import Candidate, DeepRead, Digest, DigestItem, DigestTerm

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-4o-mini"

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
    if use_openai and os.getenv("OPENAI_API_KEY") and candidates:
        try:
            raw = _call_openai(candidates, bibliography, run_date, max_items)
            return validate_digest_payload(raw, candidates, bibliography, run_date)
        except Exception as exc:
            print(f"OpenAI generation failed, using deterministic fallback: {exc}")
    return fallback_digest(candidates[:max_items], bibliography, run_date)


def _call_openai(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    run_date: date,
    max_items: int,
) -> dict[str, Any]:
    prompt = {
        "run_date": run_date.isoformat(),
        "instructions": [
            "Return a JSON object that follows the schema.",
            "Select the strongest 3-5 news items. If fewer are credible, return fewer.",
            "Keep title_en in English. Write summary_zh in Chinese, 120-180 Chinese characters if possible.",
            "Make every summary specific to the item title, source, and policy context; avoid repeated boilerplate.",
            "Explain 1-2 professional terms per item with English term, Chinese translation, and plain Chinese explanation.",
            "Select 2-3 readings from the bibliography as a separate readings section.",
            "For each reading, write note_zh explaining why it is useful for today's themes without inventing claims.",
            "Use only candidate URLs for item URLs.",
            "Use readings only from the provided bibliography entries.",
            "Do not invent authors, years, links, organizations, or dates.",
        ],
        "candidates": [candidate.__dict__ for candidate in candidates[:24]],
        "bibliography": {
            tag: [reading.__dict__ for reading in readings]
            for tag, readings in bibliography.items()
        },
    }
    payload = {
        "model": os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        "input": [
            {
                "role": "system",
                "content": (
                    "You are a policy research editor creating a concise Chinese daily digest "
                    "for SDG, ESG, and climate finance professionals."
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
        timeout=60,
    )
    text = _extract_response_text(response)
    return json.loads(text)


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
        "required": ["overview_zh", "items", "readings"],
        "properties": {
            "overview_zh": {"type": "string"},
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
                        "terms",
                        "tags",
                        "url",
                    ],
                    "properties": {
                        "title_en": {"type": "string"},
                        "source_org": {"type": "string"},
                        "published_date": {"type": "string"},
                        "summary_zh": {"type": "string"},
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
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
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
                    "required": ["title", "authors", "year", "url", "note_zh", "tags", "kind"],
                    "properties": {
                        "title": {"type": "string"},
                        "authors": {"type": "string"},
                        "year": {"type": "integer"},
                        "url": {"type": "string"},
                        "note_zh": {"type": "string"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
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
        items.append(
            DigestItem(
                title_en=str(raw["title_en"]).strip(),
                source_org=str(raw["source_org"]).strip(),
                published_date=str(raw["published_date"]).strip(),
                summary_zh=str(raw["summary_zh"]).strip(),
                terms=terms,
                tags=list(raw.get("tags", [])),
                url=str(raw["url"]).strip(),
            )
        )

    readings = []
    for raw in payload.get("readings", []):
        key = (raw.get("title"), raw.get("authors"), int(raw.get("year", 0)), raw.get("url"))
        if key not in approved_reads:
            raise ValueError(f"Digest has unapproved reading: {key}")
        readings.append(
            DeepRead(
                title=raw["title"],
                authors=raw["authors"],
                year=int(raw["year"]),
                url=raw["url"],
                note_zh=str(raw.get("note_zh", "")).strip(),
                tags=list(raw.get("tags", [])),
                kind=str(raw.get("kind", "reading")).strip() or "reading",
            )
        )

    return Digest(
        digest_date=run_date,
        subject=f"SDG Daily Digest - {run_date.isoformat()}",
        overview_zh=str(payload.get("overview_zh", "")).strip()
        or "今日摘要聚焦 SDG、ESG 与气候金融领域的可信来源更新。",
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
        items.append(
            DigestItem(
                title_en=candidate.title,
                source_org=candidate.source_org,
                published_date=candidate.published_date,
                summary_zh=_fallback_summary(candidate),
                terms=_terms_for_tags(candidate.tags),
                tags=candidate.tags,
                url=candidate.url,
            )
        )
    readings = _select_readings_for_candidates(candidates, bibliography)
    overview = (
        "今日摘要按可信来源自动筛选，并区分为新闻更新与延伸阅读。"
        "如模型生成不可用，本期使用保底摘要，但仍保留原文链接与白名单深读材料。"
    )
    if not items:
        overview = "今日未筛选到符合可信来源与时间窗口要求的新内容。"
    return Digest(
        digest_date=run_date,
        subject=f"SDG Daily Digest - {run_date.isoformat()}",
        overview_zh=overview,
        items=items,
        readings=readings,
    )


def _fallback_summary(candidate: Candidate) -> str:
    tags = "、".join(tag.lstrip("#") for tag in candidate.tags) or "可持续发展"
    hint = _trim_sentence(candidate.summary_hint, 90)
    if hint:
        return (
            f"这条来自{candidate.source_org}的更新聚焦《{candidate.title}》。"
            f"{hint} 建议重点观察其对{tags}议题下政策设计、融资安排或地区执行的影响。"
        )
    return (
        f"这条来自{candidate.source_org}的更新聚焦《{candidate.title}》，"
        f"主题与{tags}相关。建议阅读原文，判断其对政策研究、项目融资或区域发展议程的具体意义。"
    )


def _trim_sentence(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


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
            selected.append(
                DeepRead(
                    title=reading.title,
                    authors=reading.authors,
                    year=reading.year,
                    url=reading.url,
                    note_zh=reading.note_zh or _reading_note(tag),
                    tags=reading.tags or [tag],
                    kind=reading.kind,
                )
            )
            if len(selected) >= target_count:
                return selected
    return selected


def _reading_note(tag: str) -> str:
    notes = {
        "#NDC": "适合作为理解国家气候承诺、巴黎协定目标与执行差距之间关系的基础读物。",
        "#气候金融": "适合用来校准气候资金口径、核算边界与公共资金动员私人投资的讨论。",
        "#SDG进展": "适合作为理解 SDG 治理、目标相互作用和执行评估的背景材料。",
        "#绿色转型": "适合作为观察绿色产业政策、公共部门能力与低碳转型工具的理论参照。",
        "#债务可持续性": "适合连接气候融资、财政空间与发展中国家债务压力之间的政策讨论。",
        "#Global South": "适合帮助理解全球南方在气候治理、发展融资和规则公平中的结构性处境。",
    }
    return notes.get(tag, "适合作为今日议题的背景读物，帮助把单条新闻放入更长的政策讨论中理解。")
