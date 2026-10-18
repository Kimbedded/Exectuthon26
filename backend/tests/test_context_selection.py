import sys,io,json,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import translate_sentence as m
class SelectionTests(unittest.TestCase):
 def test_sentence_after_a_voltage_limit_does_not_replace_its_context(self):
  result=m.select_last_sentence('Do not apply more than 5 V. Check the lead.')
  self.assertEqual(result['target'],'Check the lead.')
  self.assertEqual(result['context'],'Do not apply more than 5 V.')
 def test_unterminated_rambling_speech_is_capped_not_unbounded(self):
  words=['word'+str(i) for i in range(120)]  # no punctuation anywhere
  result=m.select_last_sentence(' '.join(words))
  self.assertEqual(result['boundary_status'],'unterminated_fragment')
  self.assertLessEqual(len(result['target']),m.MAX_UNTERMINATED_CHARS)
  self.assertTrue(result['target'])
  self.assertFalse(result['target'].startswith('word0 '))
 def test_short_unterminated_fragment_is_not_truncated(self):
  result=m.select_last_sentence('a short fragment with no punctuation')
  self.assertEqual(result['target'],'a short fragment with no punctuation')
 def test_explicit_user_selection_overrides_earlier_topic_but_retains_history(self):
  body={'translation':'바닥을 확인하세요.','literal':'바닥을 확인하세요.','explanation':'바닥 상태를 점검합니다.'}
  stream=io.BytesIO(('data: '+json.dumps({'choices':[{'delta':{'content':json.dumps(body)},'finish_reason':'stop'}]})+'\ndata: [DONE]\n').encode())
  with patch.object(m.urllib.request,'urlopen',return_value=stream) as http:
   r=m.translate('This electrical circuit needs grounding. Check the ground.',include_choices=True,context_selection='The topic is the physical floor or earth surface.')
  self.assertTrue(r['valid'])
  payload=json.loads(http.call_args.args[0].data);data=json.loads(payload['messages'][1]['content'])
  self.assertIn('physical floor',data['TERM_HINTS']['ground'])
  self.assertEqual(data['CONTEXT']['preceding_sentences'],'This electrical circuit needs grounding.')
  self.assertIn('physical floor',data['CONTEXT']['user_selected_context'])
 def test_conflicting_context_does_not_force_an_electrical_hint(self):
  body={'translation':'번역','literal':'직역','explanation':'설명'}
  stream=io.BytesIO(('data: '+json.dumps({'choices':[{'delta':{'content':json.dumps(body)},'finish_reason':'stop'}]})+'\ndata: [DONE]\n').encode())
  with patch.object(m.urllib.request,'urlopen',return_value=stream) as http:
   result=m.translate('Check the ground.',context='The electrical circuit is outside on the floor.',include_choices=True)
  self.assertTrue(result['valid'])
  sent=json.loads(http.call_args.args[0].data)
  self.assertEqual(json.loads(sent['messages'][1]['content'])['TERM_HINTS'],{})
if __name__=='__main__':unittest.main()
