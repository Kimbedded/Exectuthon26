import unittest,sys,importlib.util
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]/'live_ui';sys.path.insert(0,str(root))
spec=importlib.util.spec_from_file_location('word_dashboard',root/'dashboard_server.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
class WordSelectionTests(unittest.TestCase):
 def setUp(self):
  d.CLOSING=False
  d.STATE.update(words=[{'word':w,'meaning':'뜻','status':'ready'} for w in ['What','Nut','am','I']],word_source='What Nut am I',word_context='mechanical',word_index=0,pending_context=None,stage='ready',generation=42,session=1,model_status='ready',target_language='ko',hardware={'rotations':0,'clicks':0,'holds':0,'selected':0})
 def test_rotation_crosses_firmware_three_slot_boundary_and_wraps(self):
  with patch.object(d,'schedule_word'):
   for n,expected in [(3,3),(4,0),(3,3)]:
    d.hardware_sample({'rotations':n,'clicks':0,'holds':0,'selected':0})
    self.assertEqual(d.STATE['word_index'],expected)
 def test_save_stores_word_meaning_and_example_once(self):
  d.STATE['word_index']=1
  with patch.object(d,'api_request',return_value={'id':7,'expression':'Nut','meaning':'뜻'}) as api:
   self.assertEqual(d.save_current_word(1,42)['id'],7);d.save_current_word(1,42)
   self.assertEqual(api.call_count,1)
   self.assertEqual(api.call_args.args,('expressions',{'expression':'Nut','meaning':'뜻','translation':'뜻','example':'What Nut am I','target_language':'ko'}))
 def test_loading_unresolved_and_stale_click_cannot_save(self):
  with patch.object(d,'api_request') as api:
   for status in ['waiting','loading','unresolved','error']:
    d.STATE['words'][0]['status']=status
    with self.assertRaises(ValueError):d.save_current_word()
   with self.assertRaises(ValueError):d.save_current_word(0,41)
   with self.assertRaises(ValueError):d.save_current_word(1,42)
   d.STATE['pending_context']={'options':['technical','casual']}
   with self.assertRaises(ValueError):d.save_current_word()
   api.assert_not_called()
if __name__=='__main__':unittest.main()
