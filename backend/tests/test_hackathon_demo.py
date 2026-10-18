"""Hardcoded regression tests for the hackathon presentation script.

Each test mirrors one beat of the demo narrative exactly: the same sentence,
the same surrounding context, and the outcome the live demo depends on. These
must stay deterministic (no live model call) so the demo cannot go flaky on
stage; see sense_probability.py / phrase_context.py for the sampled-model path
used when a sentence falls outside this reviewed set.
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from context_catalog import catalog_decision
from phrase_context import phrase_decision


class DinnerMakeItScene(unittest.TestCase):
    """"Dinner tonight, can you make it?" — ambiguous: attend vs. cook."""

    def test_bare_invitation_is_ambiguous(self):
        decision = phrase_decision("Dinner tonight, can you make it?", '')
        self.assertIsNotNone(decision)
        self.assertTrue(decision['needs_clarification'])
        self.assertEqual(decision['phrase'], 'make it')
        self.assertEqual(len(decision['options']), 2)
        self.assertIn('come', decision['options'][0].lower())
        self.assertIn('cook', decision['options'][1].lower() + decision['options'][0].lower())

    def test_an_explicit_time_resolves_to_attendance(self):
        decision = phrase_decision("Dinner tonight, can you make it at 8?", '')
        self.assertFalse(decision['needs_clarification'])
        self.assertIn('attend', decision['topic'].lower())

    def test_a_dietary_constraint_resolves_to_cooking(self):
        decision = phrase_decision("Dinner tonight, can you make it without salt?", '')
        self.assertFalse(decision['needs_clarification'])
        self.assertIn('prepare', decision['topic'].lower())


class MachineFixedScene(unittest.TestCase):
    """"Is it fixed?" while troubleshooting a machine — ambiguous: repaired vs. fastened."""

    def test_troubleshooting_context_alone_is_ambiguous(self):
        decision = catalog_decision("Is it fixed?", "We are troubleshooting a machine.")
        self.assertIsNotNone(decision)
        self.assertTrue(decision['needs_clarification'])
        self.assertEqual(decision['phrase'], 'fixed')
        self.assertEqual(len(decision['options']), 2)

    def test_repaired_sense_resolves_with_explicit_repair_evidence(self):
        decision = catalog_decision("Is it fixed now?", "The technician repaired the sensor yesterday.")
        self.assertFalse(decision['needs_clarification'])
        self.assertIn('repair', decision['topic'].lower())

    def test_fastened_sense_resolves_with_explicit_mounting_evidence(self):
        decision = catalog_decision("Is it fixed to the table?", "")
        self.assertFalse(decision['needs_clarification'])
        self.assertIn('secure', decision['topic'].lower())


class GroundScene(unittest.TestCase):
    """"Check the ground." — ambiguous; "beneath your feet" resolves it to physical."""

    def test_bare_check_the_ground_is_ambiguous(self):
        decision = catalog_decision("Check the ground.", '')
        self.assertTrue(decision['needs_clarification'])
        self.assertEqual(decision['phrase'], 'ground')
        self.assertEqual(len(decision['options']), 2)

    def test_beneath_your_feet_resolves_to_physical_ground(self):
        decision = catalog_decision("Check the ground beneath your feet.", '')
        self.assertFalse(decision['needs_clarification'])
        self.assertIn('floor', decision['topic'].lower())

    def test_electrical_context_resolves_to_electrical_ground(self):
        decision = catalog_decision("Check the ground.", "This electrical circuit needs grounding.")
        self.assertFalse(decision['needs_clarification'])
        self.assertIn('electrical', decision['topic'].lower())


if __name__ == '__main__':
    unittest.main()
