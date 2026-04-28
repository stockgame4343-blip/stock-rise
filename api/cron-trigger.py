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

# 트리거 스케줄 (KST 시:분, event_type, payload)
# - collect : 수집 워크플로우 (intraday/closing)
# - cards   : 카드뉴스 자동 생성 (pre/closing)
SCHEDULE = [
    (8,  5,  'cards',   {'series': 'pre'}),       # 프리장 시작 직후 PRE 미리 생성 (본장 시작 전 노출)
    (9,  6,  'collect', {'mode': 'intraday'}),    # 리포트 첫 업데이트 — PRE 도 함께 노출
    (10, 6,  'collect', {'mode': 'intraday'}),
    (11, 6,  'collect', {'mode': 'intraday'}),
    (12, 6,  'collect', {'mode': 'intraday'}),
    (13, 6,  'collect', {'mode': 'intraday'}),
    (14, 6,  'collect', {'mode': 'intraday'}),
    (15, 36, 'collect', {'mode': 'closing'}),
    (16, 0,  'cards',   {'series': 'closing'}),   # 1차 LEADER+CLOSE (마감 직후)
    (16, 6,  'collect', {'mode': 'closing'}),
    (20, 0,  'cards',   {'series': 'closing'}),   # 2차 — 데이터 안정화 후 덮어쓰기
]


def _should_trigger(now_kst):
    """현재 시각이 스케줄에 해당하는지 확인.

    Returns:
        (event_type, payload) or None
    """
    if now_kst.weekday() >= 5:  # 토(5), 일(6)
        return None
    for h, m, event_type, payload in SCHEDULE:
        diff = abs((now_kst.hour * 60 + now_kst.minute) - (h * 60 + m))
        if diff <= 3:  # 3분 이내
            return (event_type, payload)
    return None


def _trigger_github(event_type, payload):
    """GitHub repository_dispatch 발송."""
    token = os.environ.get('GITHUB_TOKEN', '')
    if not token:
        return False, 'GITHUB_TOKEN not set'

    url = 'https://api.github.com/repos/stockgame4343-blip/stock-rise/dispatches'
    body = json.dumps({
        'event_type': event_type,
        'client_payload': payload,
    }).encode('utf-8')

    req = urllib.request.Request(url, data=body, method='POST', headers={
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
        slot = _should_trigger(now)

        if slot is None:
            self._respond(200, {
                'status': 'skip',
                'time': now.strftime('%Y-%m-%d %H:%M KST'),
                'reason': 'not scheduled' if now.weekday() < 5 else 'weekend',
            })
            return

        event_type, payload = slot
        ok, msg = _trigger_github(event_type, payload)
        self._respond(200 if ok else 500, {
            'status': 'triggered' if ok else 'error',
            'event': event_type,
            'payload': payload,
            'time': now.strftime('%Y-%m-%d %H:%M KST'),
            'detail': msg,
        })

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
