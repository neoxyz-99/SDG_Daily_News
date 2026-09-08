from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import unittest

from sdg_digest.hero_image import (
    HeroImageError,
    build_editorial_prompt,
    generate_issue_image,
    latest_issue_date,
    request_image,
)


JPEG_BYTES = b"\xff\xd8\xff\xe0test-jpeg"


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, request_id: str = "req_test") -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = {"x-request-id": request_id}

    def json(self) -> dict:
        return self._payload


class HeroImageTests(unittest.TestCase):
    def test_latest_issue_and_prompt_use_english_editorial_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary)
            archive.joinpath("index.json").write_text(
                json.dumps({"digests": [{"date": "2026-09-07"}]}), encoding="utf-8"
            )
            self.assertEqual(latest_issue_date(archive), "2026-09-07")

        prompt = build_editorial_prompt(
            {
                "overview_en": "Institutions face a climate stress test.",
                "weekly_thread_en": "Should policy adapt institutions or rebuild them?",
                "research_signals": [{"title_en": "Grid resilience after extreme heat"}],
            }
        )
        self.assertIn("Institutions face a climate stress test.", prompt)
        self.assertIn("Grid resilience after extreme heat", prompt)
        self.assertIn("no text; no logos", prompt)

    def test_request_image_retries_transient_error_and_returns_jpeg(self) -> None:
        responses = iter(
            [
                FakeResponse(429, {"error": {"code": "rate_limit_exceeded", "message": "retry"}}),
                FakeResponse(200, {"data": [{"b64_json": base64.b64encode(JPEG_BYTES).decode()}]}),
            ]
        )
        sleeps: list[float] = []

        image = request_image(
            "prompt",
            "secret",
            post=lambda *args, **kwargs: next(responses),
            sleep=sleeps.append,
        )

        self.assertEqual(image, JPEG_BYTES)
        self.assertEqual(sleeps, [1])

    def test_generate_issue_image_writes_asset_and_skips_existing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            issue = archive / "2026-09-07"
            issue.mkdir(parents=True)
            issue.joinpath("digest.json").write_text(
                json.dumps({"overview_en": "A climate governance test."}), encoding="utf-8"
            )
            output = root / "assets"
            calls = 0

            def post(*args, **kwargs):
                nonlocal calls
                calls += 1
                return FakeResponse(200, {"data": [{"b64_json": base64.b64encode(JPEG_BYTES).decode()}]})

            destination = generate_issue_image(archive, output, "2026-09-07", "secret", post=post)
            self.assertEqual(destination.read_bytes(), JPEG_BYTES)
            generate_issue_image(archive, output, "2026-09-07", "secret", post=post)
            self.assertEqual(calls, 1)

    def test_non_transient_api_error_does_not_retry(self) -> None:
        calls = 0

        def post(*args, **kwargs):
            nonlocal calls
            calls += 1
            return FakeResponse(400, {"error": {"code": "moderation_blocked", "message": "blocked"}})

        with self.assertRaisesRegex(HeroImageError, "moderation_blocked"):
            request_image("prompt", "secret", post=post, sleep=lambda _: None)
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
