import asyncio
import hashlib
import json
import time
import uuid
from collections import deque, Counter
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
from interactions import SpeechQueue, ActivityLimiter, clean_name
from welcome_delivery import next_delivery, finish_delivery, batch_text, PLAYER_LEASE_SECONDS, EVENT_MAX_AGE

ROOT = Path(__file__).resolve().parent
AUDIO = ROOT / 'data/audio'
AUDIO.mkdir(parents=True, exist_ok=True)
gate = WelcomeGate(60)
phrases = WelcomePhrases()
binding = RoomBinding(ROOT/'data/room-binding.json')
logs = deque(maxlen=80)
pending = SpeechQueue(maxsize=120)
events = deque(maxlen=120)
sequence = 0
muted = False
generation = 0
last_player = 0.0
player_ready = False
player_id = None
server_id = uuid.uuid4().hex
last_playback = None
diagnostics = Counter()
BATCH_WINDOW = 0.8
BATCH_SIZE = 3
activity_limiter = ActivityLimiter()
INTERACTION_PATH = ROOT/'data/interaction-settings.json'
interaction_settings = {'like':True,'gift':True,'chat':True}
try:
    saved = json.loads(INTERACTION_PATH.read_text(encoding='utf-8'))
    interaction_settings.update({key:value for key,value in saved.items() if key in interaction_settings and isinstance(value,bool)})
except (OSError,ValueError,AttributeError):
    pass
bridge = None


def log(message):
    logs.appendleft({'time': time.strftime('%H:%M:%S'), 'message': message})


