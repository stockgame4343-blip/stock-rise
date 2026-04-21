"""넥스트장(NXT / Nextrade) 스냅샷 수집기

스케줄 (KST): 08:05, 16:05, 17:05, 18:05, 19:05, 20:05 (하루 6회, 월~금)
호출: .github/workflows/nxt-collect.yml 의 cron schedule

저장:
- public/data/nxt/YYYYMMDD_HHMM.json  (스냅샷)
- public/data/nxt/latest.json         (최신 복사본, 빠른 로드용)
- public/data/nxt/index.json          (스냅샷 메타 리스트, 역순)

각 스냅샷:
{
  "collected_at": "2026-04-21T20:05:03+09:00",
  "session": "postmarket",  // premarket / postmarket
  "setTime": "20260421200500",
  "totalCnt": 644,
  "gainers": [{ticker, name, market, price, change, changeRate, volume, tradingValue, creTime}, ...20],
  "losers":  [...20]
}
"""
import json
import logging
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'public', 'data', 'nxt')

NXT_URL = 'https://www.nextrade.co.kr/brdinfoTime/brdinfoTimeList.do'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://www.nextrade.co.kr/menu/transactionStatusMain/menuList.do',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
}
TOP_N = 20
KST = timezone(timedelta(hours=9))
RETENTION_DAYS = 60  # 스냅샷 보관 기간


def fetch_nxt_all():
    """넥스트레이드 전체 종목 시세 POST 호출."""
    body = b'pageIndex=1&pageUnit=2000'  # 여유있게 2000 (실제 ~644)
    req = urllib.request.Request(
        NXT_URL, data=body, headers=HEADERS, method='POST'
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def slim_item(x):
    """API 응답 → 슬림 스냅샷 형식."""
    code = (x.get('isuSrdCd') or '').lstrip('A')
    if not code:
        return None
    try:
        change_rate = float(x.get('upDownRate') or 0)
    except (TypeError, ValueError):
        return None
    return {
        'ticker': code,
        'name': x.get('isuAbwdNm', ''),
        'market': x.get('mktNm', ''),
        'price': int(x.get('curPrc') or 0),
        'change': int(x.get('contrastPrc') or 0),
        'changeRate': round(change_rate, 2),
        'volume': int(x.get('accTdQty') or 0),
        'tradingValue': int(x.get('accTrval') or 0),
        'creTime': x.get('creTime', ''),
    }


def classify_session(now_kst):
    """시각 기반 세션 판정."""
    h = now_kst.hour
    if h < 9:
        return 'premarket'
    if h >= 15:
        return 'postmarket'
    return 'regular'


def build_snapshot():
    """상승 TOP N + 하락 TOP N 스냅샷 구성."""
    now_kst = datetime.now(KST)
    raw = fetch_nxt_all()
    items_raw = raw.get('brdinfoTimeList') or []

    slim = [s for s in (slim_item(x) for x in items_raw) if s is not None]
    if not slim:
        raise RuntimeError('NXT 응답 비어있음')

    # 거래량이 없거나 창구 집계 이상치(0원) 제외
    slim = [s for s in slim if s['price'] > 0]

    gainers = sorted(slim, key=lambda s: s['changeRate'], reverse=True)[:TOP_N]
    losers = sorted(slim, key=lambda s: s['changeRate'])[:TOP_N]

    setTime = raw.get('setTime', '') or ''
    agg_dd = items_raw[0].get('aggDd', '') if items_raw else ''

    return {
        'collected_at': now_kst.isoformat(timespec='seconds'),
        'session': classify_session(now_kst),
        'aggDd': agg_dd,
        'setTime': setTime,
        'totalCnt': raw.get('totalCnt', len(slim)),
        'delayMinutes': 20,  # 넥스트레이드 표기 기준
        'gainers': gainers,
        'losers': losers,
    }


def enrich_reasons(snapshot):
    """당일 리포트의 theme_tag 를 ticker 기준으로 gainers/losers 에 부착.

    리포트 JSON 없으면 조용히 skip.
    """
    daily_dir = os.path.join(ROOT, 'public', 'data')
    date_key = (snapshot['aggDd'] or datetime.now(KST).strftime('%Y%m%d'))
    path = os.path.join(daily_dir, f'{date_key}.json')
    if not os.path.exists(path):
        return
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f'  reason 맵 로드 실패: {e}')
        return

    reason_map = {}
    for r in data.get('rankings', []):
        t = r.get('ticker')
        if not t:
            continue
        tag = r.get('theme_tag') or (r.get('theme_tags') or [None])[0] or r.get('sector')
        if tag:
            reason_map[t] = tag

    for bucket in ('gainers', 'losers'):
        for x in snapshot[bucket]:
            tag = reason_map.get(x['ticker'])
            if tag:
                x['reason'] = tag


