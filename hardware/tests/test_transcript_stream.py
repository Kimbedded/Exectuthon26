import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'live_ui'))
from transcript_stream import merge_partial
class StreamTests(unittest.TestCase):
 def test_known_prefix_does_not_erase_readable_tail(self):
  self.assertEqual(merge_partial('This circuit needs grounding.','This circuit'),'This circuit needs grounding.')
 def test_new_complete_word_is_shown_as_soon_as_decoder_catches_up(self):
  self.assertEqual(merge_partial('This circuit needs','This circuit needs grounding.'),'This circuit needs grounding.')
 def test_expired_front_of_window_is_removed_without_replaying(self):
  self.assertEqual(merge_partial('Old words. This circuit needs grounding.','This circuit needs'),'This circuit needs grounding.')
 def test_repeated_single_word_does_not_shift_the_window(self):
  self.assertEqual(merge_partial('I said I need help.','I'),'I said I need help.')
 def test_first_partial_is_available_without_waiting_for_full_sentence(self):
  self.assertEqual(merge_partial('','This circuit'),'This circuit')
if __name__=='__main__':unittest.main()

from transcript_stream import SentenceLedger, sentence_request
class SentenceLedgerTests(unittest.TestCase):
 def test_only_stable_complete_sentences_are_committed(self):
  ledger=SentenceLedger()
  self.assertFalse(ledger.update('This circuit needs grounding. Check the')['confirmed_sentences'])
  view=ledger.update('This circuit needs grounding. Check the ground.',end_ms=1000)
  self.assertEqual(view['confirmed_sentences'],['This circuit needs grounding.'])
  self.assertEqual(view['draft_text'],'Check the ground.')
 def test_silence_and_shorter_redecodes_do_not_clear_readable_text(self):
  ledger=SentenceLedger();ledger.update('First sentence. Next unfinished')
  before=ledger.update('First sentence. Next unfinished',end_ms=1000)['transcript']
  self.assertEqual(ledger.update('',silent=True)['transcript'],before)
  self.assertEqual(ledger.update('First sentence.',end_ms=2000)['transcript'],before)
 def test_committed_sentence_does_not_rewrite_with_a_late_asr_revision(self):
  ledger=SentenceLedger();ledger.update('We can finish today.');ledger.update('We can finish today.',end_ms=1000)
  view=ledger.update('We cannot finish today.',end_ms=2000)
  self.assertEqual(view['confirmed_sentences'],['We can finish today.'])
 def test_negation_change_is_not_local_agreement(self):
  ledger=SentenceLedger();ledger.update('We can finish today.')
  self.assertEqual(ledger.update('We cannot finish today.')['confirmed_sentences'],[])
 def test_window_expiry_does_not_remove_confirmed_history(self):
  ledger=SentenceLedger();ledger.update('First sentence.');ledger.update('First sentence.',end_ms=1000)
  ledger.update('A later sentence.',start_ms=2000,end_ms=3000)
  view=ledger.update('A later sentence.',start_ms=2000,end_ms=4000)
  self.assertEqual(view['confirmed_sentences'],['First sentence.','A later sentence.'])
 def test_model_context_uses_at_most_five_sentences_including_source(self):
  row={'transcript':'One. Two. Three. Four. Five. Six. Latest sentence.', 'frozen_sentence_context':'Older unrelated topic.'}
  request=sentence_request(row)
  self.assertEqual(request['transcript'],'Latest sentence.')
  self.assertEqual(request['context'],'Three. Four. Five. Six.')
  self.assertEqual(sentence_request(row,'time'),{'transcript':row['transcript'],'context':''})
 def test_frozen_decode_keeps_newer_context_instead_of_stale_live_topic(self):
  row={'transcript':'This electrical circuit has intermittent voltage. Check the ground.',
       'frozen_sentence_context':'We are inspecting soil at the construction site.'}
  request=sentence_request(row)
  self.assertEqual(request,{'transcript':'Check the ground.',
      'context':'This electrical circuit has intermittent voltage.'})
 def test_nearest_context_preserves_negation_and_units(self):
  request=sentence_request({'transcript':'Do not apply more than 5 V. Check the lead.',
      'frozen_sentence_context':'Apply 50 V to the old setup.'})
  self.assertEqual(request['context'],'Do not apply more than 5 V.')
 def test_sentence_context_retains_earlier_speech_after_audio_window_moves(self):
  request=sentence_request({'transcript':'What about now?','frozen_sentence_context':'Earlier topic. More detail. What about now?'})
  self.assertEqual(request['context'],'Earlier topic. More detail.')
