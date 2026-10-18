#!/usr/bin/env python3
"""Inspect a failed live request, or compare fixed context pairs through local AI."""
import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def call(base, path, payload=None):
    request = Request(base.rstrip('/') + path,
        data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
        headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=180 if payload else 10) as response:
        return json.load(response)


def show_state(base):
    state = call(base, '/api/state')
    event = state.get('event') or {}
    translation = event.get('translation') or {}
    print(json.dumps({
        'stage': state.get('stage'), 'error': state.get('error'),
        'chat_mode': state.get('chat_mode'), 'snapshot_id': state.get('snapshot_id'),
        'frozen_transcript': event.get('transcript'),
        'context_actually_selected': event.get('model_context_text'),
        'context_decision': state.get('context_decision'),
        'pending_context': state.get('pending_context'),
        'translation_context': event.get('translation_context'),
        'source': translation.get('source'), 'translation': translation.get('translation'),
        'selected_context': event.get('selected_context'),
    }, ensure_ascii=False, indent=2))


def compare_pairs(base, target):
    cases = [
        ('Electrical', 'This electrical circuit has intermittent voltage.',
         'electrical grounding connection'),
        ('Construction', 'The foundation is settling. Inspect the soil at this construction site.',
         'soil or ground surface'),
        ('Insufficient context', '', 'ask for the intended meaning; do not translate yet'),
    ]
    for label, context, expected in cases:
        payload = {'transcript': 'Check the ground.', 'context': context,
                   'source_language': 'en', 'target_language': target}
        decision = call(base, '/context/resolve', payload)
        report = {'case': label, 'request': payload, 'expected_sense_for_human_review': expected,
                  'context_decision': decision}
        if decision.get('needs_clarification'):
            report['translation'] = None
            report['note'] = 'Stopped for clarification. No translation request was sent.'
        else:
            guidance = context + '\nSupported topic: ' + decision.get('topic', '')
            result = call(base, '/interpret/button', {**payload, 'context': guidance})
            report['result'] = result
            report['note'] = 'Actual model output. A fluent speaker must verify the intended meaning.'
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', action='store_true', help='Make local AI calls for three fixed context cases.')
    parser.add_argument('--api-base', default='http://127.0.0.1:8000')
    parser.add_argument('--dashboard-base', default='http://127.0.0.1:8010')
    parser.add_argument('--target-language', default='ko')
    args = parser.parse_args()
    try:
        if args.pairs:
            compare_pairs(args.api_base, args.target_language)
        else:
            show_state(args.dashboard_base)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise SystemExit('Could not check the local service: ' + str(error))


if __name__ == '__main__':
    main()
