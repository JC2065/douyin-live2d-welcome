import asyncio
import unittest
from types import SimpleNamespace as S
from unittest.mock import patch
import app as server
from interactions import activity_payload, ActivityLimiter, SpeechQueue
from welcome_delivery import next_delivery, finish_delivery


def message():
    return S(user=S(id='42',nickname='技术同学'),common=S(msg_id=123))


class NormalizeTests(unittest.TestCase):
    def test_comment_is_read_and_link_shortened(self):
        event=message()
        event.content='怎么部署 https://example.com/long/path'
        data=activity_payload(event,'chat')
        self.assertIn('技术同学说：怎么部署 一个链接',data['text'])
        self.assertEqual(data['uid'],'42')

    def test_gift_combo_only_announces_final_total(self):
        event=message()
        event.gift=S(combo=True,name='小心心')
        event.gift_id=10
        event.group_id=20
        event.repeat_count=5
        event.combo_count=5
        event.group_count=1
        event.repeat_end=0
        self.assertIsNone(activity_payload(event,'gift'))
        event.repeat_end=1
        result=activity_payload(event,'gift')
        self.assertIn('小心心，共5个',result['text'])
        self.assertEqual(result['event_id'],'combo:42:10:20')

    def test_like_cooldown_does_not_suppress_other_people(self):
        now=[0]
        limiter=ActivityLimiter(lambda:now[0])
        data={'kind':'like','uid':'42','name':'同学'}
        self.assertTrue(limiter.allow(data))
        now[0]=7
        self.assertFalse(limiter.allow(data))
        self.assertTrue(limiter.allow(dict(data,uid='other')))
        now[0]=8
        self.assertTrue(limiter.allow(data))

    def test_unique_comment_ids_and_combo_replay(self):
        limiter=ActivityLimiter(lambda:1)
        comment={'kind':'chat','event_id':'1','uid':'42','text':'你好'}
        self.assertTrue(limiter.allow(comment))
        self.assertFalse(limiter.allow(comment))
        self.assertTrue(limiter.allow(dict(comment,event_id='2')))

    def test_priority_preserves_active_speech(self):
        events=[dict(id=str(i),generation=0,created=100,kind=kind)
                for i,kind in enumerate(['welcome','chat','gift','like'])]
        gift=next_delivery(events,'player',0,101)
        self.assertEqual(gift['kind'],'gift')
        self.assertEqual(next_delivery(events,'player',0,102)['id'],gift['id'])
        finish_delivery(gift,'finished')
        self.assertEqual(next_delivery(events,'player',0,103)['kind'],'chat')


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_gift_and_comment_priority(self):
        queue=SpeechQueue()
        for kind in ('like','welcome','chat','gift','chat'):
            queue.put_nowait({'kind':kind})
        self.assertEqual([(await queue.get())['kind'] for _ in range(5)],['gift','chat','chat','welcome','like'])

    async def test_only_enabled_interactions_are_enqueued(self):
        server.pending=SpeechQueue()
        server.muted=False
        import time
        server.last_player=time.monotonic()
        server.activity_limiter=ActivityLimiter()
        data={'kind':'chat','uid':'42','name':'同学','event_id':'123','text':'同学说你好'}
        with patch.dict(server.interaction_settings,{'chat':False}):
            await server.activity_enter(data)
            self.assertTrue(server.pending.empty())
        with patch.dict(server.interaction_settings,{'chat':True}):
            await server.activity_enter(data)
            self.assertEqual((await server.pending.get())['kind'],'chat')
