"""Reviewed phrasal-verb senses for ambiguity disambiguation, not sentence translations."""
import re

# Hand-reviewed candidate senses, not model guesses. Probability between senses
# is computed separately (see sense_probability.py); this module only supplies
# the candidate list so the model is never asked to invent its own options.
PHRASES = {
    'make it': [
        {'gloss_en': 'come / be able to attend', 'ko': '오다, 참석하다'},
        {'gloss_en': 'prepare or cook it', 'ko': '그것을 만들다'},
    ],
    'pick up': [
        {'gloss_en': 'give someone a ride or collect someone', 'ko': '데리러 가다, 태우러 가다'},
        {'gloss_en': 'lift a physical object', 'ko': '집어 들다'},
    ],
    'check in': [
        {'gloss_en': 'register at a hotel, airport, or front desk', 'ko': '체크인하다, 접수하다'},
        {'gloss_en': 'briefly report your status to someone', 'ko': '상황을 보고하다, 연락하다'},
    ],
    'run into': [
        {'gloss_en': 'meet someone by chance, unexpectedly', 'ko': '우연히 마주치다'},
        {'gloss_en': 'physically collide with something', 'ko': '충돌하다, 들이박다'},
    ],
    'take it': [
        {'gloss_en': 'continue or handle the rest', 'ko': '이어서 처리하다, 맡다'},
        {'gloss_en': 'physically carry the object', 'ko': '그것을 가져가다'},
    ],
}


def find_phrase(text):
    """Return (phrase, senses) for the longest lexicon phrase found in text, or None."""
    lowered = text.lower()
    for phrase in sorted(PHRASES, key=len, reverse=True):
        if re.search(r'\b' + re.escape(phrase) + r'\b', lowered):
            return phrase, PHRASES[phrase]
    return None
