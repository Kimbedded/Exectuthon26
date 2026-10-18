"""Import pinned Open English Wordnet 2025 into SQLite for offline lookup."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile
import warnings
import zipfile

from database import db_connection
from dictionary_store import (
    ENTRY_SQL, dictionary_stats, entry_values, init_dictionary,
    mark_dictionary_changed, normalize_term,
)

SOURCE = "Open English Wordnet 2025"
SOURCE_URL = "https://en-word.net/downloads"
CORPUS_SHA256 = "38b16326159f51853626b7d24a44c453fa88ab33f06fce5ec8fc5996d1c2be93"
SUPPORT_URL = "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip"
SUPPORT_SHA256 = "cbda5ea6eef7f36a97a43d4a75f85e07fccbb4f23657d27b4ccbc93e2646ab59"
POS_NAMES = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def support_data(cache: Path) -> Path:
    destination = cache / "corpora" / "wordnet.zip"
    if destination.exists() and digest(destination) == SUPPORT_SHA256:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".zip.part")
    print("Downloading dictionary reader support data (one time)...", flush=True)
    try:
        subprocess.run([
            "curl", "--fail", "--location", "--silent", "--show-error",
            "--connect-timeout", "10", "--max-time", "120",
            SUPPORT_URL, "--output", str(temporary),
        ], check=True)
        if digest(temporary) != SUPPORT_SHA256:
            raise ValueError("Reader support checksum mismatch.")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def load_reader(archive_path: Path, support: Path, root: Path):
    import nltk
    from nltk.corpus.reader.wordnet import WordNetCorpusReader

    with zipfile.ZipFile(archive_path) as archive:
        # The complete archive is verified against the pinned checksum first.
        archive.extractall(root)
    corpus = root / "oewn2025"
    with zipfile.ZipFile(support) as archive:
        (corpus / "lexnames").write_bytes(archive.read("wordnet/lexnames"))
    nltk.data.path[:0] = [str(support.parent.parent), str(corpus)]
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="The multilingual functions are not available")
        return WordNetCorpusReader(str(corpus), None)


def write_reader(reader, corpus_root: Path) -> dict:
    count = 0
    with db_connection() as connection:
        # Own namespace only: saved translations and project entries stay intact.
        connection.execute("DELETE FROM dictionary_entries WHERE entry_key LIKE 'oewn2025:%'")
        connection.execute("DELETE FROM dictionary_forms WHERE language='en'")
        batch = []
        for synset in reader.all_synsets():
            synonyms = list(dict.fromkeys(name.replace("_", " ") for name in synset.lemma_names()))
            examples = " ".join(synset.examples())
            for term in synonyms:
                entry = {
                    "key": f"oewn2025:{synset.pos()}:{synset.offset()}:{normalize_term(term)}",
                    "term": term, "language": "en",
                    "domain": synset.lexname().replace(".", " / ").replace("_", " "),
                    "meaning": synset.definition(), "example": examples,
                    "source": SOURCE, "source_url": SOURCE_URL,
                    "part_of_speech": POS_NAMES[synset.pos()],
                    "synonyms": [word for word in synonyms if normalize_term(word) != normalize_term(term)],
                }
                batch.append(entry_values(entry))
                count += 1
                if len(batch) >= 5000:
                    connection.executemany(ENTRY_SQL, batch)
                    batch.clear()
                    if count % 25000 == 0:
                        print(f"Imported {count:,} word meanings...", flush=True)
        if batch:
            connection.executemany(ENTRY_SQL, batch)
        forms = set()
        for suffix in ("noun", "verb", "adj", "adv"):
            for line in (corpus_root / f"{suffix}.exc").read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) > 1:
                    forms.update(
                        ("en", normalize_term(parts[0].replace("_", " ")),
                         normalize_term(base.replace("_", " ")))
                        for base in parts[1:]
                    )
        connection.executemany(
            "INSERT OR IGNORE INTO dictionary_forms(language,inflected,base) VALUES (?,?,?)",
            sorted(forms),
        )
        imported_count = connection.execute(
            "SELECT COUNT(*) FROM dictionary_entries WHERE source=?", (SOURCE,)
        ).fetchone()[0]
        if imported_count < 150000:
            raise RuntimeError("Incomplete dictionary import; transaction rolled back.")
        metadata = {
            "corpus_sha256": CORPUS_SHA256, "corpus_source": SOURCE,
            "corpus_url": SOURCE_URL,
            "corpus_license": "CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/",
            "corpus_meanings": str(imported_count),
        }
        connection.executemany("""
            INSERT INTO dictionary_meta(key,value) VALUES (?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, metadata.items())
        mark_dictionary_changed(connection)
        return dictionary_stats(connection)


def import_dictionary(archive_path: Path, cache: Path, force: bool = False) -> dict:
    if not archive_path.is_file():
        raise FileNotFoundError(f"Dictionary download not found: {archive_path}")
    if digest(archive_path) != CORPUS_SHA256:
        raise ValueError("Expected the original Open English Wordnet 2025 ZIP. Checksum differs.")
    init_dictionary()
    with db_connection() as connection:
        metadata = dict(connection.execute("SELECT key,value FROM dictionary_meta").fetchall())
        actual_count = connection.execute(
            "SELECT COUNT(*) FROM dictionary_entries WHERE source=?", (SOURCE,)
        ).fetchone()[0]
    if (not force and metadata.get("corpus_sha256") == CORPUS_SHA256
            and actual_count == int(metadata.get("corpus_meanings", "0")) and actual_count > 0):
        return dictionary_stats()
    support = support_data(cache)
    print("Loading the full English dictionary...", flush=True)
    with tempfile.TemporaryDirectory(prefix="idk-wordnet-") as directory:
        root = Path(directory)
        reader = load_reader(archive_path, support, root)
        return write_reader(reader, root / "oewn2025")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path,
                        default=Path.home() / "Downloads/english-wordnet-2025.zip")
    parser.add_argument("--cache", type=Path,
                        default=Path.home() / "nltk_data/idk_button")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        stats = import_dictionary(args.archive, args.cache, args.force)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Import stopped: {error}") from error
    print(f"PASS: Full dictionary ready — {stats['terms']:,} words/phrases, "
          f"{stats['meanings']:,} word meanings.")


if __name__ == "__main__":
    main()
