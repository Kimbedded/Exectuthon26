"""Sampled model preference among supplied meanings; NOT calibrated accuracy.

A 2B on-device model cannot reliably self-report a confidence percentage: asked
directly, it either commits to one sense or invents an unfounded number. Instead
we resample the model's own single-letter choice at temperature=1.0 and use the
response frequency as a model vote share, testing both option orders to reduce
order bias. Agreement can still be confidently wrong. This is not a measured
probability that a meaning or a translation is correct.
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
# The board's single NPU model is shared with the continuous live ASR process
# (polling roughly every second). Each sample is a real round trip to that
# same model, so this stays small: samples=4 means 8 total calls (forward +
# reverse) per phrase instead of 16. Lower resolution but far less contention
# with live transcription — observed live as repeated "VLM prefix reuse
# failed" resets and request timeouts when this was 8.
DEFAULT_SAMPLES = 4
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
        if token in letters and len(token) == 1:
            counts[token] += 1
    return [counts.get(letter, 0) for letter in letters]


def rank_senses(context, target, phrase, senses, *, samples=DEFAULT_SAMPLES, threshold=DEFAULT_THRESHOLD, endpoint=None):
    """Rank candidate senses by sampled model preference, not measured truth.

    Returns {'ranked': [(sense, probability), ...] sorted descending,
             'auto_resolved': sufficient samples and top vote share >= threshold}.
    The legacy auto_resolved flag must not suppress a speaker clarification.
    """
    endpoint = endpoint or os.environ.get('IDK_MODEL_ENDPOINT', 'http://127.0.0.1:18181/v1')
    if not 2 <= len(senses) <= len(LETTERS) or type(samples) is not int or not 1 <= samples <= 32:
        raise ValueError('Expected 2–4 senses and 1–32 samples per order')
    forward = _choice_probs(context, target, phrase, senses, samples=samples, endpoint=endpoint)
    reversed_probs = _choice_probs(context, target, phrase, senses[::-1], samples=samples, endpoint=endpoint)[::-1]
    votes = [f + r for f, r in zip(forward, reversed_probs)]
    valid = sum(votes)
    # Preserve the legacy ranking shape, but mark a no-vote result unavailable;
    # callers must never display this uniform placeholder as measured 50/50.
    probabilities = [count / valid if valid else 1 / len(senses) for count in votes]
    ranked = sorted(zip(senses, probabilities), key=lambda pair: -pair[1])
    return {'ranked': ranked, 'auto_resolved': bool(valid >= samples and ranked[0][1] >= threshold),
            'votes': votes, 'valid_samples': valid, 'requested_samples': samples * 2,
            'method': 'model_vote_share', 'calibrated': False}
