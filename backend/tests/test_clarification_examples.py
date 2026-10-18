import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from context_resolution import resolve_context
from phrase_context import phrase_decision
import sense_probability as votes
import translate_sentence as translator


class RequestedExamples(unittest.TestCase):
    def test_all_six_examples_without_a_live_model(self):
        examples = [
            ("Lets have dinner later, can you make it?", True, None),
            ("Lets have dinner later, can you make it at 8?", False, 'attend'),
            ("Lets have dinner later, can you make it without salt?", False, 'cook'),
            ('Check the ground.', True, None),
            ('Check the ground rail.', False, 'electrical'),
            ('Check on the ground beneath your feet.', False, 'earth'),
        ]
        with patch('context_resolution.rank_senses', side_effect=ValueError('Offline estimate unavailable')), \
             patch('context_resolution.urllib.request.urlopen') as model:
            for source, clarify, topic in examples:
                with self.subTest(source=source):
                    decision = resolve_context(source)
                    self.assertEqual(decision['needs_clarification'], clarify)
                    if topic:
                        self.assertIn(topic, decision['topic'].lower())
                    else:
                        self.assertEqual(len(decision['options']), 2)
                        self.assertEqual(decision['likelihood']['shares'], [None, None])
            model.assert_not_called()

    def test_source_constraint_beats_older_context(self):
        decision = resolve_context('Check the ground rail.', context='We are inspecting the soil outside.')
        self.assertFalse(decision['needs_clarification'])
        self.assertIn('electrical', decision['topic'])
        decision = phrase_decision('Can you make it without salt?', 'I invited you to dinner.')
        self.assertIn('cook', decision['topic'])

    def test_tonight_and_generic_dinner_are_not_decisive(self):
        self.assertTrue(phrase_decision('Can you make it tonight?', 'We are having dinner.')['needs_clarification'])

    def test_real_vote_shares_keep_choices_order_and_do_not_auto_resolve(self):
        ranking={'ranked':[({'gloss_en':'Prepare or cook it'},.75),({'gloss_en':'Come / be able to attend'},.25)],
                 'valid_samples':4,'requested_samples':4}
        with patch('context_resolution.rank_senses', return_value=ranking) as rank:
            decision=resolve_context('Can you make it?', context='Dinner later.')
        self.assertTrue(decision['needs_clarification'])
        self.assertEqual(decision['likelihood']['shares'],[.25,.75])
        self.assertFalse(decision['likelihood']['calibrated'])
        self.assertEqual(rank.call_args.args[0],'Dinner later.')

    def test_zero_votes_are_unavailable_not_invented_50_50(self):
        with patch('sense_probability._ask_once', return_value='Because'):
            result=votes.rank_senses('', 'Can you make it?', 'make it',
                [{'gloss_en':'Attend'},{'gloss_en':'Cook'}], samples=2)
        self.assertEqual(result['valid_samples'],0)
        self.assertFalse(result['auto_resolved'])

    def test_explicit_choice_cannot_be_overridden_by_another_vote(self):
        body={'translation':'저녁을 만들 수 있어요?','literal':'저녁을 만들 수 있어요?','explanation':'저녁을 준비할 수 있는지 묻습니다.'}
        event={'choices':[{'delta':{'content':json.dumps(body)},'finish_reason':'stop'}]}
        stream=io.BytesIO(('data: '+json.dumps(event)+'\ndata: [DONE]\n').encode())
        with patch.object(translator,'rank_senses') as rank, \
             patch.object(translator.urllib.request,'urlopen',return_value=stream) as http:
            result=translator.translate('Can you make it?',context='You were invited to dinner.',
                context_selection='Interpret "make it" as: prepare or cook it',include_choices=True)
        rank.assert_not_called()
        payload=json.loads(json.loads(http.call_args.args[0].data)['messages'][1]['content'])
        self.assertIn('prepare or cook it',payload['TERM_HINTS']['make it'])
        # A human explicitly chose this meaning — maximal certainty, so this
        # drives the green "certain" LED the same as a confident sampled vote.
        self.assertEqual(result['result']['translation_confidence'],1.0)


if __name__=='__main__':unittest.main()
