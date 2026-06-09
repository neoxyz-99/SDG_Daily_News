from __future__ import annotations

import os

from .http import post_json
from .models import Digest

RESEND_URL = "https://api.resend.com/emails"


def send_email(digest: Digest, html_body: str) -> dict:
    api_key = _required_env("RESEND_API_KEY")
    to_email = _required_env("DIGEST_TO_EMAIL")
    from_email = _required_env("DIGEST_FROM_EMAIL")
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": digest.subject,
        "html": html_body,
    }
    return post_json(
        RESEND_URL,
        payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