def save_snapshot(snapshot):
    """스냅샷 3종 저장: 파일 + latest + index."""
    os.makedirs(DATA_DIR, exist_ok=True)
    # 파일명은 collected_at (KST) 기준으로 생성 — setTime 포맷이 변동적이라 불안정
    # collected_at: "2026-04-21T20:05:03+09:00"
    ca = snapshot.get('collected_at', '')
    try:
        dt = datetime.fromisoformat(ca)
        date_part = dt.strftime('%Y%m%d')
        time_part = dt.strftime('%H%M')
    except (TypeError, ValueError):
        now = datetime.now(KST)
        date_part = now.strftime('%Y%m%d')
        time_part = now.strftime('%H%M')
    snap_name = f'{date_part}_{time_part}.json'
    snap_path = os.path.join(DATA_DIR, snap_name)

    with open(snap_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    logger.info(f'  저장: {snap_name} (gainers {len(snapshot["gainers"])} / losers {len(snapshot["losers"])})')

    # latest
    latest_path = os.path.join(DATA_DIR, 'latest.json')
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    # index 갱신
    update_index(snap_name, snapshot)


def update_index(snap_name, snapshot):
    """index.json 에 스냅샷 메타 추가 (중복 방지, 최신 순)."""
    index_path = os.path.join(DATA_DIR, 'index.json')
    entries = []
    if os.path.exists(index_path):
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
        except Exception:
            entries = []

    # 기존 동일 파일명 제거
    entries = [e for e in entries if e.get('file') != snap_name]

    entries.insert(0, {
        'file': snap_name,
        'collected_at': snapshot['collected_at'],
        'session': snapshot['session'],
        'setTime': snapshot['setTime'],
    })

    # 최신 순 정렬 후 오래된 항목 정리 (RETENTION_DAYS 기준)
    entries.sort(key=lambda e: e.get('file', ''), reverse=True)
    entries = cleanup_old_entries(entries)

    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def cleanup_old_entries(entries):
    """RETENTION_DAYS 보다 오래된 스냅샷 파일 삭제 + index 에서 제거."""
    cutoff = (datetime.now(KST) - timedelta(days=RETENTION_DAYS)).strftime('%Y%m%d')
    kept = []
    for e in entries:
        fname = e.get('file', '')
        date_part = fname.split('_', 1)[0] if '_' in fname else ''
        if date_part and date_part < cutoff:
            path = os.path.join(DATA_DIR, fname)
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info(f'  정리: {fname} 삭제 ({RETENTION_DAYS}일 초과)')
                except OSError as ex:
                    logger.warning(f'  파일 삭제 실패 {fname}: {ex}')
        else:
            kept.append(e)
    return kept


def main():
    logger.info('===== NXT 스냅샷 수집 시작 =====')
    try:
        snapshot = build_snapshot()
        enrich_reasons(snapshot)
        save_snapshot(snapshot)
        logger.info(f'===== 완료: gainers TOP {len(snapshot["gainers"])} / losers TOP {len(snapshot["losers"])} =====')
        return 0
    except Exception as e:
        logger.error(f'NXT 수집 실패: {e}', exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
