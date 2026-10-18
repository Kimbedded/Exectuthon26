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

    def test_green_led_uses_independent_rpc(self):
        h=HardwareBridge('3220953353',lambda _:None,lambda _:None)
        result=subprocess.CompletedProcess([],0,stdout='Got RPC response: "{\\"ok\\":true}"\n',stderr='')
        with patch('hardware_bridge.subprocess.run',return_value=result) as run:
            h.set_green_led(True)
            self.assertTrue(h.green_led)
            self.assertEqual(h.rpc('idk.green',1),{'ok':True})
        self.assertEqual(run.call_args.args[0][-1],'arduino-router-cli -- idk.green 1')

    def test_led_ack_printer_panic_is_not_treated_as_a_failed_command(self):
        h=HardwareBridge('3220953353',lambda _:None,lambda _:None)
        stdout="Sending request for method 'idk.led', with parameters: [\n  0\n]\nGot RPC error: "
        stderr="panic: unsupported type: int8\n\ngoroutine 1 [running]:\nmain.encode(...)\n"
        result=subprocess.CompletedProcess([],2,stdout=stdout,stderr=stderr)
        with patch('hardware_bridge.subprocess.run',return_value=result):
            self.assertIsNone(h.rpc('idk.led',0))

    def test_other_cli_failures_still_raise(self):
        h=HardwareBridge('3220953353',lambda _:None,lambda _:None)
        result=subprocess.CompletedProcess([],1,stdout='',stderr='adb: device offline')
        with patch('hardware_bridge.subprocess.run',return_value=result):
            with self.assertRaises(RuntimeError):
                h.rpc('idk.led',0)

    def test_close_clears_both_leds_and_display(self):
        h=HardwareBridge('3220953353',lambda _:None,lambda _:None)
        h.thread=unittest.mock.Mock()
        calls=[]
        h.rpc=lambda method,*args:calls.append((method,args))
        h.close()
        self.assertEqual(calls,[('idk.led',(0,)),('idk.green',(0,)),('idk.set',(0,0,0))])
if __name__=='__main__':unittest.main()
