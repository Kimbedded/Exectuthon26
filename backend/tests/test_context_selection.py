import sys,io,json,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import translate_sentence as m
class SelectionTests(unittest.TestCase):
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
if __name__=='__main__':unittest.main()
