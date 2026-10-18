import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
import idk_client
import main
import translate_sentence
import model_transport
from fastapi.testclient import TestClient


RESULT = {
    'elapsed_ms': None, 'source_language': 'en', 'target_language': 'ko',
    'source': "You're grounded.", 'translation_confidence': None,
    'translation': '너는 외출 금지야.', 'alternatives': [],
}


class InterpretAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(database, 'DB_PATH', Path(self.temp.name) / 'test.db')
        self.db_patch.start()
        self.client = TestClient(main.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.db_patch.stop()
        self.temp.cleanup()

    def test_existing_three_fields_and_optional_metadata(self):
        result = dict(RESULT, elapsed_ms=32000)
        with patch.object(main, 'interpret_ai', return_value=result) as ai:
            response = self.client.post('/interpret', json={
                'transcript': "You're grounded.", 'context': 'A parent is speaking.',
                'target_language': 'Korean', 'source_language': 'en', 'elapsed_ms': 32000,
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result)
        ai.assert_called_once_with(transcript="You're grounded.", context='A parent is speaking.',
            target_language='Korean', source_language='en', elapsed_ms=32000)

    def test_existing_default_target_is_preserved(self):
        with patch.object(main, 'interpret_ai', return_value=dict(RESULT, target_language='es')) as ai:
            response = self.client.post('/interpret', json={'transcript': "You're grounded."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ai.call_args.kwargs['target_language'], 'Spanish')
        self.assertIsNone(ai.call_args.kwargs['elapsed_ms'])

    def test_invalid_request_does_not_call_model(self):
        with patch.object(main, 'interpret_ai') as ai:
            for payload in ({'transcript': ''}, {'transcript': 'Hello', 'elapsed_ms': -1},
                            {'transcript': 'Hello', 'elapsed_ms': True}):
                self.assertEqual(self.client.post('/interpret', json=payload).status_code, 422)
            ai.assert_not_called()

    def test_upstream_and_input_failures_have_distinct_http_status(self):
        for failure, expected in ((URLError('refused'), 502), (RuntimeError('invalid model JSON'), 502),
                                  (json.JSONDecodeError('bad event', '!', 0), 502),
                                  (TimeoutError('slow'), 504), (ValueError('invalid language'), 422)):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(main, 'interpret_ai', side_effect=failure):
                    response = self.client.post('/interpret', json={'transcript': 'Hello'})
                self.assertEqual(response.status_code, expected)

    def test_expression_storage_still_round_trips(self):
        payload = {'expression': 'give it a shot', 'meaning': 'try it',
            'translation': '한번 해보다', 'example': "Let's give it a shot.", 'target_language': 'ko'}
        saved = self.client.post('/expressions', json=payload)
        self.assertEqual(saved.status_code, 201)
        listed = self.client.get('/expressions').json()
        self.assertEqual(listed[0]['id'], saved.json()['id'])
        self.assertEqual(listed[0]['translation'], payload['translation'])


class ModelClientTests(unittest.TestCase):
    def test_transient_gateway_is_retried(self):
        response = io.BytesIO(b"ok")
        calls = iter([response])
        failed = True

        def opener(request, timeout):
            nonlocal failed
            if failed:
                failed = False
                raise HTTPError("http://model.test", 502, "Bad Gateway", {}, io.BytesIO())
            return next(calls)

        with patch.object(model_transport.time, 'sleep') as pause:
            result = model_transport.open_model_request(
                lambda: object(), opener=opener
            )
        self.assertIs(result, response)
        pause.assert_called_once_with(0.25)

    def test_name_normalization_and_environment_endpoint(self):
        with patch.dict('os.environ', {'IDK_MODEL_ENDPOINT': 'http://model.test:18181/v1'}):
            with patch.object(idk_client, 'translate', return_value={'valid': True, 'result': RESULT}) as call:
                self.assertEqual(idk_client.interpret("You're grounded.", 'A parent.', 'Korean'), RESULT)
        self.assertEqual(call.call_args.kwargs['target_language'], 'ko')
        self.assertEqual(call.call_args.kwargs['source_language'], 'en')
        self.assertEqual(call.call_args.kwargs['endpoint'], 'http://model.test:18181/v1')

    def test_last_sentence_context_and_stream_assembly(self):
        body = json.dumps({'translation': '너는 외출 금지야.', 'alternatives': []}, ensure_ascii=False)
        events = [json.dumps({'choices': [{'delta': {'content': body[:12]}}]}),
                  json.dumps({'choices': [{'delta': {'content': body[12:]}, 'finish_reason': 'stop'}]})]
        stream = io.BytesIO(('\n'.join('data: ' + x for x in events) + '\ndata: [DONE]\n').encode())
        with patch.object(translate_sentence.urllib.request, 'urlopen', return_value=stream) as request:
            result = translate_sentence.translate("We need to talk. You're grounded.",
                context='A parent is punishing a teenager.', elapsed_ms=32000)
        self.assertTrue(result['valid'])
        self.assertEqual(result['result'], dict(RESULT, elapsed_ms=32000))
        sent = json.loads(request.call_args.args[0].data)
        data = json.loads(sent['messages'][1]['content'])
        self.assertEqual(data['SOURCE'], "You're grounded.")
        self.assertEqual(data['CONTEXT']['preceding_sentences'], 'We need to talk.')
        self.assertEqual(data['CONTEXT']['previous_turns'], 'A parent is punishing a teenager.')

    def test_malformed_model_reply_is_not_a_success(self):
        with patch.object(idk_client, 'translate', return_value={'valid': False, 'errors': ['Invalid JSON']}):
            with self.assertRaises(RuntimeError):
                idk_client.interpret('Hello')


if __name__ == '__main__':
    unittest.main()

class EnrichedContractTests(unittest.TestCase):
    def reply(self, body):
        event={'choices':[{'delta':{'content':json.dumps(body,ensure_ascii=False)},'finish_reason':'stop'}]}
        return io.BytesIO(('data: '+json.dumps(event)+'\ndata: [DONE]\n').encode())

    def test_enriched_route_preserves_expressions(self):
        result=dict(RESULT,expressions=[{'type':'word','text':'grounded','meaning':'외출 금지된'}])
        with TestClient(main.app) as client, patch.object(main,'interpret_ai',return_value=result) as ai:
            response=client.post('/interpret/enriched',json={'transcript':"You're grounded.",'target_language':'ko'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json(),result)
        self.assertTrue(ai.call_args.kwargs['include_expressions'])

    def test_extraction_cannot_copy_a_phrase_only_from_context(self):
        body={'translation':'안녕하세요.','alternatives':[],
              'expressions':[{'type':'idiom','text':'give it a shot','meaning':'시도하다'}]}
        with patch.object(translate_sentence.urllib.request,'urlopen',return_value=self.reply(body)):
            result=translate_sentence.translate('Hello.',context='Give it a shot.',include_expressions=True)
        self.assertFalse(result['valid'])
        self.assertIn('Invalid expression item',result['errors'])

    def test_missing_expressions_is_not_silently_replaced(self):
        with patch.object(translate_sentence.urllib.request,'urlopen',return_value=self.reply({'translation':'안녕','alternatives':[]})):
            result=translate_sentence.translate('Hello.',include_expressions=True)
        self.assertFalse(result['valid'])

class TranslationWorkflowTests(unittest.TestCase):
    def test_saved_translation_preserves_entire_ai_response(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(database,'DB_PATH',Path(tmp)/'test.db'):
            with TestClient(main.app) as client:
                saved=client.post('/translations',json=RESULT)
                self.assertEqual(saved.status_code,201)
                self.assertEqual({k:saved.json()[k] for k in RESULT},RESULT)
                listed=client.get('/translations')
                self.assertEqual(listed.status_code,200)
                self.assertEqual(listed.json(),[saved.json()])

    def test_button_route_requires_three_real_answers(self):
        result=dict(RESULT,answers=[{'kind':kind,'text':text} for kind,text in
            [('translation','외출 금지야.'),('literal','너는 외출 금지 상태야.'),('explanation','벌로 밖에 나가지 못한다는 뜻이야.')]])
        with TestClient(main.app) as client, patch.object(main,'interpret_ai',return_value=result) as ai:
            response=client.post('/interpret/button',json={'transcript':"You're grounded.",'target_language':'ko'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json(),result)
        self.assertTrue(ai.call_args.kwargs['include_choices'])

    def test_missing_model_answers_is_rejected(self):
        stream=io.BytesIO(('data: '+json.dumps({'choices':[{'delta':{'content':json.dumps({'translation':'안녕','alternatives':[],'answers':[]})},'finish_reason':'stop'}]})+'\ndata: [DONE]\n').encode())
        with patch.object(translate_sentence.urllib.request,'urlopen',return_value=stream):
            response=translate_sentence.translate('Hello.',include_choices=True)
        self.assertFalse(response['valid'])
        self.assertIsNone(response['result'])

class ButtonModelSchemaTests(unittest.TestCase):
    def test_three_string_fields_are_mapped_without_rewriting_text(self):
        body={'translation':'이 버튼을 테스트하고 있어요.','literal':'이 버튼을 시험해 보고 있습니다.','explanation':'사용 중인 버튼의 동작을 확인한다는 뜻입니다.'}
        stream=io.BytesIO(('data: '+json.dumps({'choices':[{'delta':{'content':json.dumps(body)},'finish_reason':'stop'}]})+'\ndata: [DONE]\n').encode())
        with patch.object(translate_sentence.urllib.request,'urlopen',return_value=stream):
            response=translate_sentence.translate("I'm trying to test this button and also",include_choices=True)
        self.assertTrue(response['valid'])
        self.assertEqual([x['text'] for x in response['result']['answers']],[body['translation'],body['literal'],body['explanation']])
