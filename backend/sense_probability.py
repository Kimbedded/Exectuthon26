"""Self-consistency sense-probability estimation for ambiguous phrases.

A 2B on-device model cannot reliably self-report a confidence percentage: asked
directly, it either commits to one sense or invents an unfounded number. Instead
we resample the model's own single-letter choice at temperature=1.0 and use the
response frequency as the probability, averaging forward and reversed option
order to cancel the model's tendency to prefer whichever option comes first.
"""
import json
import os
import urllib.request
from collections import Counter

from model_transport import open_model_request

# Duplicated from translate_sentence.MODEL on purpose: importing that module here
# would create an import cycle, since translate_sentence imports this module.
MODEL = 'unsloth/Qwen3.5-2B-GGUF:Q4_0'
LETTERS = 'ABCD'
DEFAULT_SAMPLES = 8
DEFAULT_THRESHOLD = 0.85


def _ask_once(prompt, endpoint):
    payload = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 1.0, 'enable_think': False,
        'max_tokens': 1, 'stream': False,
    }
    request = urllib.request.Request(
        endpoint.rstrip('/') + '/chat/completions',
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'},
    )
    with open_model_request(lambda: request, timeout=30, opener=urllib.request.urlopen) as response:
        raw = json.load(response)
    return raw['choices'][0]['message']['content'].strip().upper()


def _choice_probs(context, target, phrase, senses, *, samples, endpoint):
    letters = LETTERS[:len(senses)]
    options = '\n'.join(f'{letter}) {sense["gloss_en"]}' for letter, sense in zip(letters, senses))
    prompt = (f'Conversation: {context}\nSentence: {target}\n'
              f'In this sentence, what does "{phrase}" mean?\n{options}\n'
              'Answer with one letter only.')
    counts = Counter()
    for _ in range(samples):
        token = _ask_once(prompt, endpoint)
        if token and token[0] in letters:
            counts[token[0]] += 1
    total = sum(counts.values())
    if not total:
        return [1 / len(senses)] * len(senses)
    return [counts.get(letter, 0) / total for letter in letters]


def rank_senses(context, target, phrase, senses, *, samples=DEFAULT_SAMPLES, threshold=DEFAULT_THRESHOLD, endpoint=None):
    """Rank candidate senses of an ambiguous phrase by sampled model preference.

    Returns {'ranked': [(sense, probability), ...] sorted descending,
             'auto_resolved': top probability >= threshold}.
    """
    endpoint = endpoint or os.environ.get('IDK_MODEL_ENDPOINT', 'http://127.0.0.1:18181/v1')
    forward = _choice_probs(context, target, phrase, senses, samples=samples, endpoint=endpoint)
    reversed_probs = _choice_probs(context, target, phrase, senses[::-1], samples=samples, endpoint=endpoint)[::-1]
    probabilities = [(f + r) / 2 for f, r in zip(forward, reversed_probs)]
    ranked = sorted(zip(senses, probabilities), key=lambda pair: -pair[1])
    return {'ranked': ranked, 'auto_resolved': ranked[0][1] >= threshold}
