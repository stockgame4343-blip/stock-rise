"""Vercel serverless — 외부 cron에서 호출받아 GitHub Actions 트리거

5분마다 호출되면, 현재 KST 시각이 수집 스케줄에 해당할 때만 GitHub dispatch 발송.
주말/공휴일은 자동 스킵.

환경변수 필요:
  GITHUB_TOKEN — repo dispatch 권한 있는 PAT
  CRON_SECRET  — 무단 호출 방지용 시크릿
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler

KST = timezone(timedelta(hours=9))

# 수집 스케줄 (KST 시:분, 모드)
# - intraday/closing: collect.yml (event_type=collect)
# - cards-pre/cards-close: cards 생성 워크플로우 (event_type=cards)
#   16:06 closing 워크플로우가 종료된 뒤 leader/close 카드를 함께 생성하므로
#   별도 16:06 cards 트리거는 두지 않음 (closing 워크플로우 chain 으로 처리).
SCHEDULE = [
    (7, 6, 'cards-pre'),
    (9, 6, 'intraday'),
    (10, 6, 'intraday'),
    (11, 6, 'intraday'),
    (12, 6, 'intraday'),
    (13, 6, 'intraday'),
    (14, 6, 'intraday'),
    (15, 36, 'closing'),
    (16, 6, 'closing'),
]


def _should_trigger(now_kst):
    """현재 시각이 스케줄에 해당하는지 확인."""
    if now_kst.weekday() >= 5:  # 토(5), 일(6)
        return None
    for h, m, mode in SCHEDULE:
        diff = abs((now_kst.hour * 60 + now_kst.minute) - (h * 60 + m))
        if diff <= 3:  # 3분 이내
            return mode
    return None


def _trigger_github(mode):
    """GitHub repository_dispatch 발송.

    mode 가 'cards-' 로 시작하면 카드 생성용 event_type='cards', mode 는 prefix 제거.
    그 외는 일반 수집용 event_type='collect'.
    """
    token = os.environ.get('GITHUB_TOKEN', '')
    if not token:
        return False, 'GITHUB_TOKEN not set'

    if mode.startswith('cards-'):
        event_type = 'cards'
        payload_mode = mode[len('cards-'):]   # 'pre' / 'close'
    else:
        event_type = 'collect'
        payload_mode = mode

    url = 'https://api.github.com/repos/stockgame4343-blip/stock-rise/dispatches'
    payload = json.dumps({
        'event_type': event_type,
        'client_payload': {'mode': payload_mode},
    }).encode('utf-8')

    req = urllib.request.Request(url, data=payload, method='POST', headers={
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+v3+json',
        'Content-Type': 'application/json',
        'User-Agent': 'stock-rise-cron',
    })

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return True, f'dispatched ({resp.status})'
    except urllib.error.HTTPError as e:
        return False, f'HTTP {e.code}: {e.read().decode()[:200]}'
    except Exception as e:
        return False, str(e)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(self.path).query)

        # 시크릿 검증
        secret = params.get('secret', [None])[0]
        expected = os.environ.get('CRON_SECRET', '')
        if not expected or secret != expected:
            self._respond(403, {'error': 'forbidden'})
            return

        now = datetime.now(KST)
        mode = _should_trigger(now)

        if mode is None:
            self._respond(200, {
                'status': 'skip',
                'time': now.strftime('%Y-%m-%d %H:%M KST'),
                'reason': 'not scheduled' if now.weekday() < 5 else 'weekend',
            })
            return

        ok, msg = _trigger_github(mode)
        self._respond(200 if ok else 500, {
            'status': 'triggered' if ok else 'error',
            'mode': mode,
            'time': now.strftime('%Y-%m-%d %H:%M KST'),
            'detail': msg,
        })

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
