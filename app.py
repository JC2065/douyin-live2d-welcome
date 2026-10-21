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
from douyin_bridge import DouyinBridge
from welcome_phrases import WelcomePhrases
from room_binding import RoomBinding

ROOT = Path(__file__).resolve().parent
AUDIO = ROOT / 'data/audio'
AUDIO.mkdir(parents=True, exist_ok=True)
gate = WelcomeGate(60)
phrases = WelcomePhrases()
binding = RoomBinding(ROOT/'data/room-binding.json')
logs = deque(maxlen=80)
pending = asyncio.Queue(maxsize=20)
events = deque(maxlen=40)
sequence = 0
muted = False
generation = 0
last_player = 0.0
player_id = None
server_id = uuid.uuid4().hex
last_playback = None
bridge = None


def log(message):
    logs.appendleft({'time': time.strftime('%H:%M:%S'), 'message': message})


async def worker():
    global sequence
    while True:
        item = await pending.get()
        try:
            if item['generation'] != generation or muted or time.time()-item['received'] > 25:
                continue
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
            if item['generation'] != generation or muted or time.time()-item['received'] > 25:
                continue
            sequence += 1
            events.append(dict(item, seq=sequence, audio=f'/audio/{key}.mp3' if path.exists() else None, created=item['received']))
            log('准备播放：' + item['text'])
            # Cache is bounded; no indefinite accumulation of viewer names/audio.
            for old in sorted(AUDIO.glob('*.mp3'), key=lambda p:p.stat().st_mtime, reverse=True)[200:]:
                old.unlink(missing_ok=True)
        finally:
            pending.task_done()


@asynccontextmanager
async def lifespan(app):
    global bridge
    loop = asyncio.get_running_loop()
    async def live_enter(uid, name):
        result = await enter(Entry(uid=uid, name=name, source='douyin'))
        bridge.record_result(result['accepted'])
    def on_entry(uid, name):
        future = asyncio.run_coroutine_threadsafe(live_enter(uid, name), loop)
        def done(f):
            if not f.cancelled() and f.exception():
                log('真实进房处理失败：' + type(f.exception()).__name__)
        future.add_done_callback(done)
    bridge = DouyinBridge(on_entry, log)
    task = asyncio.create_task(worker())
    log('本地模拟模式已启动，未连接抖音。')
    saved_room = binding.load()
    if saved_room:
        bridge.start(saved_room)
        log('正在自动连接已绑定的直播间。')
    yield
    bridge.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


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
    source: str = 'simulation'


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
    text = phrases.next(name)
    pending.put_nowait({'id': uuid.uuid4().hex, 'text': text, 'name': name, 'generation': generation,
                       'received': time.time(), 'source': body.source})
    log(f'{"真实进房" if body.source == "douyin" else "模拟进房"} · {name}：加入欢迎队列')
    return {'accepted': True, 'text': text}


@app.get('/api/status')
def status():
    info = bridge.snapshot() if bridge else {'state': 'idle'}
    labels = {'idle': '本地模拟 · 未连接抖音', 'resolving': '正在解析分享链接', 'connecting': '正在连接抖音',
              'connected': '抖音已连接 · 监听真实进房', 'reconnecting': '抖音断线 · 正在重连',
              'stopping': '正在断开抖音', 'ended': '直播已结束', 'error': '抖音连接失败'}
    return {'bound_room': binding.load(), 'server_id': server_id, 'preset_count': len(phrases.templates), 'playback': last_playback, 'mode': labels.get(info['state'], info['state']), 'connection': info, 'cooldown': 60, 'muted': muted, 'seq': sequence,
            'player': time.monotonic()-last_player < 5, 'logs': list(logs), 'queued': pending.qsize()}


@app.get('/api/events')
def poll(after: int = 0, client: str = ''):
    global last_player, player_id
    now = time.monotonic()
    if not client or (player_id and player_id != client and now-last_player < 5):
        return {'server_id': server_id, 'events': [], 'muted': muted, 'busy': True}
    player_id, last_player = client, now
    return {'server_id': server_id, 'events': [e for e in events if e['seq'] > after and time.time()-e['created'] < 45 and e['generation']==generation], 'muted': muted, 'busy': False}


@app.post('/api/mute')
async def mute():
    global muted, generation
    muted = not muted
    if muted:
        generation += 1
        events.clear()
        while not pending.empty():
            try:
                pending.get_nowait()
                pending.task_done()
            except asyncio.QueueEmpty:
                break
    log('欢迎已暂停' if muted else '欢迎已恢复')
    return {'muted': muted}


class ConnectionInput(BaseModel):
    room: str = Field(min_length=5, max_length=3000)


class PlaybackReport(BaseModel):
    client: str = Field(min_length=1, max_length=80)
    event: str = Field(min_length=1, max_length=80)
    phase: str = Field(pattern='^(started|finished|failed)$')


@app.post('/api/playback')
async def playback_report(body: PlaybackReport):
    global last_playback
    if body.client != player_id or time.monotonic()-last_player > 5:
        raise HTTPException(status_code=409, detail='播放窗口已失去租约')
    event = next((e for e in events if e['id'] == body.event), None)
    if event is None:
        raise HTTPException(status_code=404, detail='欢迎事件已过期')
    last_playback = {'phase': body.phase, 'time': time.time(), 'source': event['source']}
    labels = {'started': '开始播放', 'finished': '浏览器播放完成', 'failed': '浏览器播放失败'}
    log(labels[body.phase] + '：' + event['text'])
    return {'ok': True}


@app.post('/api/connection/start')
async def connection_start(body: ConnectionInput):
    try:
        bridge.start(body.room)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return bridge.snapshot()


@app.post('/api/connection/stop')
async def connection_stop():
    bridge.stop()
    return bridge.snapshot()


@app.post('/api/connection/bind')
async def bind_room():
    info = bridge.snapshot()
    if info['state'] != 'connected':
        raise HTTPException(status_code=400, detail='请先成功连接直播间，再绑定')
    binding.save(info['room'])
    log('已记住直播间，下次启动自动连接。')
    return {'bound_room': info['room']}


@app.post('/api/connection/unbind')
async def unbind_room():
    binding.clear()
    log('已取消直播间绑定，当前连接继续运行。')
    return {'bound_room': ''}


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
