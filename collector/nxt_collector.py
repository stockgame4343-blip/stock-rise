"""넥스트장(NXT / Nextrade) 스냅샷 수집기

스케줄 (KST): 16:05, 17:05, 18:05, 19:05, 20:05 (하루 5회, 월~금 애프터마켓)
- 프리마켓(08:05) 은 제외: 기준가가 전일 종가라 포스트마켓의 "NXT 세션 한정 변동" 과 의미 충돌
호출: .github/workflows/nxt-collect.yml 의 cron schedule

저장:
- public/data/nxt/YYYYMMDD.json       (일별 1개, 같은 날 여러 번 돌면 overwrite)
- public/data/nxt/latest.json         (최신 복사본)
- public/data/nxt/index.json          (날짜 메타 리스트, 역순)

각 스냅샷 기본 필드:
- ticker, name, market (KOSPI/KOSDAQ)
- price, change, changeRate (NXT 가격, 전일 종가 대비)
- volume, tradingValue (NXT 누적거래량/거래대금)
- nxtChange, nxtChangeRate, krxClose (본장 종가 대비 NXT 세션 한정 변동)
- marketCap (시가총액), krxTradingValue (본장 거래대금)
- sector (업종명), themes (테마 목록, 배열)
"""
import concurrent.futures
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


_NAVER_API_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
}
_NAVER_MARKETVALUE_URL = (
    'https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize=100'
)


def _fetch_marketvalue_page(market, page, timeout=10):
    """Naver marketValue 엔드포인트 한 페이지 호출 → stocks 배열."""
    url = _NAVER_MARKETVALUE_URL.format(market=market, page=page)
    req = urllib.request.Request(url, headers=_NAVER_API_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode('utf-8')) or {}
    return data.get('stocks') or [], int(data.get('totalCount') or 0)


def fetch_all_krx_details(max_workers=10):
    """KOSPI + KOSDAQ 전 종목(ETF 포함) 상세: {ticker: {krxClose, marketCap, krxTradingValue}}.

    `stocks/marketValue/{market}` 페이지네이션 (100개/page).
    시총 순이라 NXT 대형주까지 확실히 커버.
    병렬 fetch 로 ~55 페이지 → 2~3초.
    """
    result = {}
    for market in ['KOSPI', 'KOSDAQ']:
        try:
            first, total = _fetch_marketvalue_page(market, 1)
        except Exception as e:
            logger.warning(f'  {market} page 1 실패: {e}')
            continue
        for s in first:
            _absorb_details(result, s)
        if total <= 100:
            continue
        last_page = (total + 99) // 100
        pages = list(range(2, last_page + 1))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_fetch_marketvalue_page, market, p): p for p in pages}
            for fut in concurrent.futures.as_completed(futures):
                p = futures[fut]
                try:
                    stocks, _ = fut.result()
                    for s in stocks:
                        _absorb_details(result, s)
                except Exception as e:
                    logger.warning(f'  {market} page {p} 실패: {e}')
        logger.info(f'  {market}: totalCount={total}, 매핑 {sum(1 for r in result.values() if r.get("_market") == market)}개')
    return result


def _absorb_details(result, s):
    """_fetch_marketvalue_page 반환 항목 → result dict 에 흡수."""
    t = s.get('itemCode')
    if not t:
        return
    try:
        krx_close = int(s.get('closePriceRaw') or 0)
    except (TypeError, ValueError):
        krx_close = 0
    try:
        market_cap = int(s.get('marketValueRaw') or 0)
    except (TypeError, ValueError):
        market_cap = 0
    try:
        trading_value = int(s.get('accumulatedTradingValueRaw') or 0)
    except (TypeError, ValueError):
        trading_value = 0
    if krx_close <= 0 and market_cap <= 0:
        return
    result[t] = {
        'krxClose': krx_close,
        'marketCap': market_cap,
        'krxTradingValue': trading_value,
        '_market': (s.get('stockExchangeType') or {}).get('nameEng') or '',
    }


