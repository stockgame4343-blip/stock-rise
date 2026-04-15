"""Vercel serverless — 태그 피드백 수신 (사용자 수정/삭제 학습)

브라우저에서 태그를 수정/삭제하면 이 API로 전송.
GitHub API를 통해 collector/tag_feedback.json을 업데이트하여
다음 수집 때 반영한다.

- edit: 종목 태그 수동 지정 → overrides에 저장
- delete: 잘못된 태그 삭제 → bad_tags에 추가 (다시 생성 방지)
- reset: 수동 지정 해제 → overrides에서 제거
"""
import json
import os
import urllib.request
import urllib.error
import base64
from http.server import BaseHTTPRequestHandler

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = os.environ.get('GITHUB_REPO', 'stockgame4343-blip/stock-rise')
FILE_PATH = 'collector/tag_feedback.json'
BRANCH = 'master'


def _github_api(method, url, data=None):
    """GitHub REST API 호출"""
    headers = {
        'Authorization': f'Bearer {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'stock-rise-feedback',
    }
    body = json.dumps(data).encode('utf-8') if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _get_current_feedback():
    """GitHub에서 현재 tag_feedback.json 읽기"""
    url = f'https://api.github.com/repos/{REPO}/contents/{FILE_PATH}?ref={BRANCH}'
    try:
        result = _github_api('GET', url)
        content = base64.b64decode(result['content']).decode('utf-8')
        sha = result['sha']
        feedback = json.loads(content)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # 파일 없으면 빈 구조
            return {'overrides': {}, 'bad_tags': []}, None
        raise
    return feedback, sha


def _save_feedback(feedback, sha, message):
    """GitHub에 tag_feedback.json 커밋"""
    url = f'https://api.github.com/repos/{REPO}/contents/{FILE_PATH}'
    content = json.dumps(feedback, ensure_ascii=False, indent=2)
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
    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8'))
        except (json.JSONDecodeError, ValueError):
            self._respond(400, {'error': '잘못된 요청'})
            return

        if not GITHUB_TOKEN:
            self._respond(500, {'error': 'GITHUB_TOKEN 미설정'})
            return

        action = body.get('action')
        ticker = body.get('ticker', '')
        tag = body.get('tag', '')
        original_tag = body.get('original_tag', '')

        if not action or not ticker:
            self._respond(400, {'error': 'action, ticker 필수'})
            return

        try:
            feedback, sha = _get_current_feedback()

            if 'overrides' not in feedback:
                feedback['overrides'] = {}
            if 'bad_tags' not in feedback:
                feedback['bad_tags'] = []

            if action == 'edit' and tag:
                # 수동 수정: 이 종목은 다음부터 이 태그 우선
                feedback['overrides'][ticker] = tag
                msg = f'tag-feedback: {ticker} → {tag}'

            elif action == 'delete':
                # 태그 삭제: 잘못된 태그로 학습
                if original_tag and original_tag not in feedback['bad_tags']:
                    feedback['bad_tags'].append(original_tag)
                # overrides에 있었으면 제거
                feedback['overrides'].pop(ticker, None)
                msg = f'tag-feedback: {ticker} bad_tag "{original_tag}"'

            elif action == 'reset':
                # 자동 태그로 복원
                feedback['overrides'].pop(ticker, None)
                msg = f'tag-feedback: {ticker} reset'

            else:
                self._respond(400, {'error': f'알 수 없는 action: {action}'})
                return

            _save_feedback(feedback, sha, msg)
            self._respond(200, {'ok': True, 'action': action, 'ticker': ticker})

        except Exception as e:
            self._respond(500, {'error': str(e)})

    def do_OPTIONS(self):
        """CORS preflight"""
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _respond(self, status, body):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode('utf-8'))
