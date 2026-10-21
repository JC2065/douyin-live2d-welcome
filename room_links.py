"""Resolve pasted Douyin share text without retaining tracking parameters."""
import re
from urllib.parse import urlsplit, urljoin

ALLOWED_HOSTS = {'v.douyin.com', 'live.douyin.com', 'webcast.amemv.com'}
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'


def extract_room_input(value):
    value = value.strip()
    if re.fullmatch(r'\d{5,22}', value):
        return f'https://live.douyin.com/{value}'
    match = re.search(r'https://[^\s<>"，]+', value)
    if not match:
        raise ValueError('请粘贴抖音分享链接或数字直播间号')
    url = match.group().rstrip('。；;!！')
    parts = urlsplit(url)
    if parts.hostname not in ALLOWED_HOSTS or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError('只支持抖音官方直播及分享链接')
    return url


def resolve_room(value, session=None):
    url = extract_room_input(value)
    parts = urlsplit(url)
    if parts.hostname == 'live.douyin.com' and re.fullmatch(r'/\d+/?', parts.path):
        return parts.path.strip('/')
    if session is None:
        import requests
        session = requests.Session()
    for _ in range(6):
        extract_room_input(url)  # Validate each redirect before requesting it.
        response = session.get(url, headers={'User-Agent': UA}, timeout=15, allow_redirects=False)
        response.raise_for_status()
        if response.is_redirect:
            url = urljoin(url, response.headers['Location'])
            continue
        parts = urlsplit(url)
        if parts.hostname == 'live.douyin.com' and re.fullmatch(r'/\d+/?', parts.path):
            return parts.path.strip('/')
        text = response.text.replace('\\"', '"')
        match = re.search(r'"webRid"\s*:\s*"(\d+)"', text)
        if match:
            return match.group(1)
        raise ValueError('未找到网页直播间号，请确认链接有效且正在直播')
    raise ValueError('分享链接跳转过多，请改用直播间网页地址')


def protobuf_uint64(data, field_number):
    """Read a known integer field when an upstream schema has the wrong wire type."""
    def varint(offset):
        value = 0
        for shift in range(0, 70, 7):
            if offset >= len(data):
                raise ValueError('truncated protobuf')
            byte = data[offset]
            offset += 1
            value |= (byte & 127) << shift
            if not byte & 128:
                if value >= 1 << 64:
                    raise ValueError('invalid uint64')
                return value, offset
        raise ValueError('invalid varint')
    offset = 0
    while offset < len(data):
        key, offset = varint(offset)
        number, wire = key >> 3, key & 7
        if not number:
            raise ValueError('invalid field')
        if wire == 0:
            value, offset = varint(offset)
            if number == field_number:
                return value
        elif wire == 1:
            offset += 8
        elif wire == 2:
            size, offset = varint(offset)
            offset += size
        elif wire == 5:
            offset += 4
        else:
            raise ValueError('unsupported wire type')
        if offset > len(data):
            raise ValueError('truncated field')
    return None


def member_identity(event):
    # Stable ID only; never collapse all missing IDs or use display names as IDs.
    raw_id = None
    if not event.user.id or str(event.user.id) == '0':
        raw = getattr(event.user, 'SerializeToString', lambda:b'')()
        try:
            raw_id = protobuf_uint64(raw, 1)
        except ValueError:
            pass
    uid = next((value for value in (event.user.id, raw_id, getattr(event.user, 'id_str', ''),
                                    event.user_id, event.user_open_id, getattr(event.user, 'sec_uid', ''))
                if value and str(value) != '0'), None)
    if not uid or not event.user.nickname:
        return None
    if event.action != 1 or event.is_set_to_admin:
        return None
    return 'douyin:' + str(uid), event.user.nickname[:30]