def load_sector_theme_mapping():
    """naver_mapping.json 로드 → (industries, themes).

    industries: {ticker: {name, no}}
    themes:     {ticker: [{no, name}, ...]}
    """
    path = os.path.join(ROOT, 'collector', 'naver_mapping.json')
    if not os.path.exists(path):
        logger.warning('  naver_mapping.json 없음 → 섹터/테마 스킵')
        return {}, {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            m = json.load(f)
        return m.get('industries') or {}, m.get('themes') or {}
    except Exception as e:
        logger.warning(f'  naver_mapping 로드 실패: {e}')
        return {}, {}


def enrich_nxt_full(items, krx_details, industries, themes_map):
    """각 NXT item 에 풀 메타 부착.

    - NXT 세션 변동: nxtChange/nxtChangeRate/krxClose
    - 본장 정보: marketCap, krxTradingValue
    - 매핑: sector (업종명), themes (테마명 리스트, 중복 제거)
    """
    for x in items:
        t = x['ticker']
        d = krx_details.get(t) or {}
        krx_close = d.get('krxClose') or 0
        if krx_close > 0:
            nxt_change = x['price'] - krx_close
            x['krxClose'] = krx_close
            x['nxtChange'] = nxt_change
            x['nxtChangeRate'] = round((nxt_change / krx_close) * 100, 2)
        mc = d.get('marketCap') or 0
        if mc > 0:
            x['marketCap'] = mc
        ktv = d.get('krxTradingValue') or 0
        if ktv > 0:
            x['krxTradingValue'] = ktv

        ind = industries.get(t) or {}
        if ind.get('name'):
            x['sector'] = ind['name']

        theme_list = themes_map.get(t) or []
        names = []
        seen = set()
        for th in theme_list:
            n = (th or {}).get('name') if isinstance(th, dict) else None
            if n and n not in seen:
                seen.add(n)
                names.append(n)
        if names:
            x['themes'] = names
    return items


def build_snapshot():
    """상승 TOP N + 하락 TOP N 스냅샷 구성.

    포스트마켓 세션을 가정 (프리마켓은 cron 에서 제외). 정규장 중 수동 실행 시에도
    동일 로직이 동작하지만, 정규장 가격이 KRX 종가에 반영되지 않아 nxtChangeRate 는
    0 근처로 나올 수 있음.
    """
    now_kst = datetime.now(KST)
    raw = fetch_nxt_all()
    items_raw = raw.get('brdinfoTimeList') or []

    slim = [s for s in (slim_item(x) for x in items_raw) if s is not None]
    if not slim:
        raise RuntimeError('NXT 응답 비어있음')

    # 거래량이 없거나 창구 집계 이상치(0원) 제외
    slim = [s for s in slim if s['price'] > 0]

    session = classify_session(now_kst)

    # KOSPI + KOSDAQ 전 종목 상세 (종가/시총/거래대금)
    logger.info('  KRX 전 종목 상세 fetch 시작 (marketValue 페이지네이션)...')
    krx_details = fetch_all_krx_details()
    logger.info(f'  KRX 상세 매핑: {len(krx_details)}개 종목')

    # 섹터/테마 매핑
    industries, themes_map = load_sector_theme_mapping()
    logger.info(f'  섹터 매핑: {len(industries)}개, 테마 매핑: {len(themes_map)}개')

    enrich_nxt_full(slim, krx_details, industries, themes_map)

    # 매칭 카운트 (관찰용)
    matched_close = sum(1 for s in slim if s.get('krxClose'))
    matched_sector = sum(1 for s in slim if s.get('sector'))
    matched_themes = sum(1 for s in slim if s.get('themes'))
    logger.info(
        f'  enrich 결과: KRX종가 {matched_close}/{len(slim)} · '
        f'섹터 {matched_sector}/{len(slim)} · 테마 {matched_themes}/{len(slim)}'
    )

    nxt_change_enriched = matched_close > 0

    # 정렬: nxtChangeRate 우선, 없으면 changeRate
    def sort_val(s):
        v = s.get('nxtChangeRate')
        return v if v is not None else s.get('changeRate', 0)
    if nxt_change_enriched:
        gainers = sorted(slim, key=sort_val, reverse=True)[:TOP_N]
        losers = sorted(slim, key=sort_val)[:TOP_N]
    else:
        gainers = sorted(slim, key=lambda s: s.get('changeRate', 0), reverse=True)[:TOP_N]
        losers = sorted(slim, key=lambda s: s.get('changeRate', 0))[:TOP_N]

    setTime = raw.get('setTime', '') or ''
    agg_dd = items_raw[0].get('aggDd', '') if items_raw else ''

    return {
        'collected_at': now_kst.isoformat(timespec='seconds'),
        'session': session,
        'aggDd': agg_dd,
        'setTime': setTime,
        'totalCnt': raw.get('totalCnt', len(slim)),
        'delayMinutes': 20,  # 넥스트레이드 표기 기준
        'nxtChangeEnriched': nxt_change_enriched,
        'gainers': gainers,
        'losers': losers,
    }


def save_snapshot(snapshot):
    """스냅샷 저장: 일별 1개 (하루에 여러 번 수집되면 overwrite) + latest + index.

    파일명은 KST 날짜 기준 `YYYYMMDD.json`. 같은 날 여러 번 돌면 덮어씀 → 항상 해당 일자의 최신.
    snapshot['last_updated'] 에 "HH:MM" 부착해 UI 에서 마지막 업데이트 시각으로 표시.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    ca = snapshot.get('collected_at', '')
    try:
        dt = datetime.fromisoformat(ca)
        date_part = dt.strftime('%Y%m%d')
        time_label = dt.strftime('%H:%M')
    except (TypeError, ValueError):
        now = datetime.now(KST)
        date_part = now.strftime('%Y%m%d')
        time_label = now.strftime('%H:%M')

    # UI 표시용: 마지막 업데이트 시각
    snapshot['last_updated'] = time_label
    snapshot['date'] = date_part

    snap_name = f'{date_part}.json'
    snap_path = os.path.join(DATA_DIR, snap_name)

    with open(snap_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    logger.info(
        f'  저장: {snap_name} @ {time_label} '
        f'(gainers {len(snapshot["gainers"])} / losers {len(snapshot["losers"])})'
    )

    # latest
    latest_path = os.path.join(DATA_DIR, 'latest.json')
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    # index 갱신
    update_index(snap_name, snapshot)


def update_index(snap_name, snapshot):
    """index.json — 일별 1개 entry. 같은 날짜면 덮어씀."""
    index_path = os.path.join(DATA_DIR, 'index.json')
    entries = []
    if os.path.exists(index_path):
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
        except Exception:
            entries = []

    # legacy 파일명 (YYYYMMDD_HHMM.json) 과 새 파일명 (YYYYMMDD.json) 모두 정리
    # → 같은 날짜의 legacy/신규 entry 모두 제거 후 새 entry 삽입
    date_part = snap_name.replace('.json', '')
    def _date_of(e):
        f = e.get('file', '')
        stem = f.replace('.json', '')
        return stem.split('_', 1)[0] if '_' in stem else stem
    entries = [e for e in entries if _date_of(e) != date_part]

    entries.insert(0, {
        'file': snap_name,
        'date': date_part,
        'collected_at': snapshot['collected_at'],
        'last_updated': snapshot.get('last_updated'),
        'session': snapshot['session'],
    })

    # 날짜 desc 정렬 후 오래된 항목 정리
    entries.sort(key=lambda e: _date_of(e), reverse=True)
    entries = cleanup_old_entries(entries)

    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def cleanup_old_entries(entries):
    """RETENTION_DAYS 초과 일별 스냅샷 + legacy intraday 파일 삭제.

    신규: YYYYMMDD.json / legacy: YYYYMMDD_HHMM.json 둘 다 처리.
    """
    cutoff = (datetime.now(KST) - timedelta(days=RETENTION_DAYS)).strftime('%Y%m%d')
    kept = []
    for e in entries:
        fname = e.get('file', '')
        stem = fname.replace('.json', '')
        date_part = stem.split('_', 1)[0] if '_' in stem else stem
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


def cleanup_legacy_intraday_files():
    """legacy YYYYMMDD_HHMM.json 파일 제거 (같은 날짜의 YYYYMMDD.json 이 있으면)."""
    if not os.path.isdir(DATA_DIR):
        return
    for fname in os.listdir(DATA_DIR):
        if not fname.endswith('.json'):
            continue
        stem = fname.replace('.json', '')
        if '_' not in stem:
            continue
        date_part = stem.split('_', 1)[0]
        if not date_part.isdigit() or len(date_part) != 8:
            continue
        # 같은 날짜의 신규 파일이 있으면 legacy 삭제
        new_path = os.path.join(DATA_DIR, f'{date_part}.json')
        if os.path.exists(new_path):
            legacy_path = os.path.join(DATA_DIR, fname)
            try:
                os.remove(legacy_path)
                logger.info(f'  legacy 정리: {fname} 삭제')
            except OSError as ex:
                logger.warning(f'  legacy 삭제 실패 {fname}: {ex}')


def main():
    logger.info('===== NXT 스냅샷 수집 시작 =====')
    try:
        snapshot = build_snapshot()
        save_snapshot(snapshot)
        cleanup_legacy_intraday_files()
        logger.info(f'===== 완료: gainers TOP {len(snapshot["gainers"])} / losers TOP {len(snapshot["losers"])} =====')
        return 0
    except Exception as e:
        logger.error(f'NXT 수집 실패: {e}', exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
