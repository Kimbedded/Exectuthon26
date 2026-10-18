import sys,unittest,io,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from context_resolution import validate_decision, resolve_context
from unittest.mock import patch
from context_catalog import catalog_decision, broad_clarification, classify_chat_mode
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
 def test_classify_chat_mode_defaults_casual_and_flags_technical_keywords(self):
  self.assertEqual(classify_chat_mode('Can you grab lunch later?'),'Casual')
  self.assertEqual(classify_chat_mode(''),'Casual')
  self.assertEqual(classify_chat_mode('Check the network router configuration.'),'Professional')
  self.assertEqual(classify_chat_mode('전기 회로를 점검해 주세요.'),'Professional')
class ContextResponseTests(unittest.TestCase):
 def response(self,body):
  return io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(body)},'finish_reason':'stop'}]}).encode())
 def test_unambiguous_source_can_supply_its_own_evidence(self):
  with patch('context_resolution.urllib.request.urlopen',return_value=self.response({'topic':'Greeting','evidence':'Hello','options':[]})):
   decision=resolve_context('Hello.')
  self.assertFalse(decision['needs_clarification'])
  self.assertEqual(decision['evidence'],'Hello')
 def test_mixed_resolved_and_clarification_output_falls_back_to_lexicon_not_a_question(self):
  body={'topic':'Machine adjustment','evidence':'We are adjusting a machine.',
        'options':['Mechanical looseness','Music playback']}
  with patch('context_resolution.urllib.request.urlopen',return_value=self.response(body)):
   decision=resolve_context('There is too much play.',context='We are adjusting a machine.')
  self.assertFalse(decision['needs_clarification'])
  self.assertEqual(decision['decision_method'],'lexicon_chat_mode')
  self.assertEqual(decision['topic'],'Casual')
 def test_known_ambiguous_phrase_asks_before_translation(self):
  with patch('context_resolution.rank_senses',side_effect=ValueError('No usable votes')):
   decision=resolve_context("I'm cooking dinner, can you make it tonight?")
  self.assertTrue(decision['needs_clarification'])
  self.assertEqual(decision['decision_method'],'reviewed_phrase_senses')
 def test_lopsided_vote_share_above_threshold_auto_resolves_to_green(self):
  ranking={'ranked':[({'gloss_en':'Electrical grounding'},1.0),({'gloss_en':'The floor or earth beneath you'},0.0)],
           'valid_samples':4,'requested_samples':4,'auto_resolved':True}
  with patch('context_resolution.rank_senses',return_value=ranking):
   decision=resolve_context('Check the ground.')
  self.assertFalse(decision['needs_clarification'])
  self.assertIn('electrical',decision['topic'].lower())
  self.assertTrue(decision['decision_method'].endswith('_vote_resolved'))
 def test_vote_share_below_threshold_still_asks(self):
  ranking={'ranked':[({'gloss_en':'Electrical grounding'},0.75),({'gloss_en':'The floor or earth beneath you'},0.25)],
           'valid_samples':4,'requested_samples':4,'auto_resolved':False}
  with patch('context_resolution.rank_senses',return_value=ranking):
   decision=resolve_context('Check the ground.')
  self.assertTrue(decision['needs_clarification'])
  self.assertEqual(decision['likelihood']['shares'],[0.75,0.25])
 def test_unresolvable_context_without_a_lexicon_phrase_defaults_to_casual(self):
  with patch('context_resolution.urllib.request.urlopen',return_value=self.response({'topic':'','evidence':'','options':[]})):
   decision=resolve_context('This is a vague sentence with no known phrase.')
  self.assertFalse(decision['needs_clarification'])
  self.assertEqual(decision['decision_method'],'lexicon_chat_mode')
  self.assertEqual(decision['topic'],'Casual')
 def test_unresolvable_technical_sentence_classifies_as_professional(self):
  with patch('context_resolution.urllib.request.urlopen',return_value=self.response({'topic':'','evidence':'','options':[]})):
   decision=resolve_context('The server needs a firmware update.')
  self.assertFalse(decision['needs_clarification'])
  self.assertEqual(decision['decision_method'],'lexicon_chat_mode')
  self.assertEqual(decision['topic'],'Professional')
if __name__=='__main__':unittest.main()

