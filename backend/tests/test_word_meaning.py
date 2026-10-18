import unittest,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import word_meaning as w
class MeaningTests(unittest.TestCase):
 def test_same_word_changes_sense_with_evidence_and_does_not_guess(self):
  electrical=w.resolve_word('Check the ground.',2,'This circuit needs grounding.')
  casual=w.resolve_word('Check the ground.',2,'I dropped my keys on the floor.')
  self.assertEqual(electrical['meaning'],'접지');self.assertEqual(casual['meaning'],'바닥 / 땅')
  self.assertIsNone(w.resolve_word('Check the ground.',2)['meaning'])
  self.assertIsNone(w.resolve_word('Check the ground.',2,'Circuit and floor')['meaning'])
 def test_nut_context_excludes_food_and_unknown_stays_unsaveable(self):
  r=w.resolve_word('What Nut am I',1,'A threaded fastener for a bolt.')
  self.assertEqual(r['meaning'],'너트');self.assertNotIn('땅콩',r['meaning'])
  self.assertEqual(w.resolve_word('What Nut am I',1)['status'],'unresolved')
 def test_confirmed_context_takes_priority(self):
  r=w.resolve_word('Check the ground.',2,'Circuit. The user explicitly selected this context: 바닥이나 땅')
  self.assertEqual(r['meaning'],'바닥 / 땅')
 def test_word_boundaries_keep_contractions_and_repeated_occurrences(self):
  self.assertEqual([t['word'] for t in w.words("I don't know. I know.")],['I',"don't",'know','I','know'])
  with self.assertRaises(ValueError):w.resolve_word('Hello',2)
if __name__=='__main__':unittest.main()
