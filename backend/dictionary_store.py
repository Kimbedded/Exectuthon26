"""Offline dictionary storage, spelling suggestions, and contextual meanings."""
from bisect import bisect_left
from contextlib import closing
from difflib import SequenceMatcher, get_close_matches
from functools import lru_cache
import json
from pathlib import Path
import sqlite3
import string
import unicodedata
from uuid import uuid4

import database
from database import db_connection

SEED_PATH = Path(__file__).with_name("dictionary_seed.json")
ENTRY_SQL = """
    INSERT INTO dictionary_entries
        (entry_key, term, normalized_term, language, domain, meaning, example,
         source, source_url, part_of_speech, synonyms_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(entry_key) DO UPDATE SET
        term=excluded.term, normalized_term=excluded.normalized_term,
        language=excluded.language, domain=excluded.domain,
        meaning=excluded.meaning, example=excluded.example,
        source=excluded.source, source_url=excluded.source_url,
        part_of_speech=excluded.part_of_speech, synonyms_json=excluded.synonyms_json
"""


def normalize_term(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def entry_values(entry: dict) -> tuple:
    return (
        entry["key"], entry["term"], normalize_term(entry["term"]),
        entry.get("language", "en"), entry["domain"], entry["meaning"],
        entry.get("example", ""), entry.get("source", "Project glossary"),
        entry.get("source_url", ""), entry.get("part_of_speech", ""),
        json.dumps(entry.get("synonyms", []), ensure_ascii=False),
    )


def dictionary_stats(connection=None) -> dict:
    if connection is None:
        with db_connection() as connection:
            return dictionary_stats(connection)
    row = connection.execute("""
        SELECT COUNT(DISTINCT language || ':' || normalized_term) AS terms,
               COUNT(*) AS meanings FROM dictionary_entries
    """).fetchone()
    return dict(row)


def mark_dictionary_changed(connection):
    connection.execute("""
        INSERT INTO dictionary_meta(key,value) VALUES ('revision',?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (uuid4().hex,))


def init_dictionary() -> dict:
    entries = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    with db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS dictionary_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_key TEXT NOT NULL UNIQUE,
                term TEXT NOT NULL,
                normalized_term TEXT NOT NULL,
                language TEXT NOT NULL,
                domain TEXT NOT NULL,
                meaning TEXT NOT NULL,
                example TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'Project glossary',
                source_url TEXT NOT NULL DEFAULT '',
                part_of_speech TEXT NOT NULL DEFAULT '',
                synonyms_json TEXT NOT NULL DEFAULT '[]'
            )
        """)
        columns = {row["name"] for row in connection.execute(
            "PRAGMA table_info(dictionary_entries)"
        )}
        for name, declaration in (
            ("source", "TEXT NOT NULL DEFAULT 'Project glossary'"),
            ("source_url", "TEXT NOT NULL DEFAULT ''"),
            ("part_of_speech", "TEXT NOT NULL DEFAULT ''"),
            ("synonyms_json", "TEXT NOT NULL DEFAULT '[]'"),
        ):
            if name not in columns:
                connection.execute(
                    "ALTER TABLE dictionary_entries ADD COLUMN " + name + " " + declaration
                )
        connection.execute("""
            CREATE INDEX IF NOT EXISTS dictionary_term_lookup
            ON dictionary_entries (language, normalized_term)
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS dictionary_meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS dictionary_forms (
                language TEXT NOT NULL, inflected TEXT NOT NULL, base TEXT NOT NULL,
                PRIMARY KEY(language, inflected, base)
            )
        """)
        connection.executemany(ENTRY_SQL, [entry_values(entry) for entry in entries])
        mark_dictionary_changed(connection)
        return dictionary_stats(connection)


@lru_cache(maxsize=4)
def _vocabulary(path: str, revision: str, language: str):
    # Cache vocabulary only, not every definition; Save/Review doesn't invalidate it.
    with closing(sqlite3.connect(path)) as connection:
        words = tuple(row[0] for row in connection.execute("""
            SELECT DISTINCT normalized_term FROM dictionary_entries
            WHERE language=? ORDER BY normalized_term
        """, (language,)))
    return words, frozenset(words)


def _one_edit_words(query: str, vocabulary: frozenset):
    if len(query) > 32:
        return set()
    result = set()
    for index in range(len(query) + 1):
        left, right = query[:index], query[index:]
        if right and left + right[1:] in vocabulary:
            result.add(left + right[1:])
        if len(right) > 1:
            swapped = left + right[1] + right[0] + right[2:]
            if swapped in vocabulary:
                result.add(swapped)
        for letter in string.ascii_lowercase:
            inserted = left + letter + right
            if inserted in vocabulary:
                result.add(inserted)
            if right:
                replaced = left + letter + right[1:]
                if replaced in vocabulary:
                    result.add(replaced)
    return result


def _base_forms(query: str, vocabulary: frozenset, irregular: set):
    result = set(irregular)
    if query in vocabulary:
        return result.intersection(vocabulary)
    # Suggest a base form only if it is an actual dictionary entry.
    for suffix, replacements in (
        ("s", ("",)), ("es", ("",)), ("ies", ("y",)),
        ("ed", ("", "e")), ("ing", ("", "e")),
        ("er", ("", "e")), ("est", ("", "e")),
    ):
        if query.endswith(suffix) and len(query) > len(suffix) + 1:
            stem = query[:-len(suffix)]
            result.update(stem + ending for ending in replacements)
            if suffix in {"ed", "ing", "er", "est"} and len(stem) > 2:
                if stem[-1] == stem[-2]:
                    result.add(stem[:-1])
    return result.intersection(vocabulary)


def search_dictionary(query: str, limit: int = 5, language: str = "en") -> dict:
    if not isinstance(query, str) or len(query) > 100:
        raise ValueError("Search must be a string of at most 100 characters.")
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("Limit must be between 1 and 10.")
    if not isinstance(language, str) or not 2 <= len(language.strip()) <= 20:
        raise ValueError("Invalid dictionary language.")
    language = language.strip().casefold()
    normalized = normalize_term(query)
    response = {"query": query.strip(), "language": language, "matches": []}
    if not normalized:
        return response
    with db_connection() as connection:
        revision = connection.execute(
            "SELECT value FROM dictionary_meta WHERE key='revision'"
        ).fetchone()[0]
        irregular = {row[0] for row in connection.execute("""
            SELECT base FROM dictionary_forms WHERE language=? AND inflected=?
        """, (language, normalized))}
    words, word_set = _vocabulary(str(database.DB_PATH), revision, language)
    start = bisect_left(words, normalized)
    candidates = set()
    for word in words[start:start + max(30, limit * 4)]:
        if not word.startswith(normalized):
            break
        candidates.add(word)
    one_edit = _one_edit_words(normalized, word_set)
    base_forms = _base_forms(normalized, word_set, irregular) if language == "en" else set()
    candidates.update(one_edit, base_forms)
    if len(candidates) < limit:
        candidates.update(get_close_matches(normalized, words, n=limit * 3, cutoff=0.6))
    ranked = []
    for word in candidates:
        similarity = SequenceMatcher(None, normalized, word, autojunk=False).ratio()
        if word == normalized:
            priority, kind = 0, "exact"
        elif word in base_forms:
            priority, kind = 1, "base_form"
        elif word.startswith(normalized):
            priority, kind = 2, "prefix"
        elif word in one_edit:
            priority, kind = 3, "similar"
        elif normalized in word:
            priority, kind = 4, "contains"
        else:
            priority, kind = 5, "similar"
        ranked.append(((priority, -similarity, len(word), word), word, kind, similarity))
    ranked.sort()
    selected = ranked[:limit]
    if not selected:
        return response
    placeholders = ",".join("?" for _ in selected)
    with db_connection() as connection:
        rows = connection.execute("""
            SELECT * FROM dictionary_entries
            WHERE language=? AND normalized_term IN (""" + placeholders + """)
            ORDER BY CASE WHEN source='Project glossary' THEN 0 ELSE 1 END, id
        """, (language, *(item[1] for item in selected))).fetchall()
    grouped = {}
    for row in rows:
        group = grouped.setdefault(row["normalized_term"], {
            "term": row["term"], "meanings": []
        })
        group["meanings"].append({
            **{key: row[key] for key in (
                "id", "entry_key", "domain", "meaning", "example",
                "source", "source_url", "part_of_speech"
            )},
            "synonyms": json.loads(row["synonyms_json"]),
        })
    response["matches"] = [
        {**grouped[word], "match_type": kind, "spelling_similarity": round(score, 3)}
        for _, word, kind, score in selected
    ]
    return response


if __name__ == "__main__":
    stats = init_dictionary()
    print(f"PASS: Dictionary ready — {stats['terms']:,} words/phrases, "
          f"{stats['meanings']:,} word meanings.")
