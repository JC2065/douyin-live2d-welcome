"""Start the managed local connector from a terminal."""
import argparse
import requests


def main():
    parser = argparse.ArgumentParser(description='连接直播间；支持数字直播间号、标准链接和带引号的分享文字。')
    parser.add_argument('room', help='分享链接、分享文字或数字直播间号')
    args = parser.parse_args()
    try:
        response = requests.post('http://127.0.0.1:18765/api/connection/start', json={'room': args.room}, timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        parser.exit(1, '连接请求未成功，请确认本地服务已启动，且已有连接已断开。\n')
    print('已提交连接请求。请在本地控制台查看状态、启用声音或断开连接。')


if __name__ == '__main__':
    main()
