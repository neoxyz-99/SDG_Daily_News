import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sdg_digest.editorial import load_editorial_history
from sdg_digest.generate import generate_digest
from tests.test_generate import _candidate


class EditorialTests(unittest.TestCase):
    def test_history_reads_six_prior_issues_and_skips_invalid_and_future_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for day in range(1, 11):
                path = root / f"2026-09-{day:02d}" / "digest.json"
                path.parent.mkdir()
                path.write_text(json.dumps({"overview_en": f"Lead {day}", "weekly_thread_en": "Thread",
                    "items": [{"title_en": "Title", "source_org": "Source", "core_argument_en": "Mechanism"}]}))
            (root / "2026-09-09" / "digest.json").write_text("invalid json")
            history = load_editorial_history(root, date(2026, 9, 10))
        self.assertEqual([item["date"] for item in history], [f"2026-09-{i:02d}" for i in range(8, 2, -1)])
        self.assertEqual(history[0]["articles"][0]["angle"], "Mechanism")

    def test_history_reaches_selection_prompt(self):
        history = [{"date": "2026-09-21", "editorial_note": "Who pays?",
                    "articles": [{"title": "Heat adaptation", "angle": "Cost sharing"}]}]
        response = {"output": [{"content": [{"type": "output_text", "text": "{}"}]}]}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch(
            "sdg_digest.generate.post_json", return_value=response
        ) as api:
            generate_digest([_candidate()], {}, date(2026, 9, 30), 5, editorial_history=history)
        prompt = json.loads(api.call_args.args[1]["input"][1]["content"])
        self.assertEqual(prompt["recent_editorial_history"], history)
        self.assertIn("evidence", " ".join(prompt["instructions"]))

