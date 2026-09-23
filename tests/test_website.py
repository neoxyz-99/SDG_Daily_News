from __future__ import annotations

import json
from pathlib import Path
import unittest

from sdg_digest.website import CONTACT_EMAIL, PUBLIC_ISSUE_COUNT, build_site, load_public_issues, normalize_digest


ROOT = Path(__file__).resolve().parents[1]


class WebsiteTests(unittest.TestCase):
    def test_invalid_or_missing_artwork_preserves_published_site(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "docs"
            output.mkdir()
            existing = output / "index.html"
            existing.write_text("last known good")
            assets = root / "assets"
            (assets / "issues").mkdir(parents=True)
            with self.assertRaisesRegex(RuntimeError, "without artwork"):
                build_site(ROOT / "archive", output, assets)
            latest = load_public_issues(ROOT / "archive")[0].date
            (assets / "issues" / f"{latest}.jpg").write_bytes(b"invalid image")
            with self.assertRaisesRegex(RuntimeError, "invalid artwork"):
                build_site(ROOT / "archive", output, assets)
            self.assertEqual(existing.read_text(), "last known good")

    def test_legacy_duplicate_is_removed_from_news_and_search(self) -> None:
        raw = {"digest_date": "2026-09-21", "recent_news": [
            {"title_en": "Same article", "url": "https://www.example.org/story/?utm_source=email#top", "one_sentence_en": "Brief"},
            {"title_en": "Different article", "url": "https://example.org/other", "one_sentence_en": "Other"}],
            "items": [{"title_en": "Same article", "url": "https://example.org/story", "core_argument_en": "Analysis"}]}
        issue = normalize_digest(raw)
        self.assertEqual([item.title for item in issue.news], ["Different article"])
        self.assertEqual(len(issue.signals), 1)
        self.assertEqual(len(issue.items), 2)

    def test_corrected_september_issue_has_matching_reading(self) -> None:
        raw = json.loads((ROOT / "archive/2026-09-21/digest.json").read_text())
        issue = normalize_digest(raw)
        self.assertEqual((len(issue.news), len(issue.signals)), (6, 2))
        self.assertEqual(issue.readings[0].url, "https://doi.org/10.1080/14693062.2004.9685508")
        self.assertIn("Mainstreaming adaptation", issue.readings[0].title)
        self.assertIn("Florence Crick", issue.readings[0].source)

    def test_public_archive_contains_latest_and_four_previous_issues(self) -> None:
        issues = load_public_issues(ROOT / "archive")
        self.assertEqual(len(issues), PUBLIC_ISSUE_COUNT)
        self.assertEqual(issues, sorted(issues, key=lambda issue: issue.date, reverse=True))
        self.assertTrue(all(issue.items for issue in issues))
        self.assertTrue(all(item.paragraphs for issue in issues for item in issue.items))

    def test_build_site_creates_routes_search_and_copyright(self) -> None:
        with self.subTest("temporary build"):
            import tempfile

            with tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "docs"
                issues = build_site(ROOT / "archive", output, ROOT / "website_assets")
                expected = [
                    output / "index.html",
                    output / "archive" / "index.html",
                    output / "search" / "index.html",
                    output / "about" / "index.html",
                    output / "copyright" / "index.html",
                    output / "issues" / issues[0].date / "index.html",
                    output / "search-index.json",
                ]
                self.assertTrue(all(path.exists() for path in expected))
                self.assertTrue(all((output / "assets" / "issues" / f"{issue.date}.jpg").exists() for issue in issues))
                latest_html = (output / "issues" / issues[0].date / "index.html").read_text(encoding="utf-8")
                self.assertIn('class="issue-rail"', latest_html)
                self.assertIn(f"assets/issues/{issues[0].date}.jpg", latest_html)
                copyright_html = (output / "copyright" / "index.html").read_text(encoding="utf-8")
                self.assertIn(f"mailto:{CONTACT_EMAIL}", copyright_html)
                self.assertIn("non-commercial knowledge-sharing project", copyright_html)
                generated_html = "".join(path.read_text(encoding="utf-8") for path in output.rglob("*.html"))
                self.assertNotIn("Signals, structures, and scholarship", generated_html)
                self.assertNotIn("foundational scholarship", generated_html)
                search_index = json.loads((output / "search-index.json").read_text(encoding="utf-8"))
                self.assertTrue(search_index)
                self.assertGreaterEqual(
                    {item["type"] for item in search_index},
                    {"News", "Research Signal", "Research Reading"},
                )

    def test_invalid_latest_digest_falls_back_to_previous_archives(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "archive"
            archive.mkdir()
            (archive / "index.json").write_text(
                json.dumps({"digests": [{"date": "2099-01-01"}, {"date": "2026-07-27"}]}),
                encoding="utf-8",
            )
            (archive / "2099-01-01").mkdir()
            (archive / "2099-01-01" / "digest.json").write_text("not json", encoding="utf-8")
            valid_dir = archive / "2026-07-27"
            valid_dir.mkdir()
            valid_dir.joinpath("digest.json").write_text(
                (ROOT / "archive" / "2026-07-27" / "digest.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            self.assertEqual([issue.date for issue in load_public_issues(archive)], ["2026-07-27"])

    def test_missing_archive_fails_without_overwriting_existing_site(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "docs"
            output.mkdir()
            existing = output / "index.html"
            existing.write_text("last known good", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                build_site(root / "missing", output, ROOT / "website_assets")
            self.assertEqual(existing.read_text(encoding="utf-8"), "last known good")
