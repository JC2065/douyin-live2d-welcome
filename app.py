import asyncio
import hashlib
import json
import time
import uuid
from collections import deque
from pathlib import Path
from contextlib import asynccontextmanager
import edge_tts
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from welcome import WelcomeGate

ROOT = Path(__file__).resolve().parent
AUDIO = ROOT / 'data/audio'
AUDIO.mkdir(parents=True, exist_ok=True)
gate = WelcomeGate(60)
logs = deque(maxlen=80)
pending = asyncio.Queue(maxsize=20)
events = deque(maxlen=40)
sequence = 0
muted = False
generation = 0
last_player = 0.0
player_id = None


def log(message):
    logs.appendleft({'time': time.strftime('%H:%M:%S'), 'message': message})


async def worker():
    global sequence
    while True:
        item = await pending.get()
        try:
            key = hashlib.sha256(item['text'].encode()).hexdigest()[:24]
            path = AUDIO / (key + '.mp3')
            if not path.exists():
                tmp = path.with_suffix('.tmp')
                try:
                    await asyncio.wait_for(edge_tts.Communicate(item['text'], 'zh-CN-XiaoxiaoNeural', rate='+5%').save(str(tmp)), 18)
                    tmp.replace(path)
                except Exception as exc:
                    tmp.unlink(missing_ok=True)
                    log('在线语音不可用，将尝试浏览器语音：' + type(exc).__name__)
            if item['generation'] != generation or muted:
                continue
            sequence += 1
            events.append(dict(item, seq=sequence, audio=f'/audio/{key}.mp3' if path.exists() else None, created=time.time()))
            log('准备播放：' + item['text'])
            # Cache is bounded; no indefinite accumulation of viewer names/audio.
            for old in sorted(AUDIO.glob('*.mp3'), key=lambda p:p.stat().st_mtime, reverse=True)[200:]:
                old.unlink(missing_ok=True)
        finally:
            pending.task_done()


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(worker())
    log('本地模拟模式已启动，未连接抖音。')
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


@app.middleware('http')
async def local_only(request: Request, call_next):
    host = request.headers.get('host', '').split(':')[0]
    if host not in ('127.0.0.1', 'localhost', 'testserver'):
        from fastapi.responses import JSONResponse
        return JSONResponse({'error': 'local access only'}, status_code=403)
    origin = request.headers.get('origin')
    if request.method == 'POST' and origin and origin not in ('http://127.0.0.1:18765', 'http://localhost:18765'):
        from fastapi.responses import JSONResponse
        return JSONResponse({'error': 'origin rejected'}, status_code=403)
    return await call_next(request)


class Entry(BaseModel):
    uid: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=30)


@app.post('/api/enter')
async def enter(body: Entry):
    if muted:
        return {'accepted': False, 'reason': '欢迎已暂停'}
    if time.monotonic() - last_player > 5:
        return {'accepted': False, 'reason': '请先在角色窗口点击「启用欢迎声音」'}
    if pending.full():
        return {'accepted': False, 'reason': '欢迎队列已满'}
    ok, remaining = gate.enter(body.uid)
    if not ok:
        log(f'{body.name} 重复进房：忽略，剩余 {remaining} 秒')
        return {'accepted': False, 'remaining': remaining, 'reason': f'60 秒内重复进入，剩余 {remaining} 秒'}
    name = ''.join(c for c in body.name if c.isalnum() or c in ' _-')[:20].strip() or '新朋友'
    text = f'欢迎{name}，一起探索技术吧！'
    pending.put_nowait({'id': uuid.uuid4().hex, 'text': text, 'name': name, 'generation': generation})
    log(f'{name} 进入：加入欢迎队列')
    return {'accepted': True, 'text': text}


@app.get('/api/status')
def status():
    return {'mode': '本地模拟 · 未连接抖音', 'cooldown': 60, 'muted': muted, 'seq': sequence,
            'player': time.monotonic()-last_player < 5, 'logs': list(logs), 'queued': pending.qsize()}


@app.get('/api/events')
def poll(after: int = 0, client: str = ''):
    global last_player, player_id
    now = time.monotonic()
    if not client or (player_id and player_id != client and now-last_player < 5):
        return {'events': [], 'muted': muted, 'busy': True}
    player_id, last_player = client, now
    return {'events': [e for e in events if e['seq'] > after and time.time()-e['created'] < 45 and e['generation']==generation], 'muted': muted, 'busy': False}


@app.post('/api/mute')
def mute():
    global muted, generation
    muted = not muted
    if muted:
        generation += 1
        events.clear()
    log('欢迎已暂停' if muted else '欢迎已恢复')
    return {'muted': muted}


@app.get('/')
def index():
    return FileResponse(ROOT/'web/index.html')


@app.get('/overlay')
def overlay():
    return FileResponse(ROOT/'web/overlay.html')


app.mount('/static', StaticFiles(directory=ROOT/'web'), name='static')
app.mount('/audio', StaticFiles(directory=AUDIO), name='audio')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=18765)
