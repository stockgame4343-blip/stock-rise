"""데이터 수집 파이프라인 v2 — 고도화된 거래강도 + 호재점수"""
import logging
import requests
from datetime import datetime

from config import TOP_N, USER_AGENTS
from json_store import (
    save_daily_data, update_dates_index, cleanup_old_data,
    load_sector_cache, save_sector_cache,
    load_news_history, update_news_history,
    append_backtest_data,
    get_cached_theme_tags, update_theme_cache,
    load_tag_overrides,
)
from news_crawler import (
    crawl_news_for_tickers, crawl_sector,
    crawl_sector_performance, crawl_analyst_reports_for_tickers,
    fetch_article_bodies_for_themes,
    crawl_toss_ai_signals,
)
from scorer import calculate_score, generate_rise_reason, calculate_trading_intensity, extract_theme_tag, extract_theme_from_reason

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

NAVER_STOCK_UP_URL = 'https://m.stock.naver.com/api/stocks/up/{market}?page=1&pageSize={size}'
HEADERS = {'User-Agent': USER_AGENTS[0]}


def _parse_raw(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value).replace(',', ''))
    except (ValueError, TypeError):
        return 0


def collect_naver_rising_stocks():
    """네이버 증권 API에서 코스피+코스닥 상승 종목을 가져온다."""
    logger.info("[1/9] 네이버 증권 상승 종목 수집")
    all_stocks = []

    for market in ['KOSPI', 'KOSDAQ']:
        url = NAVER_STOCK_UP_URL.format(market=market, size=TOP_N)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            stocks = data.get('stocks', [])
            logger.info(f"  {market}: {len(stocks)}개 조회")

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

    all_stocks.sort(key=lambda x: x['change_rate'], reverse=True)
    top = all_stocks[:TOP_N]
    logger.info(f"  상위 {len(top)}개 추출 완료")
    return top


def collect_trading_data(tickers):
    """5일 거래대금 평균 + 기관/외인 수급 + 회전율 산출"""
    logger.info("[2/9] 거래 강도 데이터 수집 (5일평균 + 수급)")

    trading_data = {}

    try:
        from pykrx import stock as pykrx_stock
        from datetime import timedelta
        today = datetime.now()
        start = (today - timedelta(days=14)).strftime('%Y%m%d')
        end = today.strftime('%Y%m%d')

        for idx, t in enumerate(tickers):
            try:
                # OHLCV (거래대금)
                df = pykrx_stock.get_market_ohlcv_by_date(start, end, t)
                if df.empty or len(df) < 2:
                    trading_data[t] = _default_trading_data()
                    continue

                vals = df['거래대금'].tolist()
                today_val = vals[-1]
                avg_5day = sum(vals[-6:-1]) / min(len(vals) - 1, 5) if len(vals) >= 2 else vals[-1]

                # 투자자별 순매수 (기관/외인)
                inst_net = 0
                foreign_net = 0
                try:
                    inv_df = pykrx_stock.get_market_trading_value_by_date(
                        (today - timedelta(days=3)).strftime('%Y%m%d'),
                        end, t
                    )
                    if not inv_df.empty:
                        last_row = inv_df.iloc[-1]
                        inst_net = int(last_row.get('기관합계', 0))
                        foreign_net = int(last_row.get('외국인합계', 0))
                except Exception:
                    pass

                # 상한가 체크 (등락률 29.5% 이상)
                close_prices = df['종가'].tolist()
                is_limit_up = False
                if len(close_prices) >= 2:
                    prev_close = close_prices[-2]
                    if prev_close > 0:
                        day_change = (close_prices[-1] - prev_close) / prev_close * 100
                        is_limit_up = day_change >= 29.5

                trading_data[t] = {
                    'today_value': today_val,
                    'avg_5day': avg_5day,
                    'inst_net': inst_net,
                    'foreign_net': foreign_net,
                    'is_limit_up': is_limit_up,
                }
            except Exception:
                trading_data[t] = _default_trading_data()

            if (idx + 1) % 20 == 0:
                logger.info(f"  거래 데이터 진행: {idx + 1}/{len(tickers)}")

    except ImportError:
        logger.warning("  pykrx 미설치 — 기본값 사용")
        for t in tickers:
            trading_data[t] = _default_trading_data()

    return trading_data


def _default_trading_data():
    return {
        'today_value': 0,
        'avg_5day': 0,
        'inst_net': 0,
        'foreign_net': 0,
        'is_limit_up': False,
    }


