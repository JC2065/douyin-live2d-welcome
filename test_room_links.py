import unittest
from types import SimpleNamespace as S
from room_links import extract_room_input, resolve_room, member_identity, protobuf_uint64


class Reply:
    def __init__(self, text='', location=None):
        self.text = text
        self.is_redirect = location is not None
        self.headers = {'Location': location}
    def raise_for_status(self):
        pass


class Session:
    def __init__(self, replies):
        self.replies, self.urls = iter(replies), []
    def get(self, url, **kwargs):
        self.urls.append(url)
        return next(self.replies)


class RoomTests(unittest.TestCase):
    def test_pasted_share_text(self):
        self.assertEqual(extract_room_input('直播分享 https://v.douyin.com/example/ 口令'), 'https://v.douyin.com/example/')
        self.assertEqual(resolve_room('123456789'), '123456789')
    def test_mobile_redirect_uses_web_id_not_internal_room(self):
        session = Session([Reply(location='https://webcast.amemv.com/douyin/webcast/reflow/99999'),
                           Reply(r'{\"roomIdStr\":\"99999\",\"webRid\":\"123456\"}')])
        self.assertEqual(resolve_room('https://v.douyin.com/example/',session),'123456')
    def test_reject_external_url_and_redirect_before_request(self):
        for url in ['http://live.douyin.com/123456', 'https://evil.example/123456',
                    'https://live.douyin.com.evil.example/', 'https://user@live.douyin.com/123456',
                    'https://live.douyin.com:8000/123456']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                extract_room_input(url)
        session=Session([Reply(location='http://127.0.0.1/private')])
        with self.assertRaises(ValueError):
            resolve_room('https://v.douyin.com/example/',session)
        self.assertEqual(len(session.urls),1)
    def test_missing_room(self):
        with self.assertRaises(ValueError):
            resolve_room('https://v.douyin.com/example/',Session([Reply('not a room')]))
    def test_stable_id_and_admin_events(self):
        event=S(user=S(id=0,nickname='同名用户'),user_id=0,user_open_id='stable',action=1,is_set_to_admin=False)
        self.assertEqual(member_identity(event),('douyin:stable','同名用户'))
        event.user_open_id=''
        self.assertIsNone(member_identity(event))

        event.user.id='0'
        self.assertIsNone(member_identity(event))
        event.user.id=99
        event.is_set_to_admin=True
        self.assertIsNone(member_identity(event))
        event.is_set_to_admin=False
        event.action=2
        self.assertIsNone(member_identity(event))

    def test_schema_mismatch_recovers_numeric_id(self):
        user=S(id='',nickname='同学',SerializeToString=lambda:b'\x1a\x04test\x08\xac\x02')
        event=S(user=user,user_id=0,user_open_id='',action=1,is_set_to_admin=False)
        self.assertEqual(member_identity(event),('douyin:300','同学'))
        self.assertEqual(protobuf_uint64(b'\x08\xac\x02',1),300)
        for raw in (b'\x08\x80', b'\x1a\x04t', b'\x00'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                protobuf_uint64(raw,1)

if __name__ == '__main__':
    unittest.main()
