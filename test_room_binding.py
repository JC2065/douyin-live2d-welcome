import tempfile
import unittest
from pathlib import Path
from room_binding import RoomBinding


class BindingTests(unittest.TestCase):
    def test_survives_reload_and_can_clear(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'data/binding.json'
            RoomBinding(path).save('123456789')
            self.assertEqual(RoomBinding(path).load(),'123456789')
            RoomBinding(path).clear()
            self.assertEqual(RoomBinding(path).load(),'')

    def test_invalid_input_does_not_overwrite_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            binding=RoomBinding(Path(folder)/'binding.json')
            binding.save('123456789')
            with self.assertRaises(ValueError):
                binding.save('https://v.douyin.com/share/?tracking=value')
            self.assertEqual(binding.load(),'123456789')

    def test_missing_or_corrupt_file_does_not_break_startup(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'binding.json'
            binding=RoomBinding(path)
            self.assertEqual(binding.load(),'')
            for raw in ('{broken', '[]', '{"room":12345}', '{"room":"invalid"}'):
                path.write_text(raw,encoding='utf-8')
                self.assertEqual(binding.load(),'')
