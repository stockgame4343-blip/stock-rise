"""yfinance — 미국 3대 지수 (S&P 500 / NASDAQ / DOW) 일일 마감.

운영 정책:
- 호출 실패하면 None 반환 (pre2_ny 카드 스킵, 다른 카드는 정상 생성).
- 한국 카드 날짜 기준 가장 최근 미국 거래일을 자동 선택.
"""

import logging
from datetime import datetime, timedelta

try:
    import yfinance as yf
except ImportError:
    yf = None


log = logging.getLogger(__name__)

TICKERS = {
    'sp500':  '^GSPC',
    'nasdaq': '^IXIC',
    'dow':    '^DJI',
}

LOOKBACK_DAYS = 14  # 휴장·공휴일 대비 기간


def fetch(target_date=None):
    """미국 3대 지수 일일 마감.

    Args:
        target_date: 'YYYYMMDD' 문자열. None이면 가장 최근 거래일.
                     문자열 주어지면 해당 날짜 이전 가장 최근 미국 거래일 사용
                     (한국 04.24 카드 → 한국 시간 기준 가장 최근 NY 마감).

    Returns:
        {'sp500': {'close','change','pct','date'}, 'nasdaq': {...}, 'dow': {...}}
        또는 실패 시 None.
    """
    if yf is None:
        log.warning("yfinance 미설치 — pre2_ny 카드 스킵")
        return None

    try:
        if target_date:
            end_dt = datetime.strptime(target_date, '%Y%m%d') + timedelta(days=1)
        else:
            end_dt = datetime.now() + timedelta(days=1)
        start_dt = end_dt - timedelta(days=LOOKBACK_DAYS)

        result = {}
        for key, ticker in TICKERS.items():
            df = yf.download(
                ticker,
                start=start_dt.strftime('%Y-%m-%d'),
                end=end_dt.strftime('%Y-%m-%d'),
                progress=False,
                auto_adjust=False,
            )
            if df.empty or len(df) < 2:
                log.warning(f"yfinance: {ticker} 데이터 부족 ({len(df)}일)")
                return None

            close_col = df['Close']
            if hasattr(close_col, 'columns'):
                close_series = close_col[close_col.columns[0]]
            else:
                close_series = close_col

            today = float(close_series.iloc[-1])
            prev = float(close_series.iloc[-2])
            change = today - prev
            pct = (change / prev * 100) if prev else 0.0

            result[key] = {
                'close': today,
                'change': change,
                'pct': pct,
                'date': df.index[-1].strftime('%Y%m%d'),
            }
        return result
    except Exception as exc:
        log.warning("yfinance 실패: %s", exc)
        return None
