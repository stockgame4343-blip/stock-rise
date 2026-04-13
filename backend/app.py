"""Flask API 서버 — 순위 데이터 조회 + 정적 파일 서빙"""
import logging

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from pykrx import stock

from config import FLASK_HOST, FLASK_PORT, FRONTEND_DIR, NAVER_FINANCE_ITEM_URL
from db import init_db, get_rankings, get_news_for_date, get_available_dates, get_latest_date
from scheduler import create_scheduler
from collector import collect_and_save

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
CORS(app)


# ──────────────────────────────────────
# 정적 파일 서빙
# ──────────────────────────────────────

@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(FRONTEND_DIR, path)


# ──────────────────────────────────────
# API 엔드포인트
# ──────────────────────────────────────

@app.route('/api/rankings')
def api_rankings():
    """날짜별 상승 순위 조회

    Query params:
        date (str): YYYYMMDD (기본값: 최신 수집일)
        market (str): ALL / KOSPI / KOSDAQ (기본값: ALL)
    """
    date_str = request.args.get('date', '')
    market = request.args.get('market', 'ALL').upper()

    if not date_str:
        date_str = get_latest_date()
        if not date_str:
            return jsonify({'error': '수집된 데이터가 없습니다'}), 404

    rankings = get_rankings(date_str, market)
    news_map = get_news_for_date(date_str)

    result = []
    for r in rankings:
        item = dict(r)
        item['news'] = news_map.get(r['ticker'], [])
        item['detail_link'] = NAVER_FINANCE_ITEM_URL.format(ticker=r['ticker'])
        result.append(item)

    return jsonify({
        'date': date_str,
        'market': market,
        'count': len(result),
        'rankings': result,
    })


@app.route('/api/dates')
def api_dates():
    """조회 가능한 날짜 목록"""
    dates = get_available_dates()
    return jsonify({'dates': dates})


@app.route('/api/latest-date')
def api_latest_date():
    """가장 최근 수집 날짜"""
    latest = get_latest_date()
    return jsonify({'date': latest})


@app.route('/api/current-price')
def api_current_price():
    """현재가 조회 (과거 데이터 비교용)

    Query params:
        ticker (str): 종목코드 6자리
    """
    ticker = request.args.get('ticker', '')
    if not ticker:
        return jsonify({'error': 'ticker 파라미터가 필요합니다'}), 400

    try:
        name = stock.get_market_ticker_name(ticker)
        # 최근 거래일의 종가를 현재가로 사용
        from datetime import datetime
        today = datetime.now().strftime('%Y%m%d')
        df = stock.get_market_ohlcv_by_date(today, today, ticker)
        if df.empty:
            # 오늘이 비거래일이면 최근 거래일 조회
            from pykrx.stock import get_previous_business_days
            from datetime import timedelta
            start = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
            dates = get_previous_business_days(fromdate=start, todate=today)
            if dates:
                last_date = dates[-1].strftime('%Y%m%d')
                df = stock.get_market_ohlcv_by_date(last_date, last_date, ticker)

        if df.empty:
            return jsonify({'error': '가격 정보를 조회할 수 없습니다'}), 404

        price = int(df.iloc[-1]['종가'])
        return jsonify({
            'ticker': ticker,
            'name': name,
            'price': price,
        })
    except Exception as e:
        logger.error(f"현재가 조회 실패 ({ticker}): {e}")
        return jsonify({'error': '조회 중 오류 발생'}), 502


@app.route('/api/collect', methods=['POST'])
def api_collect():
    """수동 수집 트리거 (개발/테스트용)"""
    date_str = request.args.get('date', None)
    try:
        success = collect_and_save(date_str)
        if success:
            return jsonify({'status': 'ok', 'message': '수집 완료'})
        else:
            return jsonify({'status': 'skipped', 'message': '비거래일 — 수집 건너뜀'})
    except Exception as e:
        logger.error(f"수동 수집 실패: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ──────────────────────────────────────
# 서버 시작
# ──────────────────────────────────────

if __name__ == '__main__':
    init_db()

    scheduler = create_scheduler()
    scheduler.start()
    logger.info("스케줄러 시작됨")

    logger.info(f"서버 시작: http://{FLASK_HOST}:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False)
