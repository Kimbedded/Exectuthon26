"""Adapter for Satyam's transcript/context/target_language request. Python stdlib only."""
import argparse
import json
import os
from pathlib import Path
import re
from threading import Lock
from translate_sentence import translate

# One shared board model session: serialize calls within this backend process.
_INFERENCE_LOCK = Lock()

LANGUAGE_NAMES={'korean':'ko','english':'en','spanish':'es','japanese':'ja','chinese':'zh','french':'fr','german':'de','arabic':'ar','hindi':'hi','한국어':'ko','영어':'en'}

def language_code(value):
    value=value.strip()
    code=LANGUAGE_NAMES.get(value.casefold(),value)
    if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]+)*',code):
        raise ValueError('Use a language code such as ko/en/es; this adapter maps only the listed language names')
    return code

def interpret(transcript,context='',target_language='ko',*,source_language='en',elapsed_ms=None,endpoint=None):
    source_language = language_code(source_language)
    target_language = language_code(target_language)
    with _INFERENCE_LOCK:
        response = translate(
            transcript,
            endpoint=endpoint or os.environ.get('IDK_MODEL_ENDPOINT', 'http://127.0.0.1:18181/v1'),
            source_language=source_language, target_language=target_language,
            elapsed_ms=elapsed_ms, context=context,
        )
    if not response['valid']:
        raise RuntimeError('Invalid AI response: '+('; '.join(response['errors'])))
    return response['result']

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request-json',type=Path,required=True);parser.add_argument('--output',type=Path)
    args=parser.parse_args();request=json.loads(args.request_json.read_text())
    result=interpret(**request)
    if args.output:args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
