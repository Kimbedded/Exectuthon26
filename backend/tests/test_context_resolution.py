import sys,unittest,io,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from context_resolution import validate_decision, resolve_context
from unittest.mock import patch
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
class ContextResponseTests(unittest.TestCase):
 def response(self,body):
  return io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(body)},'finish_reason':'stop'}]}).encode())
 def test_unambiguous_source_can_supply_its_own_evidence(self):
  with patch('context_resolution.urllib.request.urlopen',return_value=self.response({'topic':'Greeting','evidence':'Hello','options':[]})):
   decision=resolve_context('Hello.')
  self.assertFalse(decision['needs_clarification'])
  self.assertEqual(decision['evidence'],'Hello')
 def test_mixed_resolved_and_clarification_output_is_not_forced_into_a_topic(self):
  body={'topic':'Machine adjustment','evidence':'We are adjusting a machine.',
        'options':['Mechanical looseness','Music playback']}
  with patch('context_resolution.urllib.request.urlopen',return_value=self.response(body)):
   decision=resolve_context('There is too much play.',context='We are adjusting a machine.')
  self.assertTrue(decision['needs_clarification'])
  self.assertEqual(decision['decision_method'],'broad_context_fallback')
 def test_known_ambiguous_phrase_defers_to_translation_instead_of_broad_fallback(self):
  with patch('context_resolution.urllib.request.urlopen',return_value=self.response({'topic':'','evidence':'','options':[]})):
   decision=resolve_context("I'm cooking dinner, can you make it tonight?")
  self.assertFalse(decision['needs_clarification'])
  self.assertEqual(decision['decision_method'],'phrasal_lexicon_deferred')
 def test_unresolvable_context_without_a_lexicon_phrase_still_falls_back(self):
  with patch('context_resolution.urllib.request.urlopen',return_value=self.response({'topic':'','evidence':'','options':[]})):
   decision=resolve_context('This is a vague sentence with no known phrase.')
  self.assertTrue(decision['needs_clarification'])
  self.assertEqual(decision['decision_method'],'broad_context_fallback')
if __name__=='__main__':unittest.main()

