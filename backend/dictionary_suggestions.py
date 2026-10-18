"""Find English dictionary options in an existing result, without model calls."""
from collections import Counter
import re

import database
import dictionary_store as store
from database import db_connection

WORD = re.compile(r"[a-z]+(?:'[a-z]+)?", re.I)
STOP = frozenset("""
a an the and or but if then than so of to for from with without by at in on into onto
out up down off over under through about as is am are was were be been being do does
did doing have has had having can could will would shall should may might must not
no yes this that these those it its it's i i'm i've i'll i'd me my mine we we're our
ours you you're you've you'll you'd your yours he he's him his she she's her hers
they they're them their theirs who what which where when why how there there's
here just very really please also now before after again all any some each every
both either other such only even more most much many less few own same check checks
checking need needs needed want wants let's let make get go come say tell see look
think know don't doesn't didn't isn't aren't wasn't weren't can't won't wouldn't
couldn't shouldn't don't
""".split())
NO_SPEECH = frozenset({"[blank_audio]", "[no_speech]", "no speech detected.", "no speech detected", "[silence]"})


def _words(text):
    return WORD.findall(store.normalize_term(text))


def _content(text):
    return {word for word in _words(text) if len(word) > 2 and word not in STOP}


def _is_english(language):
    return language.strip().casefold().split("-")[0] in {"en", "eng", "english"}


def _rank_meanings(match, evidence, term):
    ignored = set(_words(term)) | set(_words(match["term"]))
    evidence = evidence - ignored
    ranked = []
    for index, meaning in enumerate(match["meanings"]):
        fields = [(meaning["domain"], 3), (meaning["meaning"], 3),
                  (meaning["example"], 1), (" ".join(meaning["synonyms"]), 2)]
        hits = set()
        score = 0
        for text, weight in fields:
            overlap = _content(text) & evidence
            hits.update(overlap)
            score += len(overlap) * weight
        ranked.append((-score, index, {**meaning, "context_words": sorted(hits)}))
    ranked.sort(key=lambda item: item[:2])
    return {**match, "total_meanings": len(ranked),
            "meanings": [item[2] for item in ranked[:8]]}


def suggest_words(source, translation, source_language="en", target_language="ko", context=""):
    result = {"basis": "none", "language": "en", "terms": []}
    if not source.strip() or not translation.strip():
        return result
    if source.strip().casefold() in NO_SPEECH or translation.strip().casefold() in NO_SPEECH:
        return result
    if _is_english(target_language):
        text = translation
        basis = "translation"
    elif _is_english(source_language):
        text = source
        basis = "source"
    else:
        return result
    result["basis"] = basis
    tokens = _words(text)
    if not tokens:
        return result
    with db_connection() as connection:
        revision = connection.execute("SELECT value FROM dictionary_meta WHERE key='revision'").fetchone()[0]
        vocabulary, word_set = store._vocabulary(str(database.DB_PATH), revision, "en")
        glossary = {row[0] for row in connection.execute(
            "SELECT DISTINCT normalized_term FROM dictionary_entries WHERE source='Project glossary' AND language='en'"
        )}
        irregular = {}
        for row in connection.execute("SELECT inflected, base FROM dictionary_forms WHERE language='en'"):
            irregular.setdefault(row[0], set()).add(row[1])
    counts = Counter(tokens)
    candidates = {}
    # Long known phrases can identify a technical expression as a single unit.
    for position in range(len(tokens)):
        for size in range(5, 1, -1):
            phrase = " ".join(tokens[position:position + size])
            if len(tokens[position:position + size]) != size or not _content(phrase):
                continue
            if phrase in word_set:
                candidates.setdefault(phrase, (1, -size, position))
                break
    unknown = []
    for position, word in enumerate(tokens):
        if len(word) < 3 or word in STOP or word in candidates:
            continue
        forms = store._base_forms(word, word_set, irregular.get(word, set()))
        if word in word_set or forms:
            project = word in glossary or bool(forms & glossary)
            candidates.setdefault(word, (0 if project else 2, -counts[word], position))
        elif len(word) >= 4 and word not in unknown:
            unknown.append(word)
    # Keep spelling suggestions bounded: unfamiliar names are not all misspellings.
    for word in unknown[:2]:
        candidates.setdefault(word, (1, 0, tokens.index(word)))
    evidence = _content(context + " " + text)
    seen = set()
    for observed in sorted(candidates, key=candidates.get):
        is_exact_or_base = observed in word_set or bool(store._base_forms(observed, word_set, irregular.get(observed, set())))
        found = store.search_dictionary(observed, limit=1 if is_exact_or_base else 3)["matches"]
        if not found or found[0]["term"].casefold() in seen:
            continue
        seen.add(found[0]["term"].casefold())
        result["terms"].append({
            "observed": observed,
            "matches": [_rank_meanings(match, evidence, observed) for match in found],
        })
        if len(result["terms"]) == 6:
            break
    return result
