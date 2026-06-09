from __future__ import annotations

import json
from urllib import request


DEFAULT_TIMEOUT_SECONDS = 20
USER_AGENT = "sdg-daily-digest/0.1 (+https://github.com/actions)"


def fetch_text(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    req = request.Request(url, headers={"User-Agent": USER_AGENT})
    with request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def post_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            **headers,
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset, errors="replace"))
