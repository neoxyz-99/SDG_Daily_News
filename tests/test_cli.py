import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sdg_digest.cli import main
from sdg_digest.models import Digest
from tests.test_generate import _candidate


class CliTests(unittest.TestCase):
    def test_selection_gets_larger_translated_pool_and_prior_editorial_context(self):
        candidates = [replace(_candidate(), title=f"Climate policy update {i}", layer="event", source_org=f"Source {i // 2}",
                              url=f"https://example.org/news/{i}") for i in range(12)]
        digest = Digest(date(2026, 9, 30), "Test issue", "", [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = root / "2026-09-21" / "digest.json"
            previous.parent.mkdir()
            previous.write_text(json.dumps({"overview_en": "Who pays?"}))
            with patch("sys.argv", ["digest", "--dry-run", "--date", "2026-09-30",
                       "--output-dir", directory, "--sent-articles", str(root / "sent.json"),
                       "--max-recent-news", "3", "--candidate-pool", "10"]), patch(
                "sdg_digest.cli.load_sources", return_value=[]
            ), patch("sdg_digest.cli.load_bibliography", return_value={}), patch(
                "sdg_digest.cli.collect_candidates", return_value=candidates
            ), patch("sdg_digest.cli.filter_relevant_candidates", side_effect=lambda items, **kw: items), patch(
                "sdg_digest.cli.translate_candidate_titles",
                side_effect=lambda items: [replace(item, title_en=item.title) for item in items]
            ), patch("sdg_digest.cli.collect_academic_readings", return_value={}), patch(
                "sdg_digest.cli.generate_digest", return_value=digest
            ) as generate, patch("sdg_digest.cli.send_email") as send, patch("builtins.print"):
                main()
            selected = generate.call_args.args[0]
            self.assertEqual(len(selected), 10)
            self.assertTrue(all(item.title_en for item in selected))
            self.assertEqual(generate.call_args.kwargs["max_recent_news"], 3)
            self.assertEqual(generate.call_args.kwargs["editorial_history"][0]["editorial_note"], "Who pays?")
            send.assert_not_called()
