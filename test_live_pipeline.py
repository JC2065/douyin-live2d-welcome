import asyncio
import time
import unittest
from unittest.mock import patch
import app as server
from welcome import WelcomeGate


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        server.gate = WelcomeGate()
        server.pending = asyncio.Queue(maxsize=2)
        server.events.clear()
        server.muted = False
        server.generation = 0
        server.last_player = 0
        server.player_id = None

    async def test_unready_player_does_not_start_cooldown(self):
        entry = server.Entry(uid='user', name='同学')
        self.assertFalse((await server.enter(entry))['accepted'])
        server.last_player = time.monotonic()
        self.assertTrue((await server.enter(entry))['accepted'])
        self.assertFalse((await server.enter(entry))['accepted'])

    async def test_live_source_and_pause_clear_pending(self):
        server.last_player = time.monotonic()
        result = await server.enter(server.Entry(uid='douyin:123', name='同学', source='douyin'))
        self.assertTrue(result['accepted'])
        self.assertEqual(server.pending._queue[0]['source'], 'douyin')
        server.events.append({'seq':1})
        await server.mute()
        self.assertTrue(server.pending.empty())
        self.assertFalse(server.events)
        self.assertEqual(server.generation,1)
        self.assertFalse((await server.enter(server.Entry(uid='another',name='同学')))['accepted'])

    async def test_stale_items_do_not_call_tts(self):
        await server.pending.put({'generation':0, 'received':time.time()-26})
        with patch('app.edge_tts.Communicate') as tts:
            task=asyncio.create_task(server.worker())
            await server.pending.join()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            tts.assert_not_called()

    async def test_player_lease_and_restart_identifier(self):
        first = server.poll(client='first')
        self.assertFalse(first['busy'])
        self.assertEqual(first['server_id'],server.server_id)
        self.assertTrue(server.poll(client='second')['busy'])
        server.last_player-=6
        self.assertFalse(server.poll(client='second')['busy'])

    async def test_full_queue_does_not_consume_cooldown(self):
        server.last_player = time.monotonic()
        await server.pending.put({})
        await server.pending.put({})
        entry=server.Entry(uid='new',name='同学')
        self.assertFalse((await server.enter(entry))['accepted'])
        server.pending.get_nowait()
        server.pending.task_done()
        self.assertTrue((await server.enter(entry))['accepted'])

if __name__=='__main__':
    unittest.main()
