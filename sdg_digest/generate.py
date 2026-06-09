from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from .http import post_json
from .models import Candidate, DeepRead, Digest, DigestItem, DigestTerm

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-4o-mini"


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
            "Select the strongest 5-8 items. If fewer are credible, return fewer.",
            "Keep title_en in English. Write summary_zh in Chinese, 100-150 Chinese characters if possible.",
            "Explain 1-3 professional terms per item with English term, Chinese translation, and plain Chinese explanation.",
            "Use only candidate URLs for item URLs.",
            "Use deep_reads only from the provided bibliography entries.",
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
        "required": ["overview_zh", "items"],
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
                        "deep_reads",
                    ],
                    "properties": {
                        "title_en": {"type": "string"},
                        "source_org": {"type": "string"},
                        "published_date": {"type": "string"},
                        "summary_zh": {"type": "string"},
                        "terms": {
                            "type": "array",
                            "maxItems": 3,
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
                        "deep_reads": {
                            "type": "array",
                            "maxItems": 3,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["title", "authors", "year", "url"],
                                "properties": {
                                    "title": {"type": "string"},
                                    "authors": {"type": "string"},
                                    "year": {"type": "integer"},
                                    "url": {"type": "string"},
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
        deep_reads = []
        for reading in raw.get("deep_reads", []):
            key = (
                reading.get("title"),
                reading.get("authors"),
                int(reading.get("year", 0)),
                reading.get("url"),
            )
            if key not in approved_reads:
                raise ValueError(f"Digest item has unapproved deep read: {key}")
            deep_reads.append(
                DeepRead(
                    title=reading["title"],
                    authors=reading["authors"],
                    year=int(reading["year"]),
                    url=reading["url"],
                )
            )
        items.append(
            DigestItem(
                title_en=str(raw["title_en"]).strip(),
                source_org=str(raw["source_org"]).strip(),
                published_date=str(raw["published_date"]).strip(),
                summary_zh=str(raw["summary_zh"]).strip(),
                terms=terms,
                tags=list(raw.get("tags", [])),
                url=str(raw["url"]).strip(),
                deep_reads=deep_reads,
            )
        )

    return Digest(
        digest_date=run_date,
        subject=f"SDG Daily Digest - {run_date.isoformat()}",
        overview_zh=str(payload.get("overview_zh", "")).strip()
        or "今日摘要聚焦 SDG、ESG 与气候金融领域的可信来源更新。",
        items=items,
    )


def fallback_digest(
    candidates: list[Candidate],
    bibliography: dict[str, list[DeepRead]],
    run_date: date,
) -> Digest:
    items: list[DigestItem] = []
    for candidate in candidates:
        deep_reads = _readings_for_tags(candidate.tags, bibliography)
        items.append(
            DigestItem(
                title_en=candidate.title,
                source_org=candidate.source_org,
                published_date=candidate.published_date,
                summary_zh=(
                    "该条目来自可信来源，涉及可持续发展、气候政策或绿色转型议题。"
                    "建议结合原文判断其对政策研究、融资工具或区域发展议程的具体影响。"
                ),
                terms=[
                    DigestTerm(
                        term_en="policy implication",
                        term_zh="政策含义",
                        explanation_zh="指信息对政策设计、执行或评估可能带来的影响。",
                    )
                ],
                tags=candidate.tags,
                url=candidate.url,
                deep_reads=deep_reads,
            )
        )
    overview = "今日摘要基于可信来源自动筛选；未调用模型时使用保守模板摘要。"
    if not items:
        overview = "今日未筛选到符合可信来源与时间窗口要求的内容。"
    return Digest(
        digest_date=run_date,
        subject=f"SDG Daily Digest - {run_date.isoformat()}",
        overview_zh=overview,
        items=items,
    )


def _readings_for_tags(tags: list[str], bibliography: dict[str, list[DeepRead]]) -> list[DeepRead]:
    selected: list[DeepRead] = []
    for tag in tags:
        for reading in bibliography.get(tag, []):
            if reading not in selected:
                selected.append(reading)
            if len(selected) >= 3:
                return selected
    return selected
