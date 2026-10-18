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
 def test_broad_chat_category_does_not_turn_failed_analysis_into_translation(self):
  row={'transcript':'There is too much play.','status':'transcribed','elapsed_ms':30000}
  decision={'needs_clarification':True,'topic':None,'evidence':None,
      'question':'Which context?','options':['Technical','Everyday'],
      'decision_method':'broad_context_fallback'}
  with patch.object(d,'api_request',return_value=decision) as api:
   with d.LOCK:d.process_snapshot(row)
  self.assertEqual([call.args[0] for call in api.call_args_list],['context/resolve'])
  self.assertEqual(d.STATE['chat_mode'],'Professional')
  self.assertFalse(d.STATE['answers'])
  self.assertIsNone(d.STATE['event'].get('translation'))
  self.assertEqual(d.STATE['stage'],'error')
  self.assertIn('one more sentence',d.STATE['error'])
  with self.assertRaises(ValueError):d.save_current_translation()
 def test_completed_snapshot_context_reaches_both_resolution_and_translation(self):
  row={'transcript':'This electrical circuit has intermittent voltage. Check the ground.',
      'frozen_sentence_context':'We are inspecting soil at the construction site.'}
  decision={'needs_clarification':False,'topic':'Electrical grounding','evidence':'electrical circuit','options':[]}
  result={'source':'Check the ground.','translation':'접지를 확인하세요.','answers':[]}
  with patch.object(d,'api_request',side_effect=[decision,result,{'terms':[]}]) as api, patch.object(d,'schedule_word'):
   with d.LOCK:d.process_snapshot(row)
  for call in api.call_args_list[:2]:
   self.assertEqual(call.args[1]['transcript'],'Check the ground.')
   self.assertIn('electrical circuit',call.args[1]['context'])
   self.assertNotIn('construction',call.args[1]['context'])
  self.assertNotIn('Professional',api.call_args_list[0].args[1]['context'])
  self.assertIn('Professional',api.call_args_list[1].args[1]['context'])
 def test_vote_auto_resolved_decision_reuses_topic_as_context_selection(self):
  row={'transcript':'Dinner tonight, can you make it?','status':'transcribed','elapsed_ms':30000}
  decision={'needs_clarification':False,'source':row['transcript'],
      'topic':'Interpret "make it" as: prepare or cook it','evidence':'',
      'decision_method':'reviewed_phrase_senses_vote_resolved',
      'likelihood':{'method':'model_vote_share','shares':[.1,.9],'valid_samples':4}}
  result={'source':row['transcript'],'translation':'저녁을 만들 수 있어요?',
      'translation_confidence':0.9,'answers':[{'kind':'translation','text':'저녁을 만들 수 있어요?'}]}
  with patch.object(d,'dictionary_options',return_value=[]),patch.object(d,'schedule_word'), \
       patch.object(d,'api_request',side_effect=[decision,result]) as api:
   with d.LOCK:d.process_snapshot(row)
  interpret=[call for call in api.call_args_list if call.args[0]=='interpret/button'][0]
  self.assertEqual(interpret.args[1]['context_selection'],'Interpret "make it" as: prepare or cook it')
  self.assertEqual(d.STATE['stage'],'ready')
 def test_choice_is_forwarded_and_resolved_led_state_is_cleared(self):
  decision={'needs_clarification':True,'source':'Can you make it?','question':'Attend or cook?',
      'options':['Attend','Cook'],'option_contexts':['come / be able to attend','prepare or cook it'],
      'likelihood':{'method':'model_vote_share','shares':[.75,.25],'valid_samples':4}}
  row={'transcript':'Can you make it?'}
  result={'source':row['transcript'],'translation':'만들 수 있어요?','answers':[{'kind':'translation','text':'만들 수 있어요?'}]}
  with patch.object(d,'dictionary_options',return_value=[]),patch.object(d,'schedule_word'),patch.object(d,'api_request',side_effect=[decision,result]) as api:
   with d.LOCK:d.process_snapshot(row)
   d.choose_context(1,'1:1')
  interpret=[call for call in api.call_args_list if call.args[0]=='interpret/button'][0]
  self.assertEqual(interpret.args[1]['context_selection'],'prepare or cook it')
  self.assertFalse(d.STATE['context_decision']['needs_clarification'])
  self.assertFalse(d.intention_mismatch())
  self.assertEqual(d.STATE['event']['clarification_options']['options'],['Attend','Cook'])
  with self.assertRaises(ValueError):d.reopen_context('old-snapshot')
  d.reopen_context('1:1')
  self.assertEqual(d.STATE['stage'],'clarifying')
  self.assertNotIn('translation',d.STATE['event'])
  self.assertFalse(d.STATE['answers'])
  with self.assertRaises(ValueError):d.save_current_translation()
if __name__=='__main__':unittest.main()
