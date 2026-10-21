import random
import unittest
from welcome_phrases import WelcomePhrases


class PhraseTests(unittest.TestCase):
    def test_every_preset_once_per_round_and_no_boundary_repeat(self):
        phrases = WelcomePhrases(rng=random.Random(7))
        expected = {t.replace('{name}', '同学') for t in phrases.templates}
        previous = None
        for _ in range(20):
            round_text = [phrases.next('同学') for _ in phrases.templates]
            self.assertEqual(set(round_text), expected)
            self.assertNotEqual(previous, round_text[0])
            previous = round_text[-1]

    def test_name_is_inserted_without_formatting_user_input(self):
        text = WelcomePhrases(rng=random.Random(1)).next('A{test}')
        self.assertIn('A{test}', text)
        self.assertNotIn('{name}', text)


if __name__ == '__main__':
    unittest.main()
