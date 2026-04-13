"""데이터 수집 파이프라인 - 네이버 증권 API + 뉴스/섹터 크롤링"""
import json
import logging
import requests
from datetime import datetime

from config import TOP_N, USER_AGENTS
from db import (
    init_db, insert_rankings, insert_news, cleanup_old_data,
    get_cached_sectors, upsert_sector
)
from news_crawler import crawl_news_for_tickers, crawl_sector
from scorer import calculate_score, generate_rise_reason, calculate_trading_intensity

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

NAVER_STOCK_UP_URL = 'https://m.stock.naver.com/api/stocks/up/{market}?page=1&pageSize={size}'
HEADERS = {'User-Agent': USER_AGENTS[0]}


def _parse_raw(value):
    """네이버 API raw 숫자 필드 파싱 (None/문자열 → int)"""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value).replace(',', ''))
    except (ValueError, TypeError):
        return 0


def collect_naver_rising_stocks():
    """네이버 증권 API에서 코스피+코스닥 상승 종목을 가져온다.
    ALL 마켓은 404이므로 KOSPI+KOSDAQ을 각각 조회 후 합산한다.
    """
    logger.info("[1/5] 네이버 증권 상승 종목 수집")
    all_stocks = []

    for market in ['KOSPI', 'KOSDAQ']:
        url = NAVER_STOCK_UP_URL.format(market=market, size=TOP_N)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            stocks = data.get('stocks', [])
            logger.info(f"  {market}: {len(stocks)}개 조회 (전체 {data.get('totalCount', '?')}개)")

            for s in stocks:
                all_stocks.append({
                    'ticker': s.get('itemCode', ''),
                    'name': s.get('stockName', ''),
                    'market': market,
                    'close_price': _parse_raw(s.get('closePriceRaw', s.get('closePrice'))),
                    'change_amount': _parse_raw(s.get('compareToPreviousClosePriceRaw', s.get('compareToPreviousClosePrice'))),
                    'change_rate': float(s.get('fluctuationsRatio', 0)),
                    'trading_value': _parse_raw(s.get('accumulatedTradingValueRaw', 0)),
                    'market_cap': _parse_raw(s.get('marketValueRaw', 0)),
                })
        except Exception as e:
            logger.error(f"  {market} 수집 실패: {e}")

    # 등락률 기준 내림차순 정렬 후 상위 100
    all_stocks.sort(key=lambda x: x['change_rate'], reverse=True)
    top = all_stocks[:TOP_N]

    logger.info(f"  상위 {len(top)}개 추출 완료")
    return top


def collect_trading_intensity(tickers):
    """3거래일 평균 대비 거래 강도 산출 (pykrx 단일 종목 OHLCV 사용)"""
    logger.info("[2/5] 거래 강도 산출")
    intensity_map = {}

    try:
        from pykrx import stock as pykrx_stock
        from datetime import timedelta
        today = datetime.now()
        start = (today - timedelta(days=10)).strftime('%Y%m%d')
        end = today.strftime('%Y%m%d')

        for idx, t in enumerate(tickers):
            try:
                df = pykrx_stock.get_market_ohlcv_by_date(start, end, t)
                if df.empty or len(df) < 2:
                    intensity_map[t] = '보통'
                    continue

                vals = df['거래대금'].tolist()
                today_val = vals[-1]
                prev_vals = vals[:-1][-3:]
                prev_avg = sum(prev_vals) / len(prev_vals) if prev_vals else 0
                intensity_map[t] = calculate_trading_intensity(today_val, prev_avg)
            except Exception:
                intensity_map[t] = '보통'

            if (idx + 1) % 20 == 0:
                logger.info(f"  거래 강도 진행: {idx + 1}/{len(tickers)}")
    except ImportError:
        logger.warning("  pykrx 미설치 — 거래 강도 기본값(보통) 사용")
        for t in tickers:
            intensity_map[t] = '보통'

    return intensity_map


def collect_sectors(tickers):
    """섹터 정보 (캐시 우선, 없으면 크롤링)"""
    logger.info("[3/5] 섹터 정보 수집")
    cached = get_cached_sectors(tickers)
    missing = [t for t in tickers if t not in cached]

    if missing:
        logger.info(f"  캐시 미스 {len(missing)}개 → 크롤링")
        for t in missing:
            sector = crawl_sector(t)
            cached[t] = sector
            upsert_sector(t, sector)

    return cached


def collect_and_save(date_str=None):
    """전체 수집 파이프라인 오케스트레이션"""
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')

    logger.info(f"===== 수집 시작: {date_str} =====")
    init_db()

    # Step 1: 네이버 상승 종목 수집
    top_stocks = collect_naver_rising_stocks()
    if not top_stocks:
        logger.info("수집 종료 (상승 종목 없음 — 비거래일 가능)")
        return False

    tickers = [s['ticker'] for s in top_stocks]

    # Step 2: 거래 강도
    intensity_map = collect_trading_intensity(tickers)

    # Step 3: 섹터
    sector_map = collect_sectors(tickers)

    # Step 4: 뉴스 + 점수
    logger.info("[4/5] 뉴스 수집 및 점수 산출")
    news_map = crawl_news_for_tickers(tickers, date_str)

    all_news = []
    for t, articles in news_map.items():
        for a in articles:
            all_news.append({
                'ticker': t,
                'title': a['title'],
                'link': a['link'],
                'source': a.get('source', ''),
            })

    # Step 5: 순위 데이터 조립
    logger.info("[5/5] 데이터 저장")
    rankings = []
    for idx, s in enumerate(top_stocks):
        t = s['ticker']
        news_articles = news_map.get(t, [])
        score_result = calculate_score(news_articles, date_str, t)
        reason = generate_rise_reason(news_articles)

        rankings.append({
            'rank': idx + 1,
            'ticker': t,
            'name': s['name'],
            'market': s['market'],
            'close_price': s['close_price'],
            'change_amount': s['change_amount'],
            'change_rate': s['change_rate'],
            'trading_value': s['trading_value'],
            'trading_intensity': intensity_map.get(t, '보통'),
            'market_cap': s['market_cap'],
            'sector': sector_map.get(t, ''),
            'score': score_result['total'],
            'score_detail': json.dumps(score_result['detail'], ensure_ascii=False),
            'rise_reason': reason,
        })

    # DB 저장
    insert_rankings(date_str, rankings)
    insert_news(date_str, all_news)
    cleanup_old_data()

    logger.info(f"===== 수집 완료: {len(rankings)}개 종목 저장 =====")
    return True


if __name__ == '__main__':
    collect_and_save()
