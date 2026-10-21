import unittest
from welcome import WelcomeGate

class CooldownTests(unittest.TestCase):
    def test_exact_boundary_and_ignored_entries_do_not_extend(self):
        now = [0.0]
        gate = WelcomeGate(clock=lambda: now[0])
        self.assertTrue(gate.enter('one')[0])
        now[0] = 59.999
        self.assertFalse(gate.enter('one')[0])
        now[0] = 60
        self.assertTrue(gate.enter('one')[0])
        now[0] = 119
        self.assertFalse(gate.enter('one')[0])
        now[0] = 120
        self.assertTrue(gate.enter('one')[0])

    def test_separate_users(self):
        gate = WelcomeGate(clock=lambda: 0)
        self.assertTrue(gate.enter('a')[0])
        self.assertTrue(gate.enter('b')[0])
        self.assertFalse(gate.enter('a')[0])

    def test_missing_id(self):
        with self.assertRaises(ValueError):
            WelcomeGate().enter('')

if __name__ == '__main__':
    unittest.main()
