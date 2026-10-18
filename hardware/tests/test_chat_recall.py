import sys,unittest,importlib.util,copy,tempfile
from pathlib import Path
from unittest.mock import Mock,patch
root=Path(__file__).resolve().parents[1]/'live_ui';sys.path.insert(0,str(root))
from word_recall import RecallTracker
from hardware_bridge import HardwareBridge
spec=importlib.util.spec_from_file_location('chat_dashboard',root/'dashboard_server.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
class RecallTests(unittest.TestCase):
 def test_nuts_matches_nut_without_semantic_equivalence_and_dedupes_windows(self):
  r=RecallTracker();entries=[{'expression':'Nut','meaning':'너트'}]
  self.assertEqual(r.update('I go Nuts.',entries,now=0)[0]['heard'],'Nuts')
  self.assertFalse(r.update('I go Nuts.',entries,now=15))
  self.assertFalse(r.update('I go',entries,now=16))
  self.assertFalse(r.update('[BLANK_AUDIO]',entries,silent=True,now=17))
  self.assertEqual(len(r.update('I go Nuts. You go nuts.',entries,now=18)),1)
 def test_whisper_sound_captions_do_not_trigger_vocabulary(self):
  r=RecallTracker();entries=[{'expression':'audience','meaning':'청중'},{'expression':'nut','meaning':'너트'}]
  self.assertFalse(r.update('(audience member speaking in foreign language)',entries))
  self.assertEqual(r.update('I go nuts. (audience laughing)',entries)[0]['word'],'nut')
 def test_boundaries_and_new_chat(self):
  entries=[{'expression':'nut','meaning':'너트'}];r=RecallTracker()
  self.assertFalse(r.update('The internet is down.',entries))
  self.assertTrue(r.update('NUTS!',entries))
  self.assertTrue(RecallTracker().update('Nuts!',entries))
 def test_led_overlay_restores_latest_normal_display(self):
  bridge=HardwareBridge('fake',lambda x:None,lambda x:self.fail(x));sent=[];clock=[0]
  bridge.display(4,0,0)
  def sample(value):
   if len(sent)==1:bridge.display(2,0,0);clock[0]=4
   else:bridge.closed.set()
  def rpc(method,*args):
   if method=='idk.set':sent.append(args);return {}
   if method=='idk.led':return {}
   return {'firmware':'idk-button-1','state':sent[-1][0],'answer_count':sent[-1][2]}
  bridge.on_sample=sample;bridge.rpc=rpc
  with patch('hardware_bridge.time.monotonic',side_effect=lambda:clock[0]):
   bridge.flash_recall(3);bridge.run()
  self.assertEqual(sent,[(3,0,0),(2,0,0)])
class ChatTests(unittest.TestCase):
 def setUp(self):
  self.old=copy.deepcopy(d.STATE);self.old_hardware=d.HARDWARE;self.temp=tempfile.TemporaryDirectory();self.patch=patch.object(d,'ROOT',Path(self.temp.name));self.patch.start()
  d.STATE.update(chat_id='old',chat_mode='Professional',chat_messages=[{'transcript':'old topic'}],model_status='ready',status='recording',stage='ready',session=3,generation=7,live={'transcript':'old words'},frozen_sentence_context='old words',chat_archive=[],vocabulary=[{'expression':'keep','meaning':'유지'}])
 def tearDown(self):d.STATE.clear();d.STATE.update(self.old);d.HARDWARE=self.old_hardware;self.patch.stop();self.temp.cleanup()
 def test_intention_mismatch_turns_led_on_and_resolved_match_turns_it_off(self):
  hardware=Mock();d.HARDWARE=hardware
  d.STATE.update(stage='clarifying',pending_context={'kind':'context'},context_decision=None,event=None)
  d.display()
  hardware.set_red_led.assert_called_with(True)
  d.STATE.update(stage='ready',pending_context=None,context_decision={'needs_clarification':False},event={'translation':{'alternatives':[]}})
  d.display()
  hardware.set_red_led.assert_called_with(False)
 def test_error_and_reset_clear_the_red_led(self):
  hardware=Mock();d.HARDWARE=hardware
  d.STATE.update(stage='ready',event={'translation':{'alternatives':[{'context':'other'}]}},pending_context=None)
  d.stage('error')
  hardware.set_red_led.assert_called_with(False)
  hardware.reset_mock()
  d.reset_chat_state()
  hardware.set_red_led.assert_called_with(False)
 def test_hold_creates_unset_chat_and_empty_pcm_session_while_preserving_archive(self):
  with patch.object(d,'send') as send:d.new_chat()
  self.assertEqual([x.args[0]['action'] for x in send.call_args_list],['stop','start'])
  self.assertEqual(d.STATE['session'],4);self.assertIsNone(d.STATE['chat_mode']);self.assertIsNone(d.STATE['live']);self.assertFalse(d.STATE['frozen_sentence_context'])
  self.assertEqual(d.STATE['chat_archive'][0]['mode'],'Professional');self.assertEqual(d.STATE['chat_archive'][0]['messages'][0]['transcript'],'old topic')
  self.assertEqual(d.STATE['vocabulary'],[{'expression':'keep','meaning':'유지'}])
  self.assertEqual(d.STATE['answers'],[])
  self.assertIsNone(d.STATE['event']);self.assertIsNone(d.STATE['snapshot'])
  self.assertIsNone(d.STATE['pending_context']);self.assertIsNone(d.STATE['context_decision'])
  self.assertEqual(d.STATE['logs'],[])
 def test_physical_hold_routes_to_new_chat_instead_of_analysis(self):
  d.STATE['hardware']={'rotations':0,'clicks':0,'holds':0}
  with patch.object(d,'new_chat') as new,patch.object(d,'analyze') as analyze:
   d.hardware_sample({'rotations':0,'clicks':0,'holds':1})
  new.assert_called_once();analyze.assert_not_called()
 def test_unset_chat_asks_category_before_any_model_call(self):
  d.STATE['chat_mode']=None
  with patch.object(d,'api_request') as api:d.process_snapshot({'transcript':'I go nuts.'})
  api.assert_not_called();self.assertEqual(d.STATE['pending_context']['kind'],'chat_mode')
 def test_category_choice_is_kept_for_following_sentences(self):
  d.STATE.update(chat_mode=None,pending_context={'kind':'chat_mode','snapshot_id':'test'},snapshot_id='test',event={'transcript':'hello'})
  with patch.object(d,'process_snapshot') as process:d.choose_context(0,'test')
  self.assertEqual(d.STATE['chat_mode'],'Casual');process.assert_called_once()
  with patch.object(d,'send'):d.start({'language':'en','target_language':'ko'})
  self.assertEqual(d.STATE['chat_mode'],'Casual')
if __name__=='__main__':unittest.main()
