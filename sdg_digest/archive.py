from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .models import Digest
from .render import render_html, render_markdown


def write_archive(digest: Digest, output_dir: str | Path = "archive") -> Path:
    root = Path(output_dir)
    day_dir = root / digest.digest_date.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)

    payload = asdict(digest)
    payload["digest_date"] = digest.digest_date.isoformat()
    (day_dir / "digest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (day_dir / "digest.md").write_text(render_markdown(digest), encoding="utf-8")
    (day_dir / "digest.html").write_text(render_html(digest), encoding="utf-8")
    _update_index(root, digest)
    return day_dir


def _update_index(root: Path, digest: Digest) -> None:
    index_path = root / "index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        index = {"digests": []}
    digest_date = digest.digest_date.isoformat()
    entry = {
        "date": digest_date,
        "subject": digest.subject,
        "item_count": len(digest.recent_news) + len(digest.research_signals or digest.items) + len(digest.classic_readings or digest.readings),
        "html": f"{digest_date}/digest.html",
        "markdown": f"{digest_date}/digest.md",
        "json": f"{digest_date}/digest.json",
    }
    index["digests"] = [item for item in index.get("digests", []) if item.get("date") != digest_date]
    index["digests"].insert(0, entry)
    index["digests"] = sorted(index["digests"], key=lambda item: item["date"], reverse=True)
    root.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "index.html").write_text(_render_index_html(index), encoding="utf-8")


def _render_index_html(index: dict) -> str:
    rows = "\n".join(
        f"<li><a href=\"{item['html']}\">{item['date']}</a> - {item['item_count']} items</li>"
        for item in index.get("digests", [])
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>The Governance Brief Archive</title>
  <style>
    body {{ font-family: Arial, "Microsoft YaHei", sans-serif; max-width: 760px; margin: 0 auto; padding: 32px 18px; background: #f6f7f4; color: #1f2933; }}
    h1 {{ color: #123524; }}
    a {{ color: #0f766e; }}
    li {{ margin: 10px 0; }}
  </style>
</head>
<body>
  <h1>The Governance Brief Archive</h1>
  <ul>{rows}</ul>
</body>
</html>
"""


def today_iso() -> str:
    return date.today().isoformat()
