"""Managed optional connector. Third-party source stays in ignored vendor/."""
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from room_links import resolve_room, member_identity


class DouyinBridge:
    def __init__(self, on_entry, on_log, client_factory=None, on_activity=None):
        self.on_entry, self.on_log = on_entry, on_log
        self.client_factory = client_factory
        self.on_activity = on_activity
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.client = None
        self.data = {'state': 'idle', 'room': '', 'error': '', 'messages': 0,
                     'members': 0, 'accepted': 0, 'skipped': 0, 'reconnects': 0,
                     'last_message': None, 'last_member': None}
        self.kinds = Counter()
        self.skip_reasons = Counter()

    def snapshot(self):
        with self.lock:
            return dict(self.data, message_types=dict(self.kinds), skip_reasons=dict(self.skip_reasons))

    def update(self, **fields):
        with self.lock:
            self.data.update(fields)

    def start(self, value):
        # Validate synchronously; network resolution happens outside the API loop.
        from room_links import extract_room_input
        extract_room_input(value)
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('连接仍在运行，请先断开并等待退出')
            self.stop_event.clear()
            self.data.update(state='resolving', room='', error='', messages=0, members=0,
                             accepted=0, skipped=0, reconnects=0, last_message=None, last_member=None)
            self.kinds.clear()
            self.skip_reasons.clear()
            self.thread = threading.Thread(target=self.run, args=(value,), daemon=True, name='douyin-bridge')
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.update(state='stopping')
        if self.client:
            self.client._stop()
        if not self.thread or not self.thread.is_alive():
            self.update(state='idle')

    def run(self, value):
        try:
            room = resolve_room(value)
            if self.stop_event.is_set():
                return
            self.update(room=room, state='connecting')
            self.on_log('已解析分享链接，正在连接直播间。')
            if self.client_factory is None:
                vendor = Path(__file__).resolve().parent/'vendor/douyin-ai-assist'
                if not (vendor/'douyin_ai_assist').is_dir():
                    raise RuntimeError('缺少可选抖音连接器，参见 docs/DOUYIN.md')
                sys.path.insert(0, str(vendor))
                from douyin_ai_assist import config
                config.COLD_FIELD_ENABLED = False
                config.TTS_ENABLED = False
                from douyin_ai_assist.live_client import DouYinLive
                self.client_factory = DouYinLive
            delay = 2
            while not self.stop_event.is_set():
                client = self.client_factory(room)
                self.client = client
                self.bind(client)
                try:
                    client.start()
                except Exception as exc:
                    self.update(error=type(exc).__name__ + '：连接失败，请检查网络与开播状态')
                finally:
                    client._stop()
                    client._parser._executor.shutdown(wait=False, cancel_futures=True)
                if self.stop_event.is_set():
                    break
                self.update(state='reconnecting', reconnects=self.data['reconnects']+1)
                self.on_log(f'直播连接断开，{delay} 秒后重试。')
                if self.stop_event.wait(delay):
                    break
                delay = min(delay*2, 30)
        except Exception as exc:
            # Never expose redirect URLs or tracking parameters in public status/logs.
            self.update(state='error', error=str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__+'：链接解析失败')
            self.on_log('抖音连接未成功：' + self.data['error'])
        finally:
            if self.stop_event.is_set() and self.data['state'] != 'ended':
                self.update(state='idle', error='')
            self.client = None

    def bind(self, client):
        from douyin_ai_assist.douyin.douyin_pb2 import MemberMessage, ControlMessage, ChatMessage, GiftMessage, LikeMessage
        from interactions import activity_payload
        def member(payload):
            event = MemberMessage()
            event.ParseFromString(payload)
            with self.lock:
                self.data['members'] += 1
                self.data['last_member'] = time.time()
            identity = member_identity(event)
            if identity:
                self.on_entry(*identity)
            else:
                self.record_result(False, "missing_identity_or_non_entry")
        def control(payload):
            event = ControlMessage()
            event.ParseFromString(payload)
            if event.action == 3:
                self.stop_event.set()
                self.update(state='ended')
                client._stop()
        client._parser._handlers = {'WebcastMemberMessage': member, 'WebcastControlMessage': control}
        def activity_handler(message_type,kind):
            def handle(payload):
                event=message_type()
                event.ParseFromString(payload)
                data=activity_payload(event,kind)
                if data and self.on_activity:
                    self.on_activity(data)
            return handle
        client._parser._handlers.update({
            'WebcastChatMessage': activity_handler(ChatMessage,'chat'),
            'WebcastGiftMessage': activity_handler(GiftMessage,'gift'),
            'WebcastLikeMessage': activity_handler(LikeMessage,'like'),
        })
        original_parse = client._parser.parse
        def parse(raw_message, send_ack=None):
            from douyin_ai_assist.douyin.douyin_pb2 import PushFrame, Response
            import gzip
            frame = PushFrame()
            frame.ParseFromString(raw_message)
            if not frame.payload:
                return
            payload = gzip.decompress(frame.payload) if frame.payload[:2] == b'\x1f\x8b' else frame.payload
            response = Response()
            response.ParseFromString(payload)
            with self.lock:
                self.data['messages'] += len(response.messages)
                self.data['last_message'] = time.time()
                self.kinds.update(m.method for m in response.messages)
            # Upstream parser assumes gzip, normalize an uncompressed payload.
            if frame.payload[:2] != b'\x1f\x8b':
                frame.payload = gzip.compress(payload)
                raw_message = frame.SerializeToString()
            original_parse(raw_message, send_ack)
        client._parser.parse = parse
        opened = client._on_open
        def on_open(ws):
            opened(ws)
            self.update(state='connected', error='')
            self.on_log('抖音已连接，正在监听真实进房。')
            opened_at = time.time()
            def watchdog():
                while not client._heartbeat_stop.wait(10):
                    last = self.snapshot()['last_message'] or opened_at
                    if time.time()-max(last,opened_at) > 90:
                        self.update(state='reconnecting', error='90 秒没有收到直播消息，正在重连')
                        client._stop()
                        break
            threading.Thread(target=watchdog,daemon=True,name='douyin-watchdog').start()
        client._on_open = on_open
        client._on_error = lambda ws, error: self.update(error=type(error).__name__+'：直播连接异常')
        closed = client._on_close
        def on_close(ws, code, message):
            closed(ws, code, message)
            if not self.stop_event.is_set():
                self.update(state='reconnecting')
        client._on_close = on_close

    def record_result(self, accepted, reason=""):
        with self.lock:
            self.data['accepted' if accepted else 'skipped'] += 1
            if not accepted:
                self.skip_reasons[reason or 'unknown'] += 1
