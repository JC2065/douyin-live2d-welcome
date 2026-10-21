"""Welcome gate: suppressed entries never extend the 60-second cooldown."""
import time
import threading


class WelcomeGate:
    def __init__(self, seconds=60, clock=time.monotonic):
        self.seconds, self.clock = seconds, clock
        self.last = {}
        self.lock = threading.Lock()

    def enter(self, uid):
        if not uid:
            raise ValueError('缺少观众 ID')
        with self.lock:
            now = self.clock()
            previous = self.last.get(uid)
            if previous is not None and now - previous < self.seconds:
                return False, round(self.seconds - (now - previous), 1)
            self.last = {k: v for k, v in self.last.items() if now-v < self.seconds}
            self.last[uid] = now
            return True, 0
