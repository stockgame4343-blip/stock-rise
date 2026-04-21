"""Vercel serverless function — 일봉 OHLC 조회 프록시 (CORS 우회)

Naver chart API 를 서버 측에서 호출해 CORS 없이 브라우저에 전달.
GET /api/chart-ohlc?ticker=222080&from=20260413&to=20260421
→ [{localDate, openPrice, highPrice, lowPrice, closePrice, ...}]
"""
import json
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler


USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
NAVER_API_URL = 'https://api.stock.naver.com/chart/domestic/item/{ticker}/day?startDateTime={from_}&endDateTime={to_}'


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        params = parse_qs(urlparse(self.path).query)
        ticker = params.get('ticker', [None])[0]
        from_ = params.get('from', [None])[0]
        to_ = params.get('to', [None])[0]

        if not ticker or len(ticker) != 6 or not ticker.isdigit():
            self._respond(400, {'error': 'ticker 파라미터 필요 (6자리 숫자)'})
            return
        if not from_ or not to_ or not from_.isdigit() or not to_.isdigit():
            self._respond(400, {'error': 'from, to 파라미터 필요 (YYYYMMDD)'})
            return

        try:
            url = NAVER_API_URL.format(ticker=ticker, from_=from_, to_=to_)
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            self._respond(200, data)

        except urllib.error.HTTPError as e:
            self._respond(502, {'error': f'네이버 API 오류: {e.code}', 'ticker': ticker})
        except Exception as e:
            self._respond(502, {'error': str(e), 'ticker': ticker})

    def _respond(self, status, body):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode('utf-8'))
