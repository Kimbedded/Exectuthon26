import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'live_ui'))
from asr_uncertainty import quality
class QualityTests(unittest.TestCase):
 def test_low_margin_is_review_not_a_confidence_probability(self):
  r=quality('hit the books',-.2,.1,False)
  self.assertEqual(r['status'],'needs_review');self.assertIsNone(r['confidence']);self.assertFalse(r['confidence_calibrated'])
 def test_caption_is_not_an_alternative_spoken_sentence(self):
  self.assertEqual(quality('(upbeat music)',-.1,2.,False)['status'],'non_speech')
 def test_blank_audio_and_inaudible_markers(self):
  for text in ['[BLANK_AUDIO]', ' [blank_audio] ', '[INAUDIBLE]']:
   self.assertEqual(quality(text,-.1,2.,False)['status'],'non_speech')
 def test_spoken_blank_word_is_not_a_marker(self):
  self.assertEqual(quality('The audio is blank.',-.1,2.,False)['status'],'normal')
 def test_clear_text_without_flags(self):
  self.assertEqual(quality('hello',-.1,2.,False)['status'],'normal')
 def test_repetition_loop_is_treated_as_non_speech_not_translated(self):
  # A decoder stuck repeating a word ("yeah yeah yeah...") makes the
  # translation model mirror the loop until it 502s on max_tokens; block it
  # the same as blank audio instead of forwarding it for translation.
  r=quality(' '.join(['yeah']*60),-.1,2.,False)
  self.assertEqual(r['status'],'non_speech')
  self.assertIn('repetitive_output',r['reasons'])
 def test_clipping_and_truncation_are_recorded(self):
  r=quality('hello',-.1,2.,True,.1)
  self.assertIn('audio_clipping',r['reasons']);self.assertIn('decoder_limit',r['reasons'])
if __name__=='__main__':unittest.main()
