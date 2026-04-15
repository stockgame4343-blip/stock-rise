"""Vercel serverless — 사용자 레이팅 동기화 (GitHub 백업)

POST: 전체 ratings 객체를 GitHub에 저장
GET:  현재 저장된 ratings 반환
"""
import json
import os
import urllib.request
import urllib.error
import base64
from http.server import BaseHTTPRequestHandler

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = os.environ.get('GITHUB_REPO', 'stockgame4343-blip/stock-rise')
FILE_PATH = 'public/data/user-ratings.json'
BRANCH = 'master'


def _github_api(method, url, data=None):
    headers = {
        'Authorization': f'Bearer {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'stock-rise-sync',
    }
    body = json.dumps(data).encode('utf-8') if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _get_current():
    url = f'https://api.github.com/repos/{REPO}/contents/{FILE_PATH}?ref={BRANCH}'
    try:
        result = _github_api('GET', url)
        content = base64.b64decode(result['content']).decode('utf-8')
        return json.loads(content), result['sha']
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}, None
        raise


def _save(ratings, sha, message):
    url = f'https://api.github.com/repos/{REPO}/contents/{FILE_PATH}'
    content = json.dumps(ratings, ensure_ascii=False, indent=2)
    encoded = base64.b64encode(content.encode('utf-8')).decode('ascii')
    data = {
        'message': message,
        'content': encoded,
        'branch': BRANCH,
    }
    if sha:
        data['sha'] = sha
    _github_api('PUT', url, data)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """서버에 저장된 ratings 반환"""
        if not GITHUB_TOKEN:
            self._respond(200, {})
            return
        try:
            ratings, _ = _get_current()
            self._respond(200, ratings)
        except Exception as e:
            self._respond(200, {})  # 실패해도 빈 객체 반환 (클라이언트 블로킹 방지)

    def do_POST(self):
        """ratings 전체를 서버에 저장"""
        try:
            length = int(self.headers.get('Content-Length', 0))
            ratings = json.loads(self.rfile.read(length).decode('utf-8'))
        except (json.JSONDecodeError, ValueError):
            self._respond(400, {'error': '잘못된 요청'})
            return

        if not GITHUB_TOKEN:
            self._respond(500, {'error': 'GITHUB_TOKEN 미설정'})
            return

        if not isinstance(ratings, dict):
            self._respond(400, {'error': 'ratings는 객체여야 합니다'})
            return

        try:
            _, sha = _get_current()
            _save(ratings, sha, 'sync: user ratings')
            self._respond(200, {'ok': True, 'count': len(ratings)})
        except Exception as e:
            self._respond(500, {'error': str(e)})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _respond(self, status, body):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode('utf-8'))
