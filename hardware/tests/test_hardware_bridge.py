import sys,subprocess,json,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'live_ui'))
from hardware_bridge import HardwareBridge
class HardwareBridgeTests(unittest.TestCase):
    def test_negative_selection_is_a_positional_rpc_argument(self):
        h=HardwareBridge('3220953353',lambda _:None,lambda _:None)
        result=subprocess.CompletedProcess([],0,stdout='Got RPC response: "{\\"ok\\":true}"\n',stderr='')
        with patch('hardware_bridge.subprocess.run',return_value=result) as run:
            self.assertEqual(h.rpc('idk.set',0,-1,0),{'ok':True})
        self.assertEqual(run.call_args.args[0][-1],'arduino-router-cli -- idk.set 0 -1 0')
if __name__=='__main__':unittest.main()
