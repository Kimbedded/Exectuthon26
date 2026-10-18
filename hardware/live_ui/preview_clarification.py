#!/usr/bin/env python3
"""Interactive UI examples without a microphone, model, database or Arduino.

All translations and vote shares in this preview are explicitly sample data.
Actual dashboard_server.py uses live /context/resolve and /interpret/button.
"""
import argparse
import json
from pathlib import Path
import sys
from http.server import ThreadingHTTPServer

import dashboard_server as dashboard

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from context_catalog import catalog_decision
from phrase_context import phrase_decision

EXAMPLES = [
    ('Dinner · ambiguous', "Let's have dinner later, can you make it?", ['나중에 저녁 같이 먹자. 올 수 있어?', '나중에 저녁 먹자. 만들어 줄 수 있어?']),
    ('Dinner · at 8', "Let's have dinner later, can you make it at 8?", ['나중에 저녁 같이 먹자. 8시에 올 수 있어?', '나중에 저녁 먹자. 8시에 만들어 줄 수 있어?']),
    ('Dinner · without salt', "Let's have dinner later, can you make it without salt?", ['나중에 저녁 같이 먹자. 소금을 가져오지 않고 올 수 있어?', '나중에 저녁 먹자. 소금 없이 만들어 줄 수 있어?']),
    ('Ground · ambiguous', 'Check the ground.', ['접지를 확인하세요.', '바닥을 확인하세요.']),
    ('Ground · electrical', 'Check the ground rail.', ['접지 레일을 확인하세요.', '지면의 레일을 확인하세요.']),
    ('Ground · physical', 'Check on the ground beneath your feet.', ['발밑의 접지를 확인하세요.', '발밑의 땅을 확인하세요.']),
]

SAMPLE_WORDS = {
    'dinner': [
        ('make it', 'To arrive or attend; in another context, to prepare or create something.'),
        ('attend', 'To be present at an event or gathering.'),
        ('prepare', 'To make something ready, such as a meal.'),
        ('arrive', 'To reach a place.'),
    ],
    'ground': [
        ('ground', 'An electrical reference connection, or the physical surface of the earth.'),
        ('grounding', 'Connecting an electrical system to its ground reference.'),
        ('floor', 'The surface you stand or walk on inside a building.'),
        ('earth', 'The land or soil beneath you.'),
    ],
}


def sample_suggestions():
    words=SAMPLE_WORDS['dinner' if dashboard.STATE['preview_example']<3 else 'ground']
    return {'basis':'source','terms':[
        {'observed':word,'matches':[{'term':word,'match_type':'exact','spelling_similarity':1.0,
          'total_meanings':1,'meanings':[{'entry_key':'preview-'+word,'meaning':definition,
            'domain':'Example meaning','synonyms':[],'context_words':[],'example':None,
            'part_of_speech':'','source':'Sample dictionary entry'}]}]}
        for word,definition in words]}


def show_example(index):
    label, source, translations = EXAMPLES[index]
    decision = phrase_decision(source) or catalog_decision(source, '')
    # An unavailable estimate is intentional: UI previews never invent votes.
    decision['likelihood'] = {'method': 'unavailable', 'shares': [None, None], 'valid_samples': 0, 'calibrated': False}
    decision['source'] = source
    dashboard.STATE.update(
        status='preview', stage='clarifying' if decision['needs_clarification'] else 'ready',
        preview_mode=True, preview_example=index, preview_examples=[item[0] for item in EXAMPLES],
        model_status='disconnected', chat_mode=None, chat_id='preview',
        snapshot_id='preview-'+str(index), generation=dashboard.STATE['generation']+1,
        event={'transcript': source, 'model_context_text': source}, answers=[], selected=0,
        words=[], pending_context=None, context_decision=decision, error=None,
        live={'transcript': source, 'revision': index, 'stream_id': 'preview-'+str(index)},
    )
    if decision['needs_clarification']:
        dashboard.STATE['pending_context']={**decision,'snapshot_id':dashboard.STATE['snapshot_id']}
    else:
        translate_example(decision.get('selected_option',0))


def translate_example(index):
    state=dashboard.STATE
    _, source, translations=EXAMPLES[state['preview_example']]
    decision=state.get('pending_context') or state['context_decision']
    options=decision.get('options') or decision.get('meaning_options')
    selected=options[index] if decision.get('needs_clarification') else None
    translation=translations[index] if len(translations)>1 else translations[0]
    result={'elapsed_ms':None,'source_language':'en','target_language':'ko','source':source,
            'translation':translation,'translation_confidence':None,'alternatives':[],
            'answers':[{'kind':'translation','text':translation}]}
    state['event'].update(translation=result, selected_context=selected,
        clarification_options={**decision,'options':options})
    state.update(stage='ready', answers=result['answers'], pending_context=None,
        context_decision={**decision,'needs_clarification':False,'options':[],'topic':selected or decision.get('topic')})


class PreviewHandler(dashboard.Handler):
    def do_GET(self):
        if self.path=='/api/translations' or self.path=='/api/words':self.reply(200,[]);return
        if self.path.startswith('/api/dictionary/stats'):
            self.reply(200,{'terms':0,'meanings':0,'full_dictionary_loaded':False});return
        if self.path.startswith('/api/dictionary/search'):
            self.reply(200,{'query':'','matches':[]});return
        super().do_GET()

    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            expected={'http://'+self.headers.get('Host','')}
            if origin and origin not in expected:raise ValueError('Invalid origin')
            size=int(self.headers.get('Content-Length','0'))
            if not 0 <= size <= 65536:raise ValueError('Request too large')
            data=json.loads(self.rfile.read(size) or b'{}')
            with dashboard.LOCK:
                if self.path=='/api/preview-example':
                    index=data.get('index')
                    if type(index) is not int or not 0<=index<len(EXAMPLES):raise ValueError('Invalid example')
                    show_example(index)
                elif self.path=='/api/context':
                    pending=dashboard.STATE.get('pending_context')
                    if not pending or data.get('snapshot_id')!=pending['snapshot_id']:raise ValueError('Stale example')
                    index=data.get('index')
                    if type(index) is not int or index not in (0,1):raise ValueError('Invalid choice')
                    translate_example(index)
                elif self.path=='/api/context-reopen':dashboard.reopen_context(data.get('snapshot_id'))
                elif self.path=='/api/new-chat':show_example(0)
                elif self.path=='/api/dictionary/suggestions':self.reply(200,sample_suggestions());return
                else:raise ValueError('Example preview only. This control needs the live device.')
            self.reply(200,{'ok':True})
        except (ValueError,TypeError,KeyError) as error:self.reply(400,{'error':str(error)})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8010)
    args=parser.parse_args()
    show_example(0)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),PreviewHandler)
    print(f'UI example preview: http://127.0.0.1:{args.port}',flush=True)
    print('Sample translations only. No board, model, microphone, or database is used. Control+C to stop.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        dashboard.CLOSING=True
        with dashboard.LIVE_CHANGED:dashboard.LIVE_CHANGED.notify_all()
        server.server_close()


if __name__=='__main__':main()
