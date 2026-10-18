# Automatic dictionary options from translation results

The dashboard finds words in each completed translation result and automatically displays possible spellings, multiple meanings, examples, and related words. There is **no search form**. A user chooses a detected word, then compares its dictionary options. Up to six detected words appear, with up to three spelling candidates for an unknown word and eight initial meanings per candidate. **View all meanings** loads the rest on demand.

The right-hand result card has two regions: **Similar & possible words** at the top and **Meanings of the selected word** below. Detected terms, spelling candidates, and related words are clickable in the top region. Selecting a related word loads that word’s dictionary definitions into the lower region. Duplicate exact-match buttons are hidden. On narrow screens the cards stack vertically. Existing AI answer selection remains in **Translation answer choices** under the left-hand translation, and physical knob behavior is unchanged.

The dictionary is English. English output is used when the target is English; otherwise the English source is used. Korean text is not fuzzy-matched against English words. Neither side being English produces an explanation rather than unrelated suggestions.

Related words come from dictionary synonym groups. Definition ordering uses shared words in the English sentence/recent transcript; this is lexical overlap, not semantic embeddings, a confidence estimate, or a validated word-sense model. It does not identify a uniquely correct interpretation. The translated sentence is preserved: this feature does not automatically rewrite Korean or feed a chosen sense back into Qwen.

## Data setup on each Mac

The full Open English Wordnet 2025 import tested contains **127,311 distinct searchable words/phrases and 185,106 meanings**, including 25 project glossary senses. This is a broad English lexical database, not every English word or a bilingual translation dictionary.

Using the existing project Python environment, from the repository root:

```bash
python -m pip install -r backend/dictionary-requirements.txt
curl -fL https://en-word.net/downloads/english-wordnet-2025.zip -o ~/Downloads/english-wordnet-2025.zip
python backend/import_dictionary.py
```

The importer verifies checksums and downloads a Princeton WordNet support archive once. It preserves saved translations and imports into `backend/idk_button.db`; a complete matching import is reused. After setup the dictionary needs no network, NLTK, AI model, or Arduino. Keep databases, environments, corpora, and runtime outputs out of Git. Source and license details are in `backend/WORDNET-NOTICE.md` and `backend/wordnet-licenses/`.

## API and runtime

Keep the existing FastAPI Python environment and model configuration. Its startup calls `init_dictionary()` and includes `dictionary_api.router`. Startup creates/updates the small project glossary but never downloads the full corpus.

- `POST /dictionary/suggestions`: accepts `source`, `translation`, `source_language`, `target_language`, and optional recent transcript `context`; returns detected words with possible spellings/meanings/synonyms. No model calls or database writes occur.
- `GET /dictionary/stats`: counts, corpus availability, source and license.
- `GET /dictionary/search?q=ground&limit=1&language=en`: supports the internal **View all meanings** action; no separate search UI is displayed.

Definitions expose stable `entry_key` identifiers. Avoid relying on SQLite row IDs across forced reimports. Spelling similarity is not confidence that a meaning is correct.

The dashboard on port 8010 proxies these routes to `127.0.0.1:8000` on the same Mac. Each new result triggers a bounded lookup. The existing 500ms state polling does not repeatedly search an unchanged result. Pending analysis, non-speech, missing results, and new sessions clear old options. Late responses cannot overwrite a newer result. Dictionary failures show a retry action and do not modify translation or saving.

## Satyam's preview

With the local FastAPI running, start:

```bash
python hardware/live_ui/preview_dictionary.py
```

Open `http://127.0.0.1:8010`. This preview uses a clearly labeled **static sample translation**, not recorded audio or freshly generated AI output. Word options appear automatically from that sample. The board, model pipeline and speech playback are not started. Sample saving and recording are disabled; Review saved remains available. Stop the preview with Control+C before restarting it or launching a real dashboard on the same port.

## Kim's active runtime copy

Kim's dashboard runs outside the checkout. Pulling the repository alone does not update that copy. Preserve existing microphone/no-speech fixes, speech playback fixes, Python environment, ADB serial, models, and firmware.

The active FastAPI needs `dictionary_suggestions.py`, `dictionary_api.py`, `dictionary_store.py`, `dictionary_seed.json`, and the dictionary startup/router additions in `backend/main.py`. Run the data importer against the database actually used by that process.

Place the new/updated `dictionary_proxy.py`, `dictionary.js`, and `dictionary.css` beside the **active dashboard_server.py**. Merge the automatic word-options section and its stylesheet/script references from `dashboard.html`, retaining other local fixes. The page calls `window.updateDictionarySuggestions?.(s)` after `updateStorageControls(s)` inside `refresh()`. The Save control also excludes `s.preview_mode`.

Merge these server additions, preserving the existing Origin check:

```python
from dictionary_proxy import serve_dictionary, serve_dictionary_post

# First lines of Handler.do_GET:
if serve_dictionary(self, ROOT):
    return

# In Handler.do_POST, AFTER the existing Origin validation:
if serve_dictionary_post(self):
    return
```

The installer supplied to Satyam replaces only known previous dictionary files, patches the HTML/server at checked anchors, and makes a backup outside the repository. Unknown local changes cause it to stop before writing. Do not replace Kim's newer runtime files wholesale.

Restart the actual dashboard and verify a real spoken phrase: options appear after the result, choosing a word shows alternative meanings/related words, a new result replaces them, and no speech clears them. Confirm existing Save/Review and physical controls still work. No firmware changes are needed for this feature.

## Validation

37 backend unit/API checks passed, including automatic extraction, English source/target choice, context ordering, spelling options, no-speech handling, and existing translation storage/model-client contracts. Full-corpus checks covered electrical versus construction context for `ground`, the misspelling `groud`, the financial sense of `bank`, and `flash the board`. These checks used no model calls and preserved saved translations.

A DOM harness exercised the dashboard HTTP handler and real FastAPI test transport with full SQLite data: no search form; automatic options; unchanged-result caching; all-meanings expansion; context changes; late-response protection; pending/non-speech clearing; retry; literal rendering of markup; and unchanged Save/Review. The updated layout was also checked for word controls in the upper-right region, definitions in the lower-right region, related-word clicks loading their own definitions, and the original AI answer controls retained on the left. These are functional checks, not a browser visual review or live hardware/translation-quality validation.