async def worker():
    global sequence
    carry = None
    while True:
        first = carry if carry is not None else await pending.get()
        carry = None
        batch = [first]
        try:
            if first['generation'] != generation or muted or time.time()-first['received'] > EVENT_MAX_AGE:
                diagnostics['expired_people'] += 1
                continue
            deadline = asyncio.get_running_loop().time()+BATCH_WINDOW
            while first.get('kind','welcome') in ('welcome','like') and len(batch) < BATCH_SIZE:
                remaining = deadline-asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    item = await asyncio.wait_for(pending.get(),remaining)
                    if item.get('kind','welcome') != first.get('kind','welcome'):
                        carry = item
                        break
                    batch.append(item)
                except asyncio.TimeoutError:
                    break
            valid = [x for x in batch if x['generation']==generation and not muted
                     and time.time()-x['received'] <= EVENT_MAX_AGE]
            diagnostics['expired_people'] += len(batch)-len(valid)
            if not valid:
                continue
            text = batch_text(valid)
            key = hashlib.sha256(text.encode()).hexdigest()[:24]
            path = AUDIO/(key+'.mp3')
            if not path.exists():
                tmp = path.with_suffix('.tmp')
                try:
                    await asyncio.wait_for(edge_tts.Communicate(text,'zh-CN-XiaoxiaoNeural',rate='+10%').save(str(tmp)),8)
                    if tmp.stat().st_size < 100:
                        raise ValueError('empty audio')
                    tmp.replace(path)
                except Exception as exc:
                    tmp.unlink(missing_ok=True)
                    diagnostics['tts_fallbacks'] += 1
                    log('在线语音不可用，尝试浏览器语音：'+type(exc).__name__)
            if first['generation'] != generation or muted:
                continue
            if len(events) == events.maxlen and not events[0].get('done'):
                diagnostics['overflow_people'] += events[0].get('people',1)
                log('播放积压已满，最早的一组欢迎被移除。')
            sequence += 1
            event = dict(valid[0], id=uuid.uuid4().hex, text=text, seq=sequence,
                         audio=f'/audio/{key}.mp3' if path.exists() else None,
                         created=min(x['received'] for x in valid), people=len(valid),
                         source='douyin' if any(x['source']=='douyin' for x in valid) else 'simulation')
            events.append(event)
            diagnostics['prepared_groups'] += 1
            log(f'准备播放（{len(valid)}人）：'+text)
            for old in sorted(AUDIO.glob('*.mp3'),key=lambda p:p.stat().st_mtime,reverse=True)[200:]:
                old.unlink(missing_ok=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            diagnostics['worker_errors'] += 1
            log('欢迎处理异常，将继续处理后续观众：'+type(exc).__name__)
        finally:
            for _ in batch:
                pending.task_done()


@asynccontextmanager
async def lifespan(app):
    global bridge
    loop = asyncio.get_running_loop()
    async def live_enter(uid, name):
        result = await enter(Entry(uid=uid, name=name, source='douyin'))
        bridge.record_result(result['accepted'], result.get('code',''))
    def on_entry(uid, name):
        future = asyncio.run_coroutine_threadsafe(live_enter(uid, name), loop)
        def done(f):
            if not f.cancelled() and f.exception():
                log('真实进房处理失败：' + type(f.exception()).__name__)
        future.add_done_callback(done)
    def on_activity(data):
        future = asyncio.run_coroutine_threadsafe(activity_enter(data),loop)
        future.add_done_callback(lambda f: log('互动处理失败：'+type(f.exception()).__name__) if not f.cancelled() and f.exception() else None)
    bridge = DouyinBridge(on_entry, log, on_activity=on_activity)
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
    diagnostics['received_requests'] += 1
    if muted:
        diagnostics['skip_paused'] += 1
        return {'accepted': False, 'code': 'paused', 'reason': '欢迎已暂停'}
    if time.monotonic() - last_player > PLAYER_LEASE_SECONDS:
        diagnostics['skip_player_unready'] += 1
        return {'accepted': False, 'code': 'player_unready', 'reason': '请先在角色窗口点击「启用欢迎声音」'}
    if pending.full():
        diagnostics['skip_queue_full'] += 1
        return {'accepted': False, 'code': 'queue_full', 'reason': '欢迎队列已满'}
    ok, remaining = gate.enter(body.uid)
    if not ok:
        diagnostics['skip_cooldown'] += 1
        log(f'{body.name} 重复进房：忽略，剩余 {remaining} 秒')
        return {'accepted': False, 'code': 'cooldown', 'remaining': remaining, 'reason': f'60 秒内重复进入，剩余 {remaining} 秒'}
    name = clean_name(body.name)
    diagnostics['accepted_people'] += 1
    text = phrases.next(name)
    pending.put_nowait({'id': uuid.uuid4().hex, 'text': text, 'name': name, 'generation': generation,
                       'received': time.time(), 'kind':'welcome', 'source': body.source})
    log(f'{"真实进房" if body.source == "douyin" else "模拟进房"} · {name}：加入欢迎队列')
    return {'accepted': True, 'text': text}


async def activity_enter(data):
    kind=data['kind']
    diagnostics[kind+'_received'] += 1
    if not interaction_settings.get(kind,False):
        diagnostics[kind+'_disabled'] += 1
        return
    if muted or time.monotonic()-last_player > PLAYER_LEASE_SECONDS:
        diagnostics[kind+'_unready'] += 1
        return
    if not activity_limiter.allow(data):
        diagnostics[kind+'_deduplicated'] += 1
        return
    if pending.full():
        diagnostics[kind+'_queue_full'] += 1
        log('互动队列已满，未朗读当前'+kind)
        return
    pending.put_nowait(dict(data,id=uuid.uuid4().hex,generation=generation,received=time.time(),source='douyin'))
    diagnostics[kind+'_accepted'] += 1
    log({'chat':'评论','gift':'礼物','like':'点赞'}[kind]+'已加入朗读队列：'+data['text'])


class InteractionSettings(BaseModel):
    like: bool
    gift: bool
    chat: bool


@app.post('/api/interactions')
async def set_interactions(body: InteractionSettings):
    value=body.model_dump()
    temp=INTERACTION_PATH.with_suffix('.tmp')
    temp.write_text(json.dumps(value),encoding='utf-8')
    temp.replace(INTERACTION_PATH)
    interaction_settings.update(value)
    log('点赞、礼物、评论朗读设置已保存。')
    return value


@app.get('/api/status')
def status():
    info = bridge.snapshot() if bridge else {'state': 'idle'}
    labels = {'idle': '本地模拟 · 未连接抖音', 'resolving': '正在解析分享链接', 'connecting': '正在连接抖音',
              'connected': '抖音已连接 · 监听真实进房', 'reconnecting': '抖音断线 · 正在重连',
              'stopping': '正在断开抖音', 'ended': '直播已结束', 'error': '抖音连接失败'}
    return {'interactions': dict(interaction_settings), 'bound_room': binding.load(), 'server_id': server_id, 'preset_count': len(phrases.templates), 'playback': last_playback, 'mode': labels.get(info['state'], info['state']), 'connection': info, 'cooldown': 60, 'muted': muted, 'seq': sequence,
            'audio_ready': player_ready, 'player': time.monotonic()-last_player < PLAYER_LEASE_SECONDS, 'diagnostics': dict(diagnostics),
            'awaiting_playback': sum(not e.get('done') and e['generation']==generation for e in events),
            'logs': list(logs), 'queued': pending.qsize()}


@app.get('/api/events')
async def poll(after: int = 0, client: str = '', ready: bool = True):
    global last_player, player_id, player_ready
    now = time.monotonic()
    if not client or (player_id and player_id != client and now-last_player < PLAYER_LEASE_SECONDS):
        return {'server_id': server_id, 'events': [], 'muted': muted, 'busy': True}
    player_id, last_player, player_ready = client, now, ready
    event = next_delivery(events,client,generation) if not muted and ready else None
    for dropped in events:
        if dropped.get('drop_reason') and not dropped.get('counted_drop'):
            dropped['counted_drop'] = True
            diagnostics[dropped['drop_reason']+'_people'] += dropped.get('people',1)
            log('欢迎未播出：'+dropped['drop_reason'])
    return {'server_id': server_id, 'events': [event] if event else [], 'muted': muted, 'busy': False}


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
    phase: str = Field(pattern='^(started|finished|failed|blocked)$')
    attempt: int = Field(default=1, ge=1, le=3)
    detail: str = Field(default='', max_length=180)


class PlayerClaim(BaseModel):
    client: str = Field(min_length=1,max_length=80)


@app.post('/api/player/claim')
async def player_claim(body: PlayerClaim):
    global player_id, last_player, player_ready
    player_id, last_player, player_ready = body.client, time.monotonic(), True
    log('当前角色窗口已接管语音播放。')
    return {'ok':True}


@app.post('/api/player/release')
async def player_release(body: PlayerClaim):
    global player_id, last_player, player_ready
    if body.client == player_id:
        player_id, last_player, player_ready = None, 0.0, False
    return {'ok':True}


@app.post('/api/playback')
async def playback_report(body: PlaybackReport):
    global last_playback
    if body.client != player_id or time.monotonic()-last_player > PLAYER_LEASE_SECONDS:
        raise HTTPException(status_code=409, detail='播放窗口已失去租约')
    event = next((e for e in events if e['id'] == body.event), None)
    if event is None:
        raise HTTPException(status_code=404, detail='欢迎事件已过期')
    if body.attempt != event.get('attempt',1):
        raise HTTPException(status_code=409,detail='旧的播放尝试已失效')
    if event.get('done'):
        return {'ok': True}
    finish_delivery(event,body.phase)
    if body.phase == 'blocked':
        event.pop('owner',None)
        diagnostics['audio_blocked'] += 1
    if body.phase == 'finished':
        diagnostics['played_groups'] += 1
        diagnostics['played_people'] += event.get('people',1)
        diagnostics[event.get('kind','welcome')+'_played'] += 1
    elif body.phase == 'failed':
        diagnostics['audio_failures'] += 1
    last_playback = {'detail': body.detail, 'phase': body.phase, 'time': time.time(), 'source': event['source']}
    labels = {'started': '开始播放', 'finished': '浏览器播放完成', 'failed': '浏览器播放失败', 'blocked': '声音被阻止，请点击角色恢复声音'}
    log(labels[body.phase] + '：' + event['text'] + (' · '+body.detail if body.detail else ''))
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
