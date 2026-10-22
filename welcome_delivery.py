"""One acknowledged greeting at a time; polling never consumes a greeting."""
import time

PLAYER_LEASE_SECONDS = 30
EVENT_MAX_AGE = 120
DELIVERY_TIMEOUT = 40
MAX_ATTEMPTS = 2


def next_delivery(events, client, generation, now=None):
    now = time.time() if now is None else now
    available = []
    for event in events:
        if event.get('done') or event['generation'] != generation:
            continue
        if now-event['created'] > EVENT_MAX_AGE:
            event['done'] = True
            event['drop_reason'] = 'expired'
            continue
        if event.get('owner') and now-event['delivered'] >= DELIVERY_TIMEOUT:
            event['attempt'] = event.get('attempt',1)+1
            event.pop('owner',None)
        if event.get('attempt',1) > MAX_ATTEMPTS:
            event['done'] = True
            event['drop_reason'] = 'playback_failed'
            continue
        available.append(event)
    if not available:
        return None
    # Finish an active utterance first; otherwise prioritize gifts and comments.
    active = next((event for event in available if event.get('owner')),None)
    priorities = {'gift':0,'chat':1,'welcome':2,'like':3}
    event = active or min(available,key=lambda item:priorities.get(item.get('kind','welcome'),2))
    if event.get('owner') != client:
        event['owner'] = client
        event['delivered'] = now
        event.setdefault('attempt',1)
    return event


def finish_delivery(event, phase):
    if phase == 'finished':
        event['done'] = True
    elif phase == 'failed':
        event['attempt'] = event.get('attempt',1)+1
        event.pop('owner',None)


def batch_text(items):
    if len(items) == 1:
        return items[0]['text']
    names = '、'.join(item['name'][:8] for item in items)
    if items[0].get('kind') == 'like':
        return f'感谢{names}的点赞！'
    return f'欢迎{names}，一起聊技术吧！'