def calculate_turnover_ranks(top_stocks, trading_data):
    """시총 대비 회전율 백분위 계산"""
    turnover_list = []
    for s in top_stocks:
        t = s['ticker']
        td = trading_data.get(t, {})
        cap = s.get('market_cap', 0)
        today_val = td.get('today_value', 0)
        turnover = (today_val / cap * 100) if cap > 0 else 0
        turnover_list.append((t, turnover))

    turnover_list.sort(key=lambda x: x[1], reverse=True)

    rank_map = {}
    total = len(turnover_list)
    for rank, (ticker, _) in enumerate(turnover_list):
        rank_map[ticker] = round(rank / total * 100) if total > 0 else 50

    return rank_map


def collect_sectors(tickers):
    """섹터 정보 (캐시 우선)"""
    logger.info("[3/9] 섹터 정보 수집")
    cached = load_sector_cache()
    missing = [t for t in tickers if t not in cached]

    if missing:
        logger.info(f"  캐시 미스 {len(missing)}개 → 크롤링")
        for t in missing:
            sector = crawl_sector(t)
            cached[t] = sector
        save_sector_cache(cached)

    return cached


def collect_52w_highs(tickers):
    """52주 최고가 및 달성일 수집 (차트 API)"""
    import time
    from datetime import timedelta
    logger.info("[4/9] 52주 최고가 수집")

    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
    high_52w_map = {}

    for idx, t in enumerate(tickers):
        try:
            url = f'https://api.stock.naver.com/chart/domestic/item/{t}/day?startDateTime={start_date}&endDateTime={end_date}'
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data:
                max_entry = max(data, key=lambda x: x.get('highPrice', 0))
                high_52w_map[t] = {
                    'price': int(max_entry.get('highPrice', 0)),
                    'date': max_entry.get('localDate', ''),
                }
            else:
                high_52w_map[t] = {'price': 0, 'date': ''}
        except Exception:
            high_52w_map[t] = {'price': 0, 'date': ''}

        if (idx + 1) % 20 == 0:
            logger.info(f"  52주 최고가 진행: {idx + 1}/{len(tickers)}")

        time.sleep(0.05)

    logger.info(f"  52주 최고가 수집 완료: {len(high_52w_map)}개")
    return high_52w_map


_SECTOR_SHORT = {
    '전자장비와기기': '전자장비', '우주항공과국방': '방산', '반도체와반도체장비': '반도체',
    '소프트웨어': 'SW', '기술하드웨어와장비': 'IT하드웨어', '디스플레이장비및부품': '디스플레이',
    '해운사': '해운', '에너지장비및서비스': '에너지', '전기장비': '전기',
    '식품과기본식료품소매': '유통', '생물공학': '바이오', '미디어와엔터테인먼트': '엔터',
    'IT서비스': 'IT', '건축자재': '건자재', '건축제품': '건설', '전자제품': '전자',
    '창업투자': 'VC', '자동차부품': '자동차', '섬유와의류': '섬유',
}


def _sector_to_tag(sector):
    """긴 섹터명을 짧은 태그로 변환"""
    if not sector:
        return ''
    return _SECTOR_SHORT.get(sector, sector)


