"""Local dictionary lookup; no model or internet connection required."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from database import db_connection
from dictionary_store import dictionary_stats, search_dictionary
from dictionary_suggestions import suggest_words

router = APIRouter(prefix="/dictionary", tags=["Dictionary"])


class DictionaryMeaning(BaseModel):
    id: int
    entry_key: str
    domain: str
    meaning: str
    example: str
    source: str
    source_url: str
    part_of_speech: str
    synonyms: list[str]


class DictionaryMatch(BaseModel):
    term: str
    meanings: list[DictionaryMeaning]
    match_type: Literal["exact", "base_form", "prefix", "similar", "contains"]
    # Spelling similarity is not a probability of the intended meaning.
    spelling_similarity: float = Field(ge=0, le=1)


class DictionarySearch(BaseModel):
    query: str
    language: str
    matches: list[DictionaryMatch]


class DictionaryStats(BaseModel):
    terms: int
    meanings: int
    full_dictionary_loaded: bool
    source: str
    source_url: str
    license_url: str


class SuggestionRequest(BaseModel):
    source: str = Field(max_length=3000)
    translation: str = Field(max_length=3000)
    source_language: str = Field(default="en", min_length=2, max_length=20)
    target_language: str = Field(default="ko", min_length=2, max_length=20)
    context: str = Field(default="", max_length=6000)


class SuggestedMeaning(DictionaryMeaning):
    context_words: list[str]


class SuggestedMatch(DictionaryMatch):
    meanings: list[SuggestedMeaning]
    total_meanings: int


class SuggestedTerm(BaseModel):
    observed: str
    matches: list[SuggestedMatch]


class DictionarySuggestions(BaseModel):
    basis: Literal["source", "translation", "none"]
    language: str
    terms: list[SuggestedTerm]


@router.post("/suggestions", response_model=DictionarySuggestions)
def suggestions(request: SuggestionRequest):
    return suggest_words(**request.model_dump())


@router.get("/search", response_model=DictionarySearch)
def search(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=5, ge=1, le=10),
    language: str = Query(default="en", min_length=2, max_length=20),
):
    if not q.strip():
        raise HTTPException(status_code=422, detail="Enter a word or phrase.")
    try:
        return search_dictionary(q, limit=limit, language=language)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/stats", response_model=DictionaryStats)
def stats():
    with db_connection() as connection:
        counts = dictionary_stats(connection)
        metadata = dict(connection.execute("SELECT key, value FROM dictionary_meta"))
        corpus_count = connection.execute(
            "SELECT COUNT(*) FROM dictionary_entries WHERE entry_key LIKE 'oewn2025:%'"
        ).fetchone()[0]
    full = (
        corpus_count >= 150000
        and str(corpus_count) == metadata.get("corpus_meanings")
        and metadata.get("corpus_source") == "Open English Wordnet 2025"
    )
    return {
        **counts,
        "full_dictionary_loaded": full,
        "source": "Open English Wordnet 2025 + project glossary" if full else "Project glossary",
        "source_url": "https://en-word.net/downloads" if full else "",
        "license_url": "https://creativecommons.org/licenses/by/4.0/" if full else "",
    }
