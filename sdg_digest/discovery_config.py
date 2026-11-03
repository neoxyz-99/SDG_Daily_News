from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DiscoveryConfig:
    rolling_days: int = 21
    upcoming_days: int = 14
    max_upcoming: int = 0
    max_requests: int = 120
    requests_per_host: int = 30
    delay_seconds: float = 1.5
    timeout_seconds: int = 15
    max_response_bytes: int = 2_000_000
    cache_hours: int = 12
    max_depth: int = 2
    max_links_per_page: int = 25
    max_discovered_sources: int = 12
    max_feed_entries: int = 500
    evidence_requests: int = 30
    selection_pool: int = 60
    relevance_threshold: int = 4
    state_retention_days: int = 120
    search_url: str = ""  # Optional operator-provided SearXNG-compatible JSON endpoint.
    max_searches: int = 4
    seeds: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path):
        values = json.loads(Path(path).read_text(encoding="utf-8"))
        config = cls(**values)
        for name in ("rolling_days", "upcoming_days", "max_requests", "requests_per_host",
                     "timeout_seconds", "max_response_bytes", "max_links_per_page",
                     "max_feed_entries", "selection_pool", "state_retention_days"):
            if getattr(config, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("max_upcoming", "max_depth", "max_discovered_sources", "evidence_requests",
                     "max_searches", "delay_seconds", "cache_hours", "relevance_threshold"):
            if getattr(config, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        return config
