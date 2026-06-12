"""Vercel serverless — 외부 cron에서 호출받아 GitHub Actions 트리거

5분마다 호출되면, 현재 KST 시각이 수집 스케줄에 해당할 때만 GitHub dispatch 발송.
주말/공휴일은 자동 스킵.

환경변수 필요:
  GITHUB_TOKEN — repo dispatch 권한 있는 PAT
  CRON_SECRET  — 무단 호출 방지용 시크릿
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler

# 휴일 캘린더 — collector/kr_holidays.py 단일 소스 import
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'collector'))
from kr_holidays import is_kr_holiday  # noqa: E402

KST = timezone(timedelta(hours=9))

STOCK_RISE_REPO = 'stockgame4343-blip/stock-rise'
WHYRISE_REPO = 'stockgame4343-blip/whyrise'
WHYRISE_EVENT = 'marketmap-intraday'   # whyrise build-history.yml repository_dispatch type
TRIGGER_WINDOW_MIN = 3                 # 슬롯 매칭 허용 오차 (외부 cron 호출 지연 흡수)
DISPATCH_TIMEOUT_SEC = 6               # 한 호출에 dispatch 2회 가능 → Vercel 함수 10s 한도 내 유지

# 본장 intraday 슬롯 — 09:06~15:21 15분 그리드 (26회)
# 외부 cron-job.org 를 5분 간격으로 호출해야 모든 슬롯이 발사된다 (시간당 1회면 :06만 발사)
_INTRADAY_SLOTS = [
    (h, m) for h in range(9, 16) for m in (6, 21, 36, 51)
    if (h, m) <= (15, 21)
]

# 트리거 스케줄 (KST 시:분, event_type, payload)
# - collect : 수집 워크플로우 (intraday/closing)
# - cards   : 카드뉴스 자동 생성 (pre/closing)
SCHEDULE = [
    # ── PRE 카드 다중 발사 — 외부 cron-job.org 한 번이라도 호출하면 PRE 카드 생성 ──
    (7,  30, 'cards',   {'series': 'pre'}),       # primary
    (8,  5,  'cards',   {'series': 'pre'}),       # 프리장 시작 직후
    (8,  35, 'cards',   {'series': 'pre'}),       # backup 1
    (9,  0,  'cards',   {'series': 'pre'}),       # 본장 시작 직전
] + [
    (h, m, 'collect', {'mode': 'intraday'}) for h, m in _INTRADAY_SLOTS
] + [
    # ── 마감 ──
    (15, 36, 'collect', {'mode': 'closing'}),
    (16, 0,  'cards',   {'series': 'closing'}),   # 1차 LEADER+CLOSE (마감 직후)
    (16, 6,  'collect', {'mode': 'closing'}),
    (20, 0,  'cards',   {'series': 'closing'}),   # 2차 — 데이터 안정화 후 덮어쓰기
]

# whyrise marketmap-intraday 슬롯 — GitHub native cron 만성 누락(하루 3회 수준) 보완.
# 같은 PAT 로 cross-repo dispatch, 실패해도 본 응답은 fail-soft (whyrise 는 자체 cron 백업 보유).
WHYRISE_SLOTS = _INTRADAY_SLOTS + [(15, 36), (16, 6)]


def _is_market_day(now_kst):
    if now_kst.weekday() >= 5:  # 토(5), 일(6)
        return False
    if is_kr_holiday(now_kst):  # 한국 공휴일(근로자의 날·어린이날·추석 등)
        return False
    return True


def _matches(now_kst, h, m):
    diff = abs((now_kst.hour * 60 + now_kst.minute) - (h * 60 + m))
    return diff <= TRIGGER_WINDOW_MIN


def _should_trigger(now_kst):
    """현재 시각이 스케줄에 해당하는지 확인.

    Returns:
        (event_type, payload) or None
    """
    for h, m, event_type, payload in SCHEDULE:
        if _matches(now_kst, h, m):
            return (event_type, payload)
    return None


def _whyrise_due(now_kst):
    return any(_matches(now_kst, h, m) for h, m in WHYRISE_SLOTS)


def _trigger_github(event_type, payload, repo=STOCK_RISE_REPO):
    """GitHub repository_dispatch 발송."""
    token = os.environ.get('GITHUB_TOKEN', '')
    if not token:
        return False, 'GITHUB_TOKEN not set'

    url = f'https://api.github.com/repos/{repo}/dispatches'
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
        resp = urllib.request.urlopen(req, timeout=DISPATCH_TIMEOUT_SEC)
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

        # ── force 파라미터 — 시각 무관 즉시 발사 (cron-job.org 1회 호출용 백업) ──
        # 사용 예: /api/cron-trigger?secret=XXX&force=cards-pre
        force = params.get('force', [None])[0]
        if force:
            FORCE_MAP = {
                'cards-pre':     ('cards',   {'series': 'pre'}),
                'cards-closing': ('cards',   {'series': 'closing'}),
                'collect-intra': ('collect', {'mode': 'intraday'}),
                'collect-close': ('collect', {'mode': 'closing'}),
            }
            slot = FORCE_MAP.get(force)
            if not slot:
                self._respond(400, {'error': f'unknown force value: {force}',
                                    'allowed': list(FORCE_MAP.keys())})
                return
            # 주말·공휴일 가드 (force 도 휴일은 차단)
            if now.weekday() >= 5:
                self._respond(200, {'status': 'skip', 'reason': 'weekend',
                                    'force': force})
                return
            if is_kr_holiday(now):
                self._respond(200, {'status': 'skip', 'reason': 'kr_holiday',
                                    'force': force,
                                    'time': now.strftime('%Y-%m-%d %H:%M KST')})
                return
            event_type, payload = slot
            ok, msg = _trigger_github(event_type, payload)
            self._respond(200 if ok else 500, {
                'status': 'forced' if ok else 'error',
                'event': event_type,
                'payload': payload,
                'time': now.strftime('%Y-%m-%d %H:%M KST'),
                'detail': msg,
            })
            return

        if not _is_market_day(now):
            self._respond(200, {
                'status': 'skip',
                'time': now.strftime('%Y-%m-%d %H:%M KST'),
                'reason': 'weekend' if now.weekday() >= 5 else 'kr_holiday',
            })
            return

        slot = _should_trigger(now)
        whyrise_due = _whyrise_due(now)

        if slot is None and not whyrise_due:
            self._respond(200, {
                'status': 'skip',
                'time': now.strftime('%Y-%m-%d %H:%M KST'),
                'reason': 'not scheduled',
            })
            return

        events = []
        ok_all = True
        if slot is not None:
            event_type, payload = slot
            ok, msg = _trigger_github(event_type, payload)
            ok_all = ok_all and ok
            events.append({'repo': 'stock-rise', 'event': event_type,
                           'payload': payload, 'ok': ok, 'detail': msg})

        # whyrise 는 fail-soft — PAT 범위 미포함 등으로 실패해도 본 트리거 상태를 오염시키지 않음
        if whyrise_due:
            ok, msg = _trigger_github(WHYRISE_EVENT, {}, repo=WHYRISE_REPO)
            events.append({'repo': 'whyrise', 'event': WHYRISE_EVENT,
                           'ok': ok, 'detail': msg})

        self._respond(200 if ok_all else 500, {
            'status': 'triggered' if ok_all else 'error',
            'events': events,
            'time': now.strftime('%Y-%m-%d %H:%M KST'),
        })

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
