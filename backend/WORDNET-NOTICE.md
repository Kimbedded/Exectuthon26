# Dictionary data and attribution

The broad English dictionary uses Open English Wordnet 2025, developed by the
Open English Wordnet Community and derived from Princeton WordNet.

- Source: https://en-word.net/downloads
- Release: Open English Wordnet 2025, December 31, 2025
- License: Creative Commons Attribution 4.0 International
- License link: https://creativecommons.org/licenses/by/4.0/
- Download: https://en-word.net/downloads/english-wordnet-2025.zip
- SHA-256: 38b16326159f51853626b7d24a44c453fa88ab33f06fce5ec8fc5996d1c2be93

The data is imported into SQLite. Underscores in word forms become spaces,
lookup keys are normalized for Unicode and case, and entries sharing a lookup
form are grouped. Meanings, examples and synonyms come from the source. This
is a broad lexical database, not a claim to contain every English word, name,
or specialist term.

The reader uses Princeton WordNet 3.0 support data from the official NLTK data
repository. Its license is included in wordnet-licenses/princeton-wordnet-3.0.txt.
NLTK is installed separately under its own license. Source archives are needed
once during setup; dictionary search is fully local afterward.

The separate project glossary in dictionary_seed.json contains short definitions
and examples for the team's ten technical demonstration words. It is labeled
separately and retained alongside the broader dictionary.

## Setup

Install dictionary-requirements.txt in the existing project environment,
download the release ZIP into Downloads, then run import_dictionary.py.
The import adds dictionary tables to idk_button.db and preserves saved
expressions and translations. Run the import before a live demo. Downloaded
archives and generated databases should not be committed to Git.

Suggestions are based on spelling and known word forms. The spelling_similarity
value is not a probability or translation-confidence score. These are English
definitions, not Korean translations. Passing a selected meaning to the
interpreter is a separate integration.
