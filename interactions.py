"""Normalize real stream events into short narration; no LLM calls."""
import asyncio
import re
import time
from collections import OrderedDict
from room_links import protobuf_uint64


def clean_name(name):
    clean = ''.join(c for c in name if c.isalnum() or c in ' _-')[:16].strip()
    if not clean:
        return '新朋友'
    return clean + '同学' if '*' in name else clean


def user_id(user):
    raw = None
    try:
        raw = protobuf_uint64(user.SerializeToString(),1)
    except (ValueError, AttributeError):
        pass
    return str(next((x for x in (getattr(user,'id',''),raw,getattr(user,'id_str',''),getattr(user,'sec_uid',''))
                     if x and str(x)!='0'), ''))


def activity_payload(event, kind):
    name = clean_name(event.user.nickname or '新朋友')
    uid = user_id(event.user)
    msg_id = str(getattr(event.common,'msg_id',0) or '')
    result = {'kind':kind,'name':name,'uid':uid,'event_id':msg_id}
    if kind == 'chat':
        text = re.sub(r'https?://\S+','一个链接',event.content)
        text = ''.join(c for c in text if c.isprintable()).strip()
        if not text:
            return None
        clipped = len(text)>100
        result['text'] = f'{name}说：{text[:100]}' + ('，后面内容请看评论区。' if clipped else '')
    elif kind == 'gift':
        if event.gift.combo and event.repeat_end != 1:
            return None  # Only announce the settled total of a combo.
        gift = ''.join(c for c in (event.gift.name or '礼物') if c.isprintable())[:25]
        count = max(1,event.repeat_count,event.combo_count,event.group_count)
        result['text'] = f'感谢{name}送出的{gift}，共{count}个！'
        if event.gift.combo and event.group_id:
            result['event_id'] = f'combo:{uid}:{event.gift_id}:{event.group_id}'
    elif kind == 'like':
        result['text'] = f'感谢{name}的点赞！'
        result['count'] = max(1,event.count)
    else:
        return None
    return result


class ActivityLimiter:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.seen = OrderedDict()

    def allow(self, event):
        now = self.clock()
        if event['kind']=='like':
            key=('like',event['uid'] or event['name'])
            ttl=8
        else:
            key=(event['kind'],event['event_id'] or (event['uid'],event['text']))
            ttl=120 if event['event_id'] else 5
        last=self.seen.get(key)
        if last is not None and now-last < ttl:
            return False
        self.seen[key]=now
        self.seen.move_to_end(key)
        while len(self.seen)>500:
            self.seen.popitem(last=False)
        return True


class SpeechQueue(asyncio.Queue):
    """FIFO within kind; gifts/comments precede unprocessed welcomes and likes."""
    PRIORITY={'gift':0,'chat':1,'welcome':2,'like':3}
    def _put(self,item):
        priority=self.PRIORITY.get(item.get('kind','welcome'),2)
        for index,other in enumerate(self._queue):
            if priority < self.PRIORITY.get(other.get('kind','welcome'),2):
                self._queue.insert(index,item)
                return
        self._queue.append(item)
