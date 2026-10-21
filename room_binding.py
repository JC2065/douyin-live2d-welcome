"""Local room preference; store the stable web ID, never a temporary room ID."""
import json
import re
from pathlib import Path


class RoomBinding:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8')).get('room', '')
            return value if isinstance(value, str) and re.fullmatch(r'\d{5,22}', value) else ''
        except (OSError, ValueError, AttributeError):
            return ''

    def save(self, room):
        if not isinstance(room, str) or not re.fullmatch(r'\d{5,22}', room):
            raise ValueError('请先成功连接直播间，再绑定')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps({'room': room}), encoding='utf-8')
        temp.replace(self.path)

    def clear(self):
        self.path.unlink(missing_ok=True)
