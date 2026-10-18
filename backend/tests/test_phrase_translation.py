import io, json, sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import translate_sentence as m


def sse(body):
    event = {'choices': [{'delta': {'content': json.dumps(body, ensure_ascii=False)}, 'finish_reason': 'stop'}]}
    return io.BytesIO(('data: ' + json.dumps(event) + '\ndata: [DONE]\n').encode())


class PhraseAlternativeTests(unittest.TestCase):
    def test_ambiguous_phrase_attaches_a_calibrated_alternative(self):
        stream = sse({'translation': '오늘 밤에 올 수 있어?', 'alternatives': []})
        plain = io.BytesIO(json.dumps(
            {'choices': [{'message': {'content': '오늘 밤에 저녁을 만들 수 있어?'}}]}
        ).encode())
        ranking = {
            'ranked': [
                ({'gloss_en': 'come / be able to attend', 'ko': '오다, 참석하다'}, 0.75),
                ({'gloss_en': 'prepare or cook it', 'ko': '그것을 만들다'}, 0.25),
            ],
            'auto_resolved': False,
        }

        with patch.object(m, 'rank_senses', return_value=ranking) as ranker, \
             patch.object(m.urllib.request, 'urlopen', side_effect=[stream, plain]):
            result = m.translate("I'm cooking dinner, can you make it tonight?")

        self.assertTrue(result['valid'])
        self.assertEqual(result['result']['translation_confidence'], 0.75)
        alternatives = result['result']['alternatives']
        self.assertEqual(len(alternatives), 1)
        self.assertEqual(alternatives[0]['probability'], 0.25)
        self.assertEqual(alternatives[0]['translation'], '오늘 밤에 저녁을 만들 수 있어?')
        self.assertEqual(ranker.call_args.args[2], 'make it')

    def test_confident_phrase_sense_reports_no_alternatives(self):
        stream = sse({'translation': '오늘 밤에 저녁을 만들 수 있어?', 'alternatives': []})
        ranking = {
            'ranked': [
                ({'gloss_en': 'prepare or cook it', 'ko': '그것을 만들다'}, 0.95),
                ({'gloss_en': 'come / be able to attend', 'ko': '오다, 참석하다'}, 0.05),
            ],
            'auto_resolved': True,
        }
        with patch.object(m, 'rank_senses', return_value=ranking), \
             patch.object(m.urllib.request, 'urlopen', return_value=stream):
            result = m.translate("I'm cooking dinner, can you make it tonight?")
        self.assertTrue(result['valid'])
        self.assertEqual(result['result']['translation_confidence'], 0.95)
        self.assertEqual(result['result']['alternatives'], [])

    def test_sentence_without_a_lexicon_phrase_is_unaffected(self):
        stream = sse({'translation': '너는 외출 금지야.', 'alternatives': []})
        with patch.object(m, 'rank_senses') as ranker, \
             patch.object(m.urllib.request, 'urlopen', return_value=stream):
            result = m.translate("You're grounded.")
        self.assertTrue(result['valid'])
        self.assertIsNone(result['result']['translation_confidence'])
        self.assertEqual(result['result']['alternatives'], [])
        ranker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
