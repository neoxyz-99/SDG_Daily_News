import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sdg_digest.backtest import ROOT, run_backtest
from sdg_digest.cli import main
from sdg_digest.discovery import DiscoveryPipeline
from sdg_digest.discovery_config import DiscoveryConfig
from sdg_digest.discovery_parse import canonical_url, normalize, parse_html
from sdg_digest.generate import generate_digest
from sdg_digest.models import Digest, NewsBrief
from sdg_digest.render import render_html, render_markdown
from sdg_digest.website import normalize_digest
from tests.test_discovery import FixtureFetcher, candidate, html


class HistoricalRegressionTests(unittest.TestCase):
    def test_four_cases_are_discovered_without_forced_publication_or_invented_dates(self):
        with tempfile.TemporaryDirectory() as output:
            result = run_backtest(ROOT / "data/discovery/historical_cases.json", output)
            self.assertEqual(len(result["regression_case_discovery"]["reviewed_corpus"]), 4)
            self.assertEqual(len(result["regression_case_discovery"]["dated_replay"]), 3)
            self.assertNotIn("climate_week_2026", result["regression_case_discovery"]["dated_replay"])
            september = json.loads((Path(output) / "2026-09-07.json").read_text())
            agenda = next(c for c in september["candidates"] if c["url"].endswith("660273"))
            self.assertEqual(agenda["development_stage"], "scheduled")
            self.assertEqual(agenda["decision"], "selected_for_publication")  # upcoming only
            self.assertEqual(agenda["event_date"], "2026-09-10")
            october = json.loads((Path(output) / "2026-10-12.json").read_text())
            presentation = next(c for c in october["candidates"] if c["url"].endswith("661097"))
            self.assertEqual(presentation["decision"], "insufficient_evidence")
            self.assertIn("metadata_only", presentation["exclusion_reason"])
            self.assertEqual(result["replay_cost"]["ai_calls"], 0)
            self.assertIsNone(result["unmeasurable_historical_metrics"]["production_important_event_recall"])
            self.assertTrue(all("full_text" not in c for c in october["candidates"]))

    def test_body_session_identifier_groups_differently_titled_reporting(self):
        body = "The IPCC-65 session was suspended after governments failed to agree a climate assessment timeline."
        one = candidate(title="Governments fail to settle assessment timetable", summary_hint=body, full_text=body, event_id="")
        two = candidate(title="Different report of climate talks", summary_hint=body, full_text=body, event_id="")
        self.assertEqual(one.event_id, "ipcc-65:2026")
        self.assertEqual(one.event_id, two.event_id)

    def test_feed_and_html_same_document_are_not_two_editorial_items(self):
        with tempfile.TemporaryDirectory() as directory:
            p = DiscoveryPipeline(DiscoveryConfig(evidence_requests=0), date(2026, 10, 19), Path(directory), FixtureFetcher())
            first = candidate(full_text="", development_stage="unknown")
            second = candidate(modified_date="2026-10-13", full_text="A longer climate adaptation policy report on government implementation and finance reform.")
            p._add(first, "primary")
            p._add(second, "primary")
            self.assertEqual(len(p.evaluate()), 1)
            self.assertTrue(any(c["exclusion_reason"] == "same_url_same_document_version" for c in p.rows))

    def test_cross_week_republication_is_suppressed_but_new_substance_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = DiscoveryConfig(evidence_requests=0)
            p = DiscoveryPipeline(cfg, date(2026, 10, 19), Path(directory), FixtureFetcher())
            c = candidate(event_name="International adaptation finance dialogue")
            p._add(c, "primary")
            p.evaluate()
            d = Digest(date(2026, 10, 19), "Test", "", [], recent_news=[NewsBrief(c.title, c.source_org, c.published_date, c.url, "测试")])
            p.finalize(d, published=True)
            p.save(Path(directory) / "report.json")
            next_run = DiscoveryPipeline(cfg, date(2026, 10, 26), Path(directory), FixtureFetcher())
            next_run._add(replace(c, url="https://second.int/news", source_org="Second", published_date="2026-10-22"), "primary")
            self.assertEqual(next_run.evaluate(), [])
            self.assertIn("event_update_already_published", next_run.rows[0]["exclusion_reason"])

    def test_discovery_only_cli_does_not_generate_send_or_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            cfg = path / "config.json"
            cfg.write_text(json.dumps({"seeds": [], "evidence_requests": 0}))
            with patch("sys.argv", ["digest", "--pipeline", "discovery", "--discovery-only", "--dry-run", "--date", "2026-10-19", "--discovery-config", str(cfg), "--discovery-state", str(path / "state"), "--diagnostics", str(path / "report")]), patch("sdg_digest.cli.load_sources", return_value=[]), patch("sdg_digest.cli.load_bibliography", return_value={}), patch("sdg_digest.cli.load_sent_articles", return_value={}), patch("sdg_digest.cli.generate_digest") as generate, patch("sdg_digest.cli.send_email") as email, patch("sdg_digest.cli.write_archive") as archive, patch("builtins.print"):
                main()
            generate.assert_not_called()
            email.assert_not_called()
            archive.assert_not_called()
            self.assertTrue((path / "report/2026-10-19.json").exists())
            self.assertFalse((path / "state/events.json").exists())

    def test_upcoming_survives_archive_and_renderers_without_becoming_news(self):
        from dataclasses import asdict
        item = NewsBrief("Policy dialogue", "Agency", "2026-10-25", "https://agency.int/event", "会议安排，尚无成果。", "Scheduled, no outcome yet.")
        digest = Digest(date(2026, 10, 19), "Test", "", [], upcoming_events=[item])
        self.assertIn("Upcoming", render_markdown(digest))
        self.assertIn("Scheduled, no outcome yet", render_html(digest))
        raw = asdict(digest); raw["digest_date"] = "2026-10-19"
        public = normalize_digest(raw)
        self.assertEqual(len(public.upcoming), 1)
        self.assertEqual(len(public.news), 0)

    def test_generation_receives_all_assessed_candidates_and_event_evidence(self):
        candidates = [candidate(title=f"Climate adaptation policy reform {i}", url=f"https://agency.int/{i}") for i in range(45)]
        response = {"output": [{"content": [{"type": "output_text", "text": "{}"}]}]}
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}), patch("sdg_digest.generate.post_json", return_value=response) as api:
            with self.assertRaisesRegex(RuntimeError, "refusing to publish"):
                generate_digest(candidates, {}, date(2026, 10, 19), 5)
        prompt = json.loads(api.call_args.args[1]["input"][1]["content"])
        self.assertEqual(len(prompt["recent_news_candidates"]), 45)
        self.assertIn("development_stage", prompt["recent_news_candidates"][0])
        self.assertTrue(any("An agenda" in instruction for instruction in prompt["instructions"]))


if __name__ == "__main__":
    unittest.main()
