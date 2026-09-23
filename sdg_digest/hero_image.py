from __future__ import annotations

import argparse
import base64
import json
import os
import time
from pathlib import Path
from typing import Callable

import requests

from .image_validation import validate_jpeg


IMAGE_API_URL = "https://api.openai.com/v1/images/generations"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1536x864"
DEFAULT_QUALITY = "medium"
DEFAULT_COMPRESSION = 88
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class HeroImageError(RuntimeError):
    """Raised when an issue hero image cannot be generated safely."""


def latest_issue_date(archive_dir: Path) -> str:
    try:
        index = json.loads((archive_dir / "index.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HeroImageError(f"Cannot read archive index: {exc}") from exc

    for entry in index.get("digests", []):
        issue_date = entry.get("date") if isinstance(entry, dict) else None
        if isinstance(issue_date, str) and issue_date.strip():
            return issue_date.strip()
    raise HeroImageError("Archive index does not contain an issue date")


def load_digest(archive_dir: Path, issue_date: str) -> dict:
    digest_path = archive_dir / issue_date / "digest.json"
    try:
        raw = json.loads(digest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HeroImageError(f"Cannot read digest for {issue_date}: {exc}") from exc
    if not isinstance(raw, dict):
        raise HeroImageError(f"Digest for {issue_date} is not a JSON object")
    return raw


def _clean(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _signal_titles(digest: dict, limit: int = 4) -> list[str]:
    rows = digest.get("research_signals") or digest.get("items") or []
    titles: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _clean(row.get("title_en"), 180)
        if title:
            titles.append(title)
        if len(titles) == limit:
            break
    return titles


def build_editorial_prompt(digest: dict) -> str:
    editorial = _clean(digest.get("overview_en"), 600)
    weekly_thread = _clean(digest.get("weekly_thread_en"), 600)
    signal_titles = _signal_titles(digest)
    if not editorial and not weekly_thread and not signal_titles:
        raise HeroImageError("Digest does not contain enough English material for an editorial image")

    themes = "; ".join(signal_titles) or "climate governance and sustainable development"
    return f"""Use case: photorealistic-natural
Asset type: editorial hero image for a modern weekly climate-governance knowledge website
Primary request: Create one original visual interpretation of this issue's editorial argument. Editorial note: {editorial or weekly_thread}
Editorial question: {weekly_thread or editorial}
Issue themes: {themes}
Scene/backdrop: a plausible contemporary real-world setting that unifies the issue themes through people, institutions, infrastructure, land, water, or energy systems; choose one coherent scene rather than a collage
Subject: anonymous people and public-interest systems affected by or responding to the issue; no individual should dominate
Style/medium: sophisticated contemporary editorial photography, natural realism, restrained international magazine aesthetic, not retro and not futuristic concept art
Composition/framing: wide 16:9 landscape composition with a strong focal point, layered depth, and a clear visual hierarchy suitable for a website hero
Lighting/mood: natural light, serious and thoughtful, cautiously constructive rather than celebratory
Color palette: restrained natural colors with muted greens, earth tones, pale blue, and charcoal
Materials/textures: credible real-world textures and subtle photographic grain
Constraints: original scene only; do not imitate or reproduce any source image; no identifiable public figures; no text; no logos; no flags; no brand marks; no watermark
Avoid: disaster spectacle, propaganda imagery, corporate stock-photo poses, split-screen collage, glowing AI motifs, oversaturated colors"""


def _error_message(response: requests.Response) -> str:
    request_id = response.headers.get("x-request-id", "unknown")
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return f"Image API returned HTTP {response.status_code} (request {request_id})"
    code = error.get("code") or error.get("type") or "unknown_error"
    message = _clean(error.get("message"), 300) or "Image generation failed"
    return f"Image API error {code}: {message} (request {request_id})"


def request_image(
    prompt: str,
    api_key: str,
    *,
    model: str = DEFAULT_MODEL,
    post: Callable[..., requests.Response] = requests.post,
    sleep: Callable[[float], None] = time.sleep,
    attempts: int = 3,
) -> bytes:
    if not api_key:
        raise HeroImageError("OPENAI_API_KEY is not configured")

    payload = {
        "model": model,
        "prompt": prompt,
        "size": DEFAULT_SIZE,
        "quality": DEFAULT_QUALITY,
        "output_format": "jpeg",
        "output_compression": DEFAULT_COMPRESSION,
        "n": 1,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    response: requests.Response | None = None
    for attempt in range(attempts):
        try:
            response = post(IMAGE_API_URL, headers=headers, json=payload, timeout=180)
        except requests.RequestException as exc:
            if attempt + 1 == attempts:
                raise HeroImageError(f"Image API request failed after {attempts} attempts: {exc}") from exc
            sleep(2**attempt)
            continue

        if response.status_code < 400:
            break
        if response.status_code not in TRANSIENT_STATUS_CODES or attempt + 1 == attempts:
            raise HeroImageError(_error_message(response))
        sleep(2**attempt)

    if response is None:
        raise HeroImageError("Image API did not return a response")
    try:
        encoded = response.json()["data"][0]["b64_json"]
        image_bytes = base64.b64decode(encoded, validate=True)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HeroImageError("Image API response did not contain valid base64 image data") from exc
    try:
        validate_jpeg(image_bytes)
    except ValueError as exc:
        raise HeroImageError("Image API response was not a valid JPEG") from exc
    return image_bytes


def write_image_atomic(destination: Path, image_bytes: bytes) -> None:
    validate_jpeg(image_bytes)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(image_bytes)
    temporary.replace(destination)


def generate_issue_image(
    archive_dir: Path,
    output_dir: Path,
    issue_date: str,
    api_key: str,
    *,
    force: bool = False,
    model: str = DEFAULT_MODEL,
    post: Callable[..., requests.Response] = requests.post,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    destination = output_dir / f"{issue_date}.jpg"
    if destination.exists() and not force:
        try:
            validate_jpeg(destination.read_bytes())
            return destination
        except ValueError:
            print(f"Replacing invalid artwork for {issue_date}")
    digest = load_digest(archive_dir, issue_date)
    image_bytes = request_image(
        build_editorial_prompt(digest),
        api_key,
        model=model,
        post=post,
        sleep=sleep,
    )
    write_image_atomic(destination, image_bytes)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the editorial hero image for an SDG Weekly Compass issue")
    parser.add_argument("--date", help="Issue date in YYYY-MM-DD; defaults to the latest archive entry")
    parser.add_argument("--archive", default="archive")
    parser.add_argument("--output", default="website_assets/issues")
    parser.add_argument("--force", action="store_true", help="Replace an existing issue image")
    parser.add_argument("--model", default=os.getenv("HERO_IMAGE_MODEL", DEFAULT_MODEL))
    args = parser.parse_args()

    archive_dir = Path(args.archive)
    issue_date = args.date or latest_issue_date(archive_dir)
    destination = generate_issue_image(
        archive_dir,
        Path(args.output),
        issue_date,
        os.getenv("OPENAI_API_KEY", ""),
        force=args.force,
        model=args.model,
    )
    print(f"Editorial hero image ready: {destination}")


if __name__ == "__main__":
    main()
