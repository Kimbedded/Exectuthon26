import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'live_ui'))
from rolling_context import RollingContext
class RollingTests(unittest.TestCase):
 def test_thirty_second_window_and_exact_frozen_bytes(self):
  c=RollingContext(rate=10,seconds=30)
  c.append(b'a'*400);c.append(b'b'*400)
  metadata=c.freeze();frozen=c.pending.get_nowait()
  self.assertEqual((metadata['window_start_ms'],metadata['window_end_ms']),(10000,40000))
  self.assertEqual(frozen['pcm'],b'a'*200+b'b'*400)
  c.append(b'c'*200)
  self.assertEqual(frozen['pcm'],b'a'*200+b'b'*400)
  self.assertEqual(c.snapshot()['pcm'],b'b'*400+b'c'*200)
 def test_short_warmup_uses_available_audio_without_waiting(self):
  c=RollingContext(rate=10);c.append(b'a'*40)
  self.assertEqual(c.freeze()['window_seconds'],2.)
 def test_empty_input_cannot_be_frozen(self):
  with self.assertRaises(ValueError):RollingContext().freeze()
if __name__=='__main__':unittest.main()