def collect_and_save(date_str=None, mode='closing'):
    """전체 수집 파이프라인 v2
    mode: 'closing' = 장마감 최종 수집, 'intraday' = 장중 실시간
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')

    logger.info(f"===== 수집 시작 v2: {date_str} =====")

    # Step 1: 네이버 상승 종목
    top_stocks = collect_naver_rising_stocks()
    if not top_stocks:
        logger.info("수집 종료 (상승 종목 없음 — 비거래일 가능)")
        return False

    tickers = [s['ticker'] for s in top_stocks]

    # Step 2: 거래 강도 데이터 (5일평균 + 수급)
    trading_data = collect_trading_data(tickers)
    turnover_ranks = calculate_turnover_ranks(top_stocks, trading_data)

    # Step 3: 섹터
    sector_map = collect_sectors(tickers)

    # Step 4: 52주 최고가
    high_52w_map = collect_52w_highs(tickers)

    # Step 5: 뉴스
    logger.info("[5/9] 뉴스 수집")
    news_map = crawl_news_for_tickers(tickers, date_str)

    # Step 6: 기사 본문 수집 (테마 추출용, 오버라이드 > 캐시 > 추출)
    logger.info("[6/9] 기사 본문 수집 (테마 추출)")
    tag_overrides = load_tag_overrides()
    override_tickers = set(t for t in tickers if t in tag_overrides)
    remaining = [t for t in tickers if t not in override_tickers]
    if override_tickers:
        logger.info(f"  사용자 오버라이드: {len(override_tickers)}개")

    cached_tags, uncached_tickers = get_cached_theme_tags(remaining, date_str)
    logger.info(f"  테마 캐시 히트: {len(cached_tags)}개, 미스: {len(uncached_tickers)}개")

    article_bodies_map = {}
    if uncached_tickers:
        uncached_news = {t: news_map.get(t, []) for t in uncached_tickers}
        article_bodies_map = fetch_article_bodies_for_themes(uncached_news)

    # Step 7: 업종 등락률 + 증권사 리포트
    logger.info("[7/10] 업종 등락률 + 증권사 리포트 수집")
    sector_performance = crawl_sector_performance()
    report_map = crawl_analyst_reports_for_tickers(tickers)

    # Step 8: 토스증권 AI 시그널 (1순위 상승 이유)
    logger.info("[8/10] 토스증권 AI 시그널 수집")
    toss_reasons = crawl_toss_ai_signals()

    # Step 9: 뉴스 이력 로드 + 갱신
    logger.info("[9/10] 뉴스 이력 갱신 + 점수 산출")
    news_history = load_news_history()
    update_news_history(date_str, news_map)

    # Step 10: 순위 데이터 조립
    logger.info("[10/10] 데이터 저장")
    rankings = []
    new_theme_tags = {}
    for idx, s in enumerate(top_stocks):
        t = s['ticker']
        news_articles = news_map.get(t, [])

        # 거래 강도 v2
        td = trading_data.get(t, _default_trading_data())
        intensity_label, intensity_detail = calculate_trading_intensity(
            today_value=td['today_value'],
            avg_5day_value=td['avg_5day'],
            inst_net=td['inst_net'],
            foreign_net=td['foreign_net'],
            turnover_rank_pct=turnover_ranks.get(t, 50),
        )

        # 상한가 종목 별도 플래그
        if td.get('is_limit_up'):
            intensity_label = '상한가'

        # 호재 점수 v3
        score_result = calculate_score(
            articles=news_articles,
            date_str=date_str,
            ticker=t,
            close_price=s['close_price'],
            sector_performance=sector_performance,
            turnover_rank_pct=turnover_ranks.get(t, 50),
        )

        # 테마 태그 + 상승 이유 (우선순위: 오버라이드 > 캐시 > 추출)
        if t in tag_overrides:
            theme_tag = tag_overrides[t]
        elif t in cached_tags:
            theme_tag = cached_tags[t]
        else:
            theme_tag = extract_theme_tag(news_articles, article_bodies_map.get(t, []), stock_name=s['name'])
            new_theme_tags[t] = theme_tag
        # Fallback 1: Toss 상승이유에서 추출
        if not theme_tag and t in toss_reasons:
            theme_tag = extract_theme_from_reason(toss_reasons[t])
            if theme_tag:
                new_theme_tags[t] = theme_tag
        # Fallback 2: 상승이유에서 추출
        if not theme_tag:
            theme_tag = extract_theme_from_reason(
                generate_rise_reason(news_articles, report_map.get(t, []),
                                     theme_tag='', stock_name=s['name'])
            )
        # Fallback 3: 섹터명을 태그로 사용
        if not theme_tag:
            theme_tag = _sector_to_tag(sector_map.get(t, ''))

        # 상승 이유 (우선순위: Toss AI > 뉴스 키워드 분석)
        if t in toss_reasons:
            reason = toss_reasons[t]
        else:
            reason = generate_rise_reason(news_articles, report_map.get(t, []),
                                          theme_tag=theme_tag, stock_name=s['name'])

        rankings.append({
            'rank': idx + 1,
            'ticker': t,
            'name': s['name'],
            'market': s['market'],
            'close_price': s['close_price'],
            'change_amount': s['change_amount'],
            'change_rate': s['change_rate'],
            'trading_value': s['trading_value'],
            'market_cap': s['market_cap'],
            'sector': sector_map.get(t, ''),
            'high_52w': high_52w_map.get(t, {}).get('price', 0),
            'high_52w_date': high_52w_map.get(t, {}).get('date', ''),
            'theme_tag': theme_tag,
            'score': score_result['total'],
            'score_detail': score_result['detail'],
            'rise_reason': reason,
            'news': news_articles,
        })

    # 테마 캐시 갱신
    if new_theme_tags:
        update_theme_cache(date_str, new_theme_tags)

    # JSON 저장
    daily_data = {
        'date': date_str,
        'collected_at': datetime.now().isoformat(timespec='seconds'),
        'mode': mode,
        'is_final': mode == 'closing',
        'count': len(rankings),
        'version': 2,
        'rankings': rankings,
    }

    save_daily_data(date_str, daily_data)
    update_dates_index()
    cleanup_old_data()

    # 백테스트 데이터 기록
    append_backtest_data(date_str, rankings)

    logger.info(f"===== 수집 완료 v2: {len(rankings)}개 종목 저장 =====")
    return True


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', default='closing', choices=['closing', 'intraday'])
    parser.add_argument('--date', default=None)
    args = parser.parse_args()
    collect_and_save(date_str=args.date, mode=args.mode)
