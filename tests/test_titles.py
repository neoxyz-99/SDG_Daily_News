import json
import os
import unittest
from dataclasses import replace
from datetime import date
from unittest.mock import patch

from sdg_digest.generate import fallback_digest, validate_digest_payload
from sdg_digest.titles import translate_candidate_titles
from tests.test_generate import _candidate, _item


def response(rows):
    return {"choices": [{"message": {"content": json.dumps({"titles": rows})}}]}


class TitleTests(unittest.TestCase):
    def test_multilingual_titles_are_translated_and_english_is_preserved(self):
        candidates = [
            replace(_candidate(), title="中国发布气候适应计划"),
            replace(_candidate(), title="El transporte limpio llega a las comunidades rurales"),
            replace(_candidate(), title="L’accès à l’eau dans les villes"),
            _candidate(),
        ]
        translations = ["China releases climate adaptation plan",
                        "Clean transport reaches rural communities", "Access to water in cities"]
        rows = [{"id": i, "source_language": language, "title_en": title}
                for i, (language, title) in enumerate(zip(
                    ["zh", "es", "fr", "en"], translations + ["Unrequested English rewrite"]
                ))]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch(
            "sdg_digest.titles.post_json", return_value=response(list(reversed(rows)))
        ):
            translated = translate_candidate_titles(candidates)
        self.assertEqual([c.title_en for c in translated], translations + [candidates[-1].title])
        self.assertEqual([c.title for c in translated], [c.title for c in candidates])

    def test_copied_non_english_and_missing_translations_fail_closed(self):
        candidate = replace(_candidate(), title="El transporte limpio llega a las comunidades rurales")
        for rows in [[], [{"id": 0, "source_language": "es", "title_en": candidate.title}],
                     [{"id": 0, "source_language": "zh", "title_en": "未翻译的标题"}]]:
            with self.subTest(rows=rows), patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch(
                "sdg_digest.titles.post_json", return_value=response(rows)
            ) as api:
                with self.assertRaisesRegex(RuntimeError, "refusing to publish"):
                    translate_candidate_titles([candidate])
                self.assertEqual(api.call_count, 2)

    def test_validation_and_fallback_use_prepared_title_in_both_modules(self):
        news = replace(_candidate(), title="中国发布气候适应计划", title_en="China releases climate adaptation plan",
                       layer="event", url="https://example.org/news")
        research = replace(_candidate(), title="城市的水资源治理", title_en="Urban water governance")
        payload = {"recent_news": [{"title_en": news.title, "source_org": news.source_org,
                    "published_date": news.published_date, "url": news.url,
                    "one_sentence_zh": "中国公布了气候适应计划。", "one_sentence_en": "China published an adaptation plan."}],
                   "research_signals": [_item(research)]}
        payload.update(issue_title_en="Climate Adaptation, Water Access and Local Institutions",
                       issue_title_zh="气候适应、水资源获取与地方制度",
                       title_support=[{"url": item.url, "angle_en": "This article connects adaptation and local policy implementation."}
                                      for item in [news, research]])
        digests = [validate_digest_payload(payload, [news, research], {}, date(2026, 9, 30)),
                   fallback_digest([news, research], {}, date(2026, 9, 30))]
        for digest in digests:
            self.assertEqual(digest.recent_news[0].title_en, news.title_en)
            self.assertEqual(digest.recent_news[0].title_original, news.title)
            self.assertEqual(digest.research_signals[0].title_en, research.title_en)
            self.assertEqual(digest.research_signals[0].title_original, research.title)

    def test_untranslated_script_is_rejected_by_generation_validation(self):
        candidate = replace(_candidate(), title="城市的水资源治理")
        with self.assertRaisesRegex(ValueError, "English"):
            validate_digest_payload({"items": [_item(candidate)]}, [candidate], {}, date(2026, 9, 30))
