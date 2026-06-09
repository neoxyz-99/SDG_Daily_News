from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import DeepRead, Source


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
                url=item["url"],
                note_zh=item.get("note_zh", ""),
                tags=[tag],
                kind=item.get("kind", "reading"),
            )
            for item in items
        ]
    return readings
