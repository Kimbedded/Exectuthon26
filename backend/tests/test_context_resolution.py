import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from context_resolution import validate_decision
from context_catalog import catalog_decision, broad_clarification
class ContextTests(unittest.TestCase):
 def test_two_distinct_meanings_are_required(self):
  r=validate_decision({'topic':'','evidence':'','options':['전기 접지','바닥 상태']},'Check the ground.','')
  self.assertTrue(r['needs_clarification']);self.assertEqual(len(r['options']),2)
  for options in [['접지'],['접지','접지'],['접지','바닥','운동장']]:
   with self.assertRaises(ValueError):validate_decision({'topic':'','evidence':'','options':options},'ground','')
 def test_resolved_topic_requires_quote_from_frozen_input(self):
  self.assertFalse(validate_decision({'topic':'회로 접지','evidence':'electrical circuit','options':[]},'Check the ground.','An electrical circuit.')['needs_clarification'])
  with self.assertRaises(ValueError):validate_decision({'topic':'회로 접지','evidence':'made-up evidence','options':[]},'Check the ground.','')
class CatalogTests(unittest.TestCase):
 def test_ambiguous_ground_requires_two_meaning_choices(self):
  r=catalog_decision('Check the ground.','')
  self.assertTrue(r['needs_clarification']);self.assertEqual(len(r['options']),2)
 def test_evidence_changes_the_selected_meaning(self):
  electrical=catalog_decision('Check the ground.','This electrical circuit has a problem.')
  casual=catalog_decision('Check the ground.','I dropped my keys outside.')
  self.assertFalse(electrical['needs_clarification']);self.assertFalse(casual['needs_clarification'])
  self.assertNotEqual(electrical['topic'],casual['topic'])
 def test_conflicting_topics_require_choice(self):
  self.assertTrue(catalog_decision('Check the ground.','The circuit is outside on the floor.')['needs_clarification'])
 def test_fallback_is_explicitly_broad_and_has_two_options(self):
  self.assertEqual(len(broad_clarification()['options']),2)
  self.assertEqual(broad_clarification()['decision_method'],'broad_context_fallback')
if __name__=='__main__':unittest.main()

