"""5월~현재 과거 pullbacks 에 '고점회복(졸업)' 종목 소급 백필.

각 거래일 D 에 대해: 직전 거래일 pullback 종목 중, D 종가가 고점(peakPrice) 이상으로
회복했고 D 당일엔 조정 목록에 없는 종목을 recovered=True / recoveredDate=D 로
D.json 의 pullbacks 맨 앞에 추가한다. 멱등(이미 recovered 면 건너뜀) — 재실행 안전.

실행:  python collector/backfill_recovered.py        (기본 START=20260501)
"""
import json
import os
import time

import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'public', 'data')
START = '20260501'
HEADERS = {'User-Agent': 'Mozilla/5.0'}


def trading_dates():
    files = sorted(
        f for f in os.listdir(DATA_DIR)
        if len(f) == 13 and f[:8].isdigit() and f.endswith('.json')
    )
    return [f[:8] for f in files]


def load(d):
    with open(os.path.join(DATA_DIR, d + '.json'), 'r', encoding='utf-8') as f:
        return json.load(f)


def save(d, data):
    # json_store 와 동일 포맷(indent=2) — 안 그러면 파일 전체가 minify 되어 diff 폭발
    with open(os.path.join(DATA_DIR, d + '.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_closes(ticker, start, end):
    """ticker 의 start~end 일별 종가 {date: close}."""
    url = (
        f'https://api.stock.naver.com/chart/domestic/item/{ticker}/day'
        f'?startDateTime={start}&endDateTime={end}'
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        out = {}
        for x in r.json() or []:
            ld, cp = x.get('localDate'), x.get('closePrice')
            if ld and cp:
                out[ld] = int(cp)
        return out
    except Exception as e:
        print(f'  close fetch fail {ticker}: {e}')
        return {}


def main():
    all_dates = trading_dates()
    targets = [d for d in all_dates if d >= START]
    if not targets:
        print('대상 날짜 없음')
        return
    idx_of = {d: i for i, d in enumerate(all_dates)}
    start_fetch = all_dates[max(0, idx_of[targets[0]] - 1)]   # 직전일 포함해 종가 확보
    end_fetch = all_dates[-1]
    print(f'대상 {len(targets)}일 ({targets[0]}~{targets[-1]}), 종가 {start_fetch}~{end_fetch}')

    tickers = set()
    for d in all_dates:
        if d < start_fetch:
            continue
        for pb in load(d).get('pullbacks', []):
            if pb.get('ticker'):
                tickers.add(pb['ticker'])
    tickers = sorted(tickers)
    print(f'종목 {len(tickers)}개 종가 조회...')

    price = {}
    for i, t in enumerate(tickers):
        price[t] = fetch_closes(t, start_fetch, end_fetch)
        time.sleep(0.08)
        if (i + 1) % 50 == 0:
            print(f'  {i + 1}/{len(tickers)}')

    changed = 0
    total_rec = 0
    for d in targets:
        i = idx_of[d]
        if i == 0:
            continue
        prev_d = all_dates[i - 1]
        d_data = load(d)
        d_pbs = d_data.get('pullbacks', [])
        existing = {p['ticker'] for p in d_pbs if p.get('ticker')}
        already = {p['ticker'] for p in d_pbs if p.get('recovered')}
        recovered = []
        for pb in load(prev_d).get('pullbacks', []):
            if pb.get('recovered'):
                continue
            t, peak = pb.get('ticker'), pb.get('peakPrice')
            if not t or not peak or t in existing or t in already:
                continue
            cur = price.get(t, {}).get(d)
            if cur and cur >= peak:
                e = dict(pb)
                e['currentPrice'] = cur
                e['dropPct'] = round((peak - cur) / peak * 100, 2)
                e['recovered'] = True
                e['recoveredDate'] = d
                low = pb.get('postPeakLow') or pb.get('lowPrice') or cur
                e['postPeakLow'] = low
                e['bouncePct'] = round((cur - low) / low * 100, 2) if low else 0
                e['bounceBack'] = True
                recovered.append(e)
        if recovered:
            d_data['pullbacks'] = recovered + d_pbs
            save(d, d_data)
            changed += 1
            total_rec += len(recovered)
            print(f'  {d}: +{len(recovered)} 졸업')
    print(f'완료: {changed}일 변경, 졸업 {total_rec}개')


if __name__ == '__main__':
    main()
