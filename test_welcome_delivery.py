import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import app as server
from welcome_delivery import next_delivery, finish_delivery


def event(number, created=100):
    return {'id':str(number), 'generation':0, 'created':created, 'people':1}


class DeliveryTests(unittest.TestCase):
    def test_poll_does_not_consume_and_finish_advances(self):
        events=[event(1),event(2)]
        self.assertEqual(next_delivery(events,'a',0,101)['id'],'1')
        self.assertEqual(next_delivery(events,'a',0,102)['id'],'1')
        finish_delivery(events[0],'finished')
        self.assertEqual(next_delivery(events,'a',0,103)['id'],'2')

    def test_retry_and_timeout_do_not_stall_next_person(self):
        events=[event(1),event(2)]
        first=next_delivery(events,'a',0,101)
        finish_delivery(first,'failed')
        self.assertEqual(next_delivery(events,'a',0,102)['attempt'],2)
        self.assertEqual(next_delivery(events,'a',0,143)['id'],'2')
        self.assertEqual(first['drop_reason'],'playback_failed')

    def test_expiration_and_pause_generation(self):
        events=[event(1,0),event(2,200)]
        self.assertEqual(next_delivery(events,'a',0,200)['id'],'2')
        self.assertEqual(events[0]['drop_reason'],'expired')
        self.assertIsNone(next_delivery(events,'a',1,201))


class BurstTests(unittest.IsolatedAsyncioTestCase):
    async def test_seven_people_form_three_groups_without_losing_names(self):
        server.pending=asyncio.Queue(maxsize=120)
        server.events.clear()
        server.generation=0
        server.muted=False
        server.diagnostics.clear()
        now=time.time()
        for i in range(7):
            await server.pending.put({'id':str(i),'text':'欢迎同学'+str(i), 'name':'同学'+str(i),
                'generation':0, 'received':now, 'source':'simulation'})
        class TTS:
            def __init__(self,*args,**kwargs):pass
            async def save(self,path):
                Path(path).write_bytes(b'test audio'*30)
        with tempfile.TemporaryDirectory() as folder, patch.object(server,'AUDIO',Path(folder)), \
                patch.object(server,'BATCH_WINDOW',0.01),patch('app.edge_tts.Communicate',TTS):
            task=asyncio.create_task(server.worker())
            await asyncio.wait_for(server.pending.join(),2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual([x['people'] for x in server.events],[3,3,1])
        self.assertEqual(sum(x['people'] for x in server.events),7)
        for i in range(7):
            self.assertTrue(any('同学'+str(i) in x['text'] for x in server.events))

    async def test_finish_ack_counts_people_and_blocked_does_not_drop(self):
        server.events.clear()
        server.diagnostics.clear()
        server.player_id='player'
        server.last_player=time.monotonic()
        server.events.append(dict(event(1,time.time()), source='simulation',text='欢迎',people=3,attempt=1))
        await server.playback_report(server.PlaybackReport(client='player',event='1',phase='blocked'))
        self.assertFalse(server.events[0].get('done',False))
        self.assertEqual(server.events[0]['attempt'],1)
        await server.playback_report(server.PlaybackReport(client='player',event='1',phase='finished'))
        await server.playback_report(server.PlaybackReport(client='player',event='1',phase='finished'))
        self.assertEqual(server.diagnostics['played_people'],3)
