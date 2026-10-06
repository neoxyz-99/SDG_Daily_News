import json
import os
import tempfile
import unittest
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sdg_digest.archive import write_archive
from sdg_digest.editorial import load_editorial_history, validate_issue_title
from sdg_digest.generate import generate_digest, validate_digest_payload
from sdg_digest.models import Digest, DigestItem, NewsBrief
from sdg_digest.website import normalize_digest, _home, _archive_cards, _issue_page
from tests.test_generate import _candidate, _candidate_two, _payload, _item


TITLE = "Energy Security, Industrial Policy and Climate Accountability"


def article(index, research=False):
    values = dict(title_en=f"Article {index} on climate policy", source_org=f"Source {index}",
                  url=f"https://example.org/{index}", published_date="2026-10-05")
    if research:
        return DigestItem(**values, summary_zh="政策分析", terms=[], tags=[], core_argument_en="Policy evidence.")
    return NewsBrief(**values, one_sentence_zh="新闻简讯", one_sentence_en="A policy update.")


def title_payload(items):
    return {"issue_title_en": TITLE, "issue_title_zh": "能源安全、产业政策与气候问责",
            "title_support": [{"url": item.url, "angle_en": "This article explains one of the title's policy strands."}
                              for item in items]}


class IssueTitleTests(unittest.TestCase):
    def test_title_covers_multiple_selected_articles_and_majority_of_signals(self):
        news, signals = [article(0)], [article(i, True) for i in range(1, 4)]
        title, _, support = validate_issue_title(title_payload(signals[:2] + news), news, signals)
        self.assertEqual(title, TITLE)
        self.assertEqual(len(support), 3)

    def test_single_article_duplicates_and_unselected_references_are_rejected(self):
        items = [article(0), article(1)]
        cases = [title_payload(items[:1]), title_payload([items[0], items[0]]),
                 title_payload([items[0], article(99)])]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_issue_title(payload, items, [])

    def test_support_must_cover_research_majority_not_just_two_briefs(self):
        news, signals = [article(0), article(1)], [article(i, True) for i in range(2, 5)]
        with self.assertRaisesRegex(ValueError, "majority"):
            validate_issue_title(title_payload(news + signals[:1]), news, signals)

    def test_title_cannot_be_missing_or_copy_an_article(self):
        items = [replace(article(0), title_en=TITLE), article(1)]
        for title in ["", TITLE]:
            payload = title_payload(items)
            payload["issue_title_en"] = title
            with self.subTest(title=title), self.assertRaises(ValueError):
                validate_issue_title(payload, items, [])

    def test_thin_issue_uses_neutral_label_instead_of_article_headline(self):
        self.assertEqual(validate_issue_title(title_payload([article(0)]), [article(0)], []), ("", "", []))
        issue = normalize_digest({"digest_date": "2026-10-05", "subject": "Week of October 5",
                                  "issue_title_en": "", "overview_en": "A single article finding"})
        self.assertEqual(issue.headline, "Week of October 5")

    def test_support_is_checked_after_source_caps(self):
        candidates = [replace(_candidate(), title=f"Signal {i}", source_org="Same source",
                              url=f"https://example.org/{i}") for i in range(3)]
        payload = _payload(candidates[0], candidates[1])
        payload["items"] = [_item(c) for c in candidates]
        payload["title_support"][1]["url"] = candidates[2].url
        with self.assertRaisesRegex(ValueError, "actually selected"):
            validate_digest_payload(payload, candidates, {}, date(2026, 10, 5))

    def test_invalid_title_retries_with_coverage_feedback(self):
        first, second = _candidate(), _candidate_two()
        valid = _payload(first, second)
        invalid = deepcopy(valid)
        invalid["title_support"] = invalid["title_support"][:1]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch(
            "sdg_digest.generate._call_openai", side_effect=[invalid, valid]
        ) as call:
            result = generate_digest([first, second], {}, date(2026, 10, 5), 5)
        self.assertEqual(call.call_count, 2)
        self.assertIn("at least two", call.call_args.kwargs["feedback"])
        self.assertEqual(result.issue_title_en, valid["issue_title_en"])

    def test_title_intro_and_support_survive_archive_and_render_separately(self):
        news = [article(0), article(1)]
        en, zh, support = validate_issue_title(title_payload(news), news, [])
        intro = "A concrete finding that belongs in the introduction."
        digest = Digest(date(2026, 10, 5), "Week of October 5", "具体发现", [],
                        overview_en=intro, recent_news=news, issue_title_en=en,
                        issue_title_zh=zh, title_support=support)
        with tempfile.TemporaryDirectory() as directory:
            folder = write_archive(digest, directory)
            raw = json.loads((folder / "digest.json").read_text())
            self.assertEqual(raw["title_support"][0]["url"], news[0].url)
            self.assertIn(TITLE, (folder / "digest.md").read_text())
            self.assertIn(intro, (folder / "digest.html").read_text())
            history = load_editorial_history(directory, date(2026, 10, 6))
            self.assertEqual(history[0]["issue_title"], TITLE)
            self.assertEqual(history[0]["editorial_note"], intro)
        issue = normalize_digest(raw)
        for page in [_home([issue]), _issue_page(issue, [issue])]:
            self.assertIn(f"<h1>{TITLE}</h1>", page)
            self.assertIn(intro, page)
            self.assertNotIn(f"<h1>{intro}</h1>", page)
        archive = _archive_cards([issue], 1)
        self.assertIn(TITLE, archive)
        self.assertIn(intro, archive)

    def test_legacy_heading_stays_unchanged(self):
        raw = {"digest_date": "2026-09-28", "overview_en": "The archived heading"}
        self.assertEqual(normalize_digest(raw).headline, "The archived heading")
