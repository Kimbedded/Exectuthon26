"""Small, reviewed ambiguity rules. These choose meanings, never translations.

Source-level constraints take priority over older conversation. Weak clues such
as dinner/later/tonight alone deliberately do not resolve 'make it'.
"""
import re

from phrasal_lexicon import find_phrase


def phrase_decision(source, context=''):
    hit = find_phrase(source)
    if not hit:
        return None
    phrase, senses = hit
    if phrase != 'make it':
        # Other phrases retain the general model resolver instead of always
        # interrupting clearly worded requests such as 'pick up the suitcase'.
        return None
    evidence = None
    chosen = None
    if phrase == 'make it':
        # A time attached to this phrase is attendance; an ingredient or cooking
        # constraint is preparation. Conflicting constraints need a person.
        patterns = [
            r'\bmake it\s+(?:at\s+\d{1,2}(?::\d{2})?\b|by\s+\d{1,2}(?::\d{2})?\b|to\s+(?:the\s+)?(?:dinner|party|meeting|event)\b)',
            r'\bmake it\s+(?:(?:with|without)\s+(?:any\s+|the\s+)?(?:salt|sugar|milk|butter|oil|nuts|peanuts|gluten)\b|(?:less|more)\s+(?:salty|spicy|sweet)\b|(?:vegan|vegetarian|gluten.free)\b)',
        ]
        matches = [re.search(pattern, source, re.I) for pattern in patterns]
        if sum(match is not None for match in matches) == 1:
            chosen = next(i for i, match in enumerate(matches) if match)
            evidence = matches[chosen].group()
        else:
            # Explicit earlier commitments are useful; generic meal words are not.
            context_patterns = [
                r'\b(?:invited you|join us|attend the|arrive at|your attendance)\b',
                r'\b(?:you(?:\s+will|\'ll| are going to) cook|you are cooking|your recipe|prepare (?:the|our) (?:meal|dinner))\b',
            ]
            earlier = [re.search(pattern, context, re.I) for pattern in context_patterns]
            if not any(matches) and sum(match is not None for match in earlier) == 1:
                chosen = next(i for i, match in enumerate(earlier) if match)
                evidence = earlier[chosen].group()
    options = [sense['gloss_en'].capitalize() for sense in senses]
    common = {
        'phrase': phrase,
        'meaning_options': options,
        'option_contexts': ['Interpret "' + phrase + '" as: ' + sense['gloss_en'] for sense in senses],
        'decision_method': 'reviewed_phrase_senses',
    }
    if chosen is not None:
        return {**common, 'needs_clarification': False, 'topic': common['option_contexts'][chosen],
                'evidence': evidence, 'question': None, 'options': [], 'selected_option': chosen}
    return {**common, 'needs_clarification': True, 'topic': None, 'evidence': None,
            'question': 'When you say "' + phrase + '", which meaning do you intend?', 'options': options}
