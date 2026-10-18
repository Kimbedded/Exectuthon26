import importlib.util,io,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]/'live_ui';sys.path.insert(0,str(root))
spec=importlib.util.spec_from_file_location('dashboard',root/'dashboard_server.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
class BlankTests(unittest.TestCase):
 def test_blank_clears_stale_translation_and_rejects_save(self):
  event={'transcript':'[BLANK_AUDIO]','translation':{'translation':'stale','answers':[{'text':'stale'}]}}
  proc=type('Proc',(),{'stdout':io.StringIO('EVENT '+json.dumps(event)+'\n'),'wait':lambda self:0})()
  d.STATE['answers']=[{'text':'old answer'}];d.CLOSING=True
  with patch.object(Path,'write_text'),patch.object(d,'display'):
   d.consume(proc)
  self.assertEqual(d.STATE['event']['message'],'No speech detected.')
  self.assertNotIn('translation',d.STATE['event']);self.assertEqual(d.STATE['answers'],[])
  with patch.object(d.urllib.request,'urlopen') as http:
   with self.assertRaisesRegex(ValueError,'No speech detected'):d.save_current_translation()
   http.assert_not_called()
if __name__=='__main__': unittest.main()
