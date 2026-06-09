from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import DeepRead, FurtherReading, Source


def load_json_yaml(path: str | Path) -> dict[str, Any]:
    """Load JSON-compatible YAML.

    The project keeps `.yml` filenames as the public interface, while the v1
    files are JSON-compatible YAML so the runtime does not need PyYAML.
    """
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_sources(path: str | Path) -> list[Source]:
    data = load_json_yaml(path)
    sources = []
    for raw in data.get("sources", []):
        sources.append(
            Source(
                name=raw["name"],
                type=raw["type"],
                strategy=raw["strategy"],
                url=raw.get("url"),
                issn=list(raw.get("issn", [])),
                allowed_domains=list(raw.get("allowed_domains", [])),
                default_tags=list(raw.get("default_tags", [])),
                layer=raw.get("layer", "research"),
            )
        )
    return sources


def load_bibliography(path: str | Path) -> dict[str, list[DeepRead]]:
    data = load_json_yaml(path)
    readings: dict[str, list[DeepRead]] = {}
    for tag, items in data.get("readings", {}).items():
        readings[tag] = [
            DeepRead(
                title=item["title"],
                authors=item["authors"],
                year=int(item["year"]),
                url=item.get("url") or f"https://doi.org/{item.get('doi', '').strip()}",
                note_zh=item.get("brief_zh", item.get("note_zh", "")),
                note_en=item.get("note_en", ""),
                journal=item.get("journal", ""),
                doi=item.get("doi", ""),
                methodology_zh=item.get("methodology_zh", ""),
                further_reading=[
                    FurtherReading(
                        title=reading["title"],
                        authors=reading["authors"],
                        year=int(reading["year"]),
                        description_zh=reading["description_zh"],
                        url=reading.get("url", ""),
                    )
                    for reading in item.get("further_reading", [])
                ],
                argument_zh=item.get("argument_zh", ""),
                argument_en=item.get("argument_en", ""),
                method_zh=item.get("method_zh", ""),
                method_en=item.get("method_en", ""),
                evidence_zh=item.get("evidence_zh", ""),
                evidence_en=item.get("evidence_en", ""),
                relevance_zh=item.get("relevance_zh", ""),
                relevance_en=item.get("relevance_en", ""),
                tags=list(item.get("tags", [tag])),
                kind=item.get("kind", "journal article"),
            )
            for item in items
        ]
    return readings
