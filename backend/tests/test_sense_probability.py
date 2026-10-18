import io, json, sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sense_probability as sp
import phrasal_lexicon as lex


def reply(letter):
    body = {'choices': [{'message': {'content': letter}}]}
    return io.BytesIO(json.dumps(body).encode())


class SenseProbabilityTests(unittest.TestCase):
    def test_consistent_choice_resolves_with_high_probability(self):
        senses = [{'gloss_en': 'come / be able to attend', 'ko': '오다'},
                  {'gloss_en': 'prepare or cook it', 'ko': '만들다'}]
        responses = [reply('B') for _ in range(sp.DEFAULT_SAMPLES)] + [reply('A') for _ in range(sp.DEFAULT_SAMPLES)]
        with patch.object(sp.urllib.request, 'urlopen', side_effect=responses):
            result = sp.rank_senses(
                '', "I'm cooking dinner, can you make it tonight?", 'make it', senses,
                endpoint='http://model.test/v1',
            )
        top_sense, top_probability = result['ranked'][0]
        self.assertEqual(top_sense['gloss_en'], 'prepare or cook it')
        self.assertEqual(top_probability, 1.0)
        self.assertTrue(result['auto_resolved'])

    def test_split_choice_does_not_auto_resolve(self):
        senses = [{'gloss_en': 'sense A', 'ko': 'A뜻'}, {'gloss_en': 'sense B', 'ko': 'B뜻'}]
        forward = [reply('A') for _ in range(6)] + [reply('B') for _ in range(2)]
        reverse = [reply('A') for _ in range(2)] + [reply('B') for _ in range(6)]
        with patch.object(sp.urllib.request, 'urlopen', side_effect=forward + reverse):
            result = sp.rank_senses('', 'An ambiguous sentence.', 'phrase', senses, endpoint='http://model.test/v1')
        self.assertFalse(result['auto_resolved'])
        self.assertEqual(len(result['ranked']), 2)
        self.assertAlmostEqual(result['ranked'][0][1], 0.75)

    def test_invalid_responses_fall_back_to_uniform(self):
        senses = [{'gloss_en': 'sense A', 'ko': 'A뜻'}, {'gloss_en': 'sense B', 'ko': 'B뜻'}]
        garbage = [reply('X') for _ in range(sp.DEFAULT_SAMPLES * 2)]
        with patch.object(sp.urllib.request, 'urlopen', side_effect=garbage):
            result = sp.rank_senses('', 'sentence', 'phrase', senses, endpoint='http://model.test/v1')
        self.assertFalse(result['auto_resolved'])
        self.assertAlmostEqual(result['ranked'][0][1], 0.5)
        self.assertAlmostEqual(result['ranked'][1][1], 0.5)


class PhrasalLexiconTests(unittest.TestCase):
    def test_longest_phrase_wins_and_is_case_insensitive(self):
        hit = lex.find_phrase("Can you PICK UP the kids tonight?")
        self.assertEqual(hit[0], 'pick up')

    def test_no_match_returns_none(self):
        self.assertIsNone(lex.find_phrase('Nothing ambiguous here.'))

    def test_word_boundary_does_not_match_substring(self):
        self.assertIsNone(lex.find_phrase('The sprinter will overtake it on the final lap.'))


if __name__ == '__main__':
    unittest.main()
