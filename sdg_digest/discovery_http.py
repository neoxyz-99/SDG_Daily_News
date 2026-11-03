"""Bounded public-web transport. No authentication, paywall bypass or silent redirects."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .http import USER_AGENT


class FetchFailure(RuntimeError):
    pass


@dataclass
class FetchResult:
    url: str
    text: str
    content_type: str = "text/html"
    fetched_at: float = 0
    cached: bool = False


class PublicFetcher:
    def __init__(self, cache_dir: Path, *, max_requests=120, per_host=30,
                 delay=1.5, timeout=15, max_bytes=2_000_000, cache_hours=12):
        self.cache_dir = Path(cache_dir)
        self.max_requests, self.per_host = max_requests, per_host
        self.delay, self.timeout, self.max_bytes = delay, timeout, max_bytes
        self.cache_seconds = cache_hours * 3600
        self.requests = self.cache_hits = self.bytes = 0
        self.host_counts: dict[str, int] = {}
        self.last_request: dict[str, float] = {}
        self.robots: dict[str, RobotFileParser] = {}
        self.blocked_hosts: set[str] = set()
        self.sitemaps: dict[str, list[str]] = {}

    @staticmethod
    def validate_url(url):
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise FetchFailure("unsafe_url")
        if parts.port not in {None, 80, 443}:
            raise FetchFailure("unsafe_port")
        try:
            addresses = socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise FetchFailure("non_public_address")
        except OSError as exc:
            raise FetchFailure("dns_failure") from exc

    def _request(self, url, delay=None):
        self.validate_url(url)
        host = urlsplit(url).netloc
        if host in self.blocked_hosts:
            raise FetchFailure("host_access_restricted")
        if self.requests >= self.max_requests or self.host_counts.get(host, 0) >= self.per_host:
            raise FetchFailure("request_budget_exhausted")
        pause = max(self.delay, delay or 0) - (time.monotonic() - self.last_request.get(host, 0))
        if pause > 60:
            raise FetchFailure("crawl_delay_requires_later_run")
        if pause > 0:
            time.sleep(pause)
        self.requests += 1
        self.host_counts[host] = self.host_counts.get(host, 0) + 1
        self.last_request[host] = time.monotonic()
        try:
            with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=self.timeout,
                              stream=True, allow_redirects=False) as response:
                if response.status_code in {401, 403, 429}:
                    self.blocked_hosts.add(host)  # no retries this run, including Retry-After
                if 300 <= response.status_code < 400:
                    return response.status_code, response.headers.get("Location", ""), ""
                if response.status_code != 200:
                    raise FetchFailure(f"http_{response.status_code}")
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    self.bytes += len(chunk)
                    if size > self.max_bytes:
                        raise FetchFailure("response_size_limit")
                    chunks.append(chunk)
                kind = response.headers.get("Content-Type", "").lower()
                if kind and not any(x in kind for x in ("text", "xml", "json")):
                    raise FetchFailure("unsupported_content_type:" + kind.split(";")[0])
                return 200, b"".join(chunks).decode(response.encoding or "utf-8", errors="replace"), kind
        except requests.RequestException as exc:
            raise FetchFailure(type(exc).__name__) from exc

    def _policy(self, url):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            parser = RobotFileParser(origin + "/robots.txt")
            try:
                code, body, _ = self._request(parser.url)
                if code != 200:
                    raise FetchFailure("robots_redirect_unverified")
                parser.parse(body.splitlines())
                self.sitemaps[origin] = parser.site_maps() or []
            except FetchFailure as exc:
                if str(exc) == "http_404":
                    parser.parse(["User-agent: *", "Allow: /"])
                else:
                    # Fail closed for inaccessible robots, including network errors.
                    parser.parse(["User-agent: *", "Disallow: /"])
            self.robots[origin] = parser
        policy = self.robots[origin]
        if not policy.can_fetch(USER_AGENT, url):
            raise FetchFailure("robots_disallowed_or_unavailable")
        rate = policy.request_rate(USER_AGENT)
        return max(policy.crawl_delay(USER_AGENT) or 0, rate.seconds / rate.requests if rate else 0)

    def get(self, url, _redirects=0):
        if _redirects > 3:
            raise FetchFailure("redirect_limit")
        delay = self._policy(url)
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache_dir / (key + ".json")
        if path.exists():
            try:
                cached = json.loads(path.read_text())
                if time.time() - cached["fetched_at"] < self.cache_seconds:
                    if any(marker in cached.get("text", "").lower() for marker in ("_incapsula_resource", "cf-chl-", "captcha")):
                        raise FetchFailure("access_challenge")
                    self.cache_hits += 1
                    return FetchResult(**{**cached, "cached": True})
            except (ValueError, KeyError, TypeError):
                pass
        code, body, kind = self._request(url, delay)
        if code != 200:
            if not body:
                raise FetchFailure("redirect_missing_location")
            # Every redirect target receives URL, robots and rate checks.
            return self.get(urljoin(url, body), _redirects + 1)
        if any(marker in body.lower() for marker in ("_incapsula_resource", "cf-chl-", "captcha")):
            raise FetchFailure("access_challenge")
        result = FetchResult(url, body, kind, time.time())
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if "noarchive" not in body.lower():
            path.write_text(json.dumps(asdict(result)), encoding="utf-8")
        return result

    def metrics(self):
        return {"http_requests": self.requests, "cache_hits": self.cache_hits,
                "downloaded_bytes": self.bytes, "requests_by_host": self.host_counts}
