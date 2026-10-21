"""Optional real-room bridge. Never runs unless explicitly started with a room ID."""
import argparse
import logging
import re
import sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'vendor/douyin-ai-assist'))


def main():
    parser = argparse.ArgumentParser(description='开播后手动连接抖音进房事件；不发送弹幕。')
    parser.add_argument('room', help='数字直播间号或 https://live.douyin.com/数字')
    args = parser.parse_args()
    match = re.fullmatch(r'(?:https://live\.douyin\.com/)?(\d+)/?', args.room.strip())
    if not match:
        parser.error('请提供数字直播间号或标准直播间链接')
    from douyin_ai_assist import config
    config.COLD_FIELD_ENABLED = False
    config.TTS_ENABLED = False
    from douyin_ai_assist.live_client import DouYinLive
    from douyin_ai_assist.douyin.douyin_pb2 import MemberMessage
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    client = DouYinLive(match.group(1))
    def member(payload):
        event = MemberMessage()
        event.ParseFromString(payload)
        # Only explicit entrance events; skip admin/member-state changes.
        if event.action != 1:
            return
        uid = str(event.user.id or event.user_id or event.user_open_id or '')
        if not uid or uid == '0':
            return
        try:
            reply = requests.post('http://127.0.0.1:18765/api/enter', json={
                'uid': 'douyin:'+uid, 'name': (event.user.nickname or '新朋友')[:30]
            }, timeout=3)
            reply.raise_for_status()
            logging.info('进房处理：%s', reply.json())
        except requests.RequestException as exc:
            logging.error('本地欢迎服务不可用：%s', exc)
    # Do not run upstream AI/chat/gift/idle handlers.
    client._parser._handlers = {'WebcastMemberMessage': member,
                               'WebcastControlMessage': client._parser._handle_control}
    print('仅监听进房；请先在控制台启用角色声音。按 Ctrl+C 停止。')
    try:
        client.start()
    except KeyboardInterrupt:
        pass
    finally:
        client._stop()


if __name__ == '__main__':
    main()
