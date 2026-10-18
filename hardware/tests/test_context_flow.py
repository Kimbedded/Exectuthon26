import sys,unittest,importlib.util,io,json
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]/'live_ui';sys.path.insert(0,str(root))
spec=importlib.util.spec_from_file_location('context_dashboard',root/'dashboard_server.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
class InlineThread:
 def __init__(self,target,**kwargs):self.target=target
 def start(self):self.target()
class ContextFlowTests(unittest.TestCase):
 def setUp(self):
  d.CLOSING=False;d.STATE.update(chat_mode='Professional',chat_messages=[],session=1,generation=0,snapshot_id='1:1',stage='recording',event=None,answers=[],pending_context=None,source_language='en',target_language='ko',selected=0)
  self.stage=patch.object(d,'stage',side_effect=lambda s:d.STATE.update(stage=s));self.stage.start()
  self.thread=patch.object(d.threading,'Thread',InlineThread);self.thread.start()
 def tearDown(self):self.thread.stop();self.stage.stop()
 def test_no_translation_before_choice_and_live_does_not_replace_snapshot(self):
  row={'transcript':'Check the ground.','status':'transcribed','elapsed_ms':30000}
  decision={'needs_clarification':True,'topic':None,'evidence':None,'question':'어떤 문맥인가요?','options':['전기 회로','바닥'],'source':row['transcript']}
  result={'translation':'접지를 확인하세요.','answers':[{'kind':'translation','text':'접지를 확인하세요.'}]}
  with patch.object(d,'schedule_word'), patch.object(d,'api_request',side_effect=[decision,result]) as api:
   with d.LOCK:d.process_snapshot(row)
   self.assertEqual(api.call_count,1);self.assertEqual(d.STATE['stage'],'clarifying');self.assertFalse(d.STATE['answers'])
   with self.assertRaises(ValueError):d.save_current_translation()
   # A later live ASR update cannot change the question's frozen source.
   d.CLOSING=True
   proc=type('Proc',(),{'stdout':io.StringIO('LIVE '+json.dumps({'transcript':'New unrelated conversation.'})+'\n'),'wait':lambda self:0})()
   d.consume(proc);d.CLOSING=False
   self.assertEqual(d.STATE['event']['transcript'],'Check the ground.')
   with self.assertRaises(ValueError):d.choose_context(0,'old-snapshot')
   d.choose_context(0,'1:1')
   interpret_calls=[call for call in api.call_args_list if call.args[0]=='interpret/button']
   self.assertEqual(interpret_calls[-1].args[1]['transcript'],'Check the ground.')
   self.assertIn('전기 회로',interpret_calls[-1].args[1]['context'])
   self.assertEqual(d.STATE['event']['selected_context'],'전기 회로')
 def test_old_generation_cannot_replace_new_snapshot(self):
  d.STATE['generation']=4
  with patch.object(d,'api_request',return_value={'answers':[]}) as api:
   d.translate_snapshot({'transcript':'old'},{'context':'','transcript':'old'},{},1,3)
  self.assertIsNone(d.STATE['event'])
if __name__=='__main__':unittest.main()
