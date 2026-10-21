"""Shuffle all presets once per round, with no repeat at round boundaries."""
import json
import random
from pathlib import Path


class WelcomePhrases:
    def __init__(self, path=None, rng=None):
        path = path or Path(__file__).with_name('welcome_presets.json')
        self.templates = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(self.templates, list) or len(self.templates) < 2:
            raise ValueError('至少需要两条欢迎语')
        if any(not isinstance(t, str) or not 1 <= len(t) <= 60
               or '{name}' not in t or '{' in t.replace('{name}', '')
               or '}' in t.replace('{name}', '') for t in self.templates):
            raise ValueError('欢迎语须包含 {name}，最长 60 字，不支持其他占位符')
        if len(set(self.templates)) != len(self.templates):
            raise ValueError('欢迎语不能重复')
        self.rng = rng or random.Random()
        self.bag = []
        self.last = None

    def next(self, name):
        if not self.bag:
            self.bag = list(self.templates)
            self.rng.shuffle(self.bag)
            if self.bag[-1] == self.last:
                self.bag[0], self.bag[-1] = self.bag[-1], self.bag[0]
        self.last = self.bag.pop()
        return self.last.replace('{name}', name)
