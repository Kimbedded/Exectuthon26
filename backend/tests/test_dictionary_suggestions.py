"""Automatic word options without a board or a second AI request."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
import dictionary_store
import main
from fastapi.testclient import TestClient


class AutomaticDictionaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(database, "DB_PATH", Path(self.temp.name) / "test.db")
        self.db_patch.start()
        self.client = TestClient(main.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.db_patch.stop()
        self.temp.cleanup()

    def options(self, **updates):
        request = {"source": "Check the ground.", "translation": "접지를 확인하세요.",
                   "source_language": "en", "target_language": "ko", **updates}
        with patch.object(main, "interpret_ai") as ai:
            response = self.client.post("/dictionary/suggestions", json=request)
            ai.assert_not_called()
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_english_source_is_used_for_korean_translation(self):
        result = self.options(context="This electrical circuit has voltage problems.")
        self.assertEqual(result["basis"], "source")
        word = result["terms"][0]
        self.assertEqual(word["observed"], "ground")
        self.assertEqual(word["matches"][0]["term"], "ground")
        meaning = word["matches"][0]["meanings"][0]
        self.assertIn("circuit reference", meaning["domain"])
        self.assertIn("circuit", meaning["context_words"])

    def test_different_context_changes_order_not_translation(self):
        result = self.options(context="Inspect the soil at this construction site.")
        meaning = result["terms"][0]["matches"][0]["meanings"][0]
        self.assertIn("Construction", meaning["domain"])
        self.assertNotIn("translation", result)

    def test_english_translation_is_used_when_source_is_korean(self):
        result = self.options(source="접지를 확인하세요.", translation="Check the ground.",
                              source_language="ko", target_language="en")
        self.assertEqual(result["basis"], "translation")
        self.assertEqual(result["terms"][0]["observed"], "ground")

    def test_spelling_options_do_not_rewrite_source(self):
        result = self.options(source="Check the groud.")
        term = result["terms"][0]
        self.assertEqual(term["observed"], "groud")
        self.assertEqual(term["matches"][0]["term"], "ground")
        self.assertEqual(term["matches"][0]["match_type"], "similar")

    def test_non_english_no_speech_and_empty_have_no_options(self):
        for values in (
            {"source_language": "ko", "target_language": "es"},
            {"source": "[BLANK_AUDIO]"}, {"translation": "No speech detected."},
            {"source": ""}, {"translation": ""},
        ):
            with self.subTest(values=values):
                self.assertEqual(self.options(**values)["terms"], [])

    def test_new_corpus_word_and_synonyms_not_limited_to_seed_terms(self):
        with database.db_connection() as connection:
            connection.execute(dictionary_store.ENTRY_SQL, dictionary_store.entry_values({
                "key": "custom.bank", "term": "bank", "domain": "Finance",
                "meaning": "A financial institution that holds money.",
                "synonyms": ["financial institution", "depository"],
            }))
            dictionary_store.mark_dictionary_changed(connection)
        result = self.options(source="The bank holds money.")
        term = next(term for term in result["terms"] if term["observed"] == "bank")
        self.assertIn("depository", term["matches"][0]["meanings"][0]["synonyms"])

    def test_large_or_malformed_result_rejected(self):
        for body in ({}, {"source": "a" * 3001, "translation": "a"},
                     {"source": "ground", "translation": "a", "context": "a" * 6001}):
            self.assertEqual(self.client.post("/dictionary/suggestions", json=body).status_code, 422)


if __name__ == "__main__":
    unittest.main()
