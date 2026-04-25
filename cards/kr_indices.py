"""pykrx — KOSPI / KOSDAQ 일일 마감.

운영 정책: 호출 실패하면 None (close 카드는 지수 영역만 빠지고 나머지는 정상).
"""

import logging
from datetime import datetime, timedelta

try:
    from pykrx import stock
except ImportError:
    stock = None


log = logging.getLogger(__name__)

INDICES = {
    'kospi':  '1001',
    'kosdaq': '2001',
}

LOOKBACK_DAYS = 10  # 직전 거래일까지 충분한 기간


def fetch(yyyymmdd):
    """`yyyymmdd` 기준 KOSPI/KOSDAQ 마감 + 전일 대비.

    Returns:
        {'kospi': {'close','change','pct'}, 'kosdaq': {...}} or None
    """
    if stock is None:
        log.warning("pykrx 미설치 — close 카드 지수 영역 스킵")
        return None

    try:
        start_dt = datetime.strptime(yyyymmdd, '%Y%m%d') - timedelta(days=LOOKBACK_DAYS)
        start = start_dt.strftime('%Y%m%d')
        result = {}
        for key, code in INDICES.items():
            df = stock.get_index_ohlcv(start, yyyymmdd, code)
            if df.empty:
                log.warning(f"pykrx: {code} ({key}) 빈 응답")
                return None
            today = float(df['종가'].iloc[-1])
            prev = float(df['종가'].iloc[-2]) if len(df) >= 2 else today
            change = today - prev
            pct = (change / prev * 100) if prev else 0.0
            result[key] = {'close': today, 'change': change, 'pct': pct}
        return result
    except Exception as exc:
        log.warning("pykrx 실패: %s", exc)
        return None
