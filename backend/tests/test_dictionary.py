"""Dictionary behavior checks; no board, model, or extra dependencies required."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
import dictionary_store
import import_dictionary
import translation_store


class DictionaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(
            database, "DB_PATH", Path(self.temp.name) / "test.db"
        )
        self.db_patch.start()
        dictionary_store.init_dictionary()

    def tearDown(self):
        self.db_patch.stop()
        self.temp.cleanup()

    def test_typo_finds_ground_and_preserves_distinct_senses(self):
        result = dictionary_store.search_dictionary("groud")
        closest = result["matches"][0]
        self.assertEqual(closest["term"], "ground")
        self.assertEqual(closest["match_type"], "similar")
        self.assertEqual(len(closest["meanings"]), 3)
        self.assertTrue(any("Construction" in x["domain"] for x in closest["meanings"]))
        self.assertTrue(any("circuit reference" in x["domain"] for x in closest["meanings"]))
        self.assertNotIn("translation_confidence", closest)

    def test_exact_match_precedes_other_spelling_suggestions(self):
        result = dictionary_store.search_dictionary("lead", limit=1)
        self.assertEqual(len(result["matches"]), 1)
        match = result["matches"][0]
        self.assertEqual(match["term"], "lead")
        self.assertEqual(match["match_type"], "exact")
        self.assertEqual(len(match["meanings"]), 3)
        self.assertEqual(match["spelling_similarity"], 1)

    def test_unicode_case_and_prefix_queries(self):
        exact = dictionary_store.search_dictionary("  ＧＲＯＵＮＤ  ")
        self.assertEqual(exact["matches"][0]["match_type"], "exact")
        prefix = dictionary_store.search_dictionary("floa")
        self.assertEqual(prefix["matches"][0]["term"], "floating")
        self.assertEqual(prefix["matches"][0]["match_type"], "prefix")

    def test_empty_unknown_and_other_language_have_no_guesses(self):
        for query, language in [("  ", "en"), ("zzzzzzzzzz", "en"), ("ground", "ko")]:
            with self.subTest(query=query, language=language):
                self.assertEqual(
                    dictionary_store.search_dictionary(query, language=language)["matches"],
                    [],
                )

    def test_query_is_data_and_invalid_limits_are_rejected(self):
        dictionary_store.search_dictionary("'; DROP TABLE dictionary_entries; --")
        self.assertEqual(dictionary_store.search_dictionary("tap")["matches"][0]["term"], "tap")
        for limit in (0, 11, True, "5"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                dictionary_store.search_dictionary("ground", limit=limit)
        with self.assertRaises(ValueError):
            dictionary_store.search_dictionary("a" * 101)

    def test_reinitializing_keeps_ids_and_saved_translations(self):
        before = dictionary_store.search_dictionary("ground")["matches"][0]["meanings"]
        database.init_db()
        translation_store.init_translation_store()
        saved = translation_store.save_translation({
            "elapsed_ms": None, "source_language": "en", "target_language": "ko",
            "source": "Hello.", "translation_confidence": None,
            "translation": "안녕하세요.", "alternatives": [],
        })
        stats = dictionary_store.init_dictionary()
        self.assertEqual(stats, {"terms": 10, "meanings": 25})
        self.assertEqual(
            dictionary_store.search_dictionary("ground")["matches"][0]["meanings"],
            before,
        )
        self.assertEqual(translation_store.list_translations(), [saved])

    def test_base_forms_and_transpositions(self):
        self.assertEqual(
            dictionary_store.search_dictionary("grounded")["matches"][0]["term"],
            "ground",
        )
        self.assertEqual(
            dictionary_store.search_dictionary("grounded")["matches"][0]["match_type"],
            "base_form",
        )
        self.assertEqual(
            dictionary_store.search_dictionary("laod")["matches"][0]["term"],
            "load",
        )

    def test_new_dictionary_entries_refresh_cached_vocabulary(self):
        dictionary_store.search_dictionary("widget")
        with database.db_connection() as connection:
            connection.execute(dictionary_store.ENTRY_SQL, dictionary_store.entry_values({
                "key": "custom.widget", "term": "widget", "domain": "Custom",
                "meaning": "A user-defined component.",
            }))
            dictionary_store.mark_dictionary_changed(connection)
        result = dictionary_store.search_dictionary("widget")["matches"][0]
        self.assertEqual(result["match_type"], "exact")
        self.assertEqual(result["meanings"][0]["meaning"], "A user-defined component.")

    def test_legacy_starter_schema_migrates_without_losing_a_custom_word(self):
        with database.db_connection() as connection:
            connection.execute("DROP TABLE dictionary_entries")
            connection.execute("""
                CREATE TABLE dictionary_entries (
                    id INTEGER PRIMARY KEY, entry_key TEXT UNIQUE, term TEXT,
                    normalized_term TEXT, language TEXT, domain TEXT,
                    meaning TEXT, example TEXT
                )
            """)
            connection.execute("""
                INSERT INTO dictionary_entries VALUES
                (42,'custom.widget','widget','widget','en','Custom','A custom item.','')
            """)
        dictionary_store.init_dictionary()
        match = dictionary_store.search_dictionary("widget")["matches"][0]
        self.assertEqual(match["meanings"][0]["id"], 42)
        self.assertEqual(match["meanings"][0]["meaning"], "A custom item.")

    def test_wrong_archive_is_rejected_before_touching_existing_data(self):
        before = dictionary_store.dictionary_stats()
        path = Path(self.temp.name) / "wrong.zip"
        path.write_bytes(b"not the expected dictionary archive")
        with self.assertRaisesRegex(ValueError, "Checksum"):
            import_dictionary.import_dictionary(path, Path(self.temp.name) / "cache")
        self.assertEqual(dictionary_store.dictionary_stats(), before)

    def test_incomplete_import_rolls_back_its_delete_and_insert(self):
        with database.db_connection() as connection:
            connection.execute(dictionary_store.ENTRY_SQL, dictionary_store.entry_values({
                "key": "oewn2025:n:1:previous", "term": "previous",
                "domain": "Test", "meaning": "A previously imported definition.",
                "source": import_dictionary.SOURCE,
            }))
            dictionary_store.mark_dictionary_changed(connection)
        before = dictionary_store.dictionary_stats()

        class Synset:
            def lemma_names(self): return ["new_word"]
            def examples(self): return []
            def pos(self): return "n"
            def offset(self): return 2
            def lexname(self): return "noun.test"
            def definition(self): return "An incomplete test import."

        class Reader:
            def all_synsets(self): return iter([Synset()])

        root = Path(self.temp.name) / "corpus"
        root.mkdir()
        for part in ("noun", "verb", "adj", "adv"):
            (root / f"{part}.exc").write_text("")
        with self.assertRaisesRegex(RuntimeError, "Incomplete"):
            import_dictionary.write_reader(Reader(), root)
        self.assertEqual(dictionary_store.dictionary_stats(), before)
        self.assertEqual(
            dictionary_store.search_dictionary("previous")["matches"][0]["meanings"][0]["meaning"],
            "A previously imported definition.",
        )


if __name__ == "__main__":
    unittest.main()
