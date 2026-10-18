"""Check search and storage together without connecting to the board/model."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
import main
from fastapi.testclient import TestClient


class DictionaryAPITests(unittest.TestCase):
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

    def test_typo_and_multiple_meanings_are_available_without_ai(self):
        with patch.object(main, "interpret_ai") as model:
            response = self.client.get("/dictionary/search", params={"q": "groud", "limit": 1})
            model.assert_not_called()
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["query"], "groud")
        match = result["matches"][0]
        self.assertEqual(match["term"], "ground")
        self.assertEqual(match["match_type"], "similar")
        self.assertEqual(len(match["meanings"]), 3)
        self.assertTrue(any("Construction" in item["domain"] for item in match["meanings"]))
        self.assertTrue(all(item["entry_key"] for item in match["meanings"]))

    def test_validation_and_no_matches(self):
        for params in ({}, {"q": ""}, {"q": "  "}, {"q": "x" * 101},
                       {"q": "ground", "limit": 11}, {"q": "ground", "language": " "}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/dictionary/search", params=params).status_code, 422)
        response = self.client.get("/dictionary/search", params={"q": "zzzzzzzzzz"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["matches"], [])

    def test_stats_do_not_claim_full_corpus_when_only_glossary_loaded(self):
        response = self.client.get("/dictionary/stats")
        self.assertEqual(response.status_code, 200)
        stats = response.json()
        self.assertEqual((stats["terms"], stats["meanings"]), (10, 25))
        self.assertFalse(stats["full_dictionary_loaded"])

    def test_search_keeps_saved_translation_unchanged(self):
        payload = {
            "elapsed_ms": None, "source_language": "en", "target_language": "ko",
            "source": "Check the ground.", "translation_confidence": None,
            "translation": "접지를 확인하세요.", "alternatives": [],
        }
        saved = self.client.post("/translations", json=payload)
        self.assertEqual(saved.status_code, 201)
        self.client.get("/dictionary/search", params={"q": "ground"})
        self.assertEqual(self.client.get("/translations").json(), [saved.json()])


if __name__ == "__main__":
    unittest.main()
