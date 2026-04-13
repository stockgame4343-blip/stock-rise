"""SQLite 데이터베이스 초기화 및 쿼리 헬퍼"""
import sqlite3
import os
from datetime import datetime, timedelta
from config import DB_PATH, DATA_DIR, DATA_RETENTION_DAYS


def get_connection():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_rankings (
            date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            name TEXT NOT NULL,
            market TEXT NOT NULL,
            close_price INTEGER NOT NULL,
            change_amount INTEGER NOT NULL,
            change_rate REAL NOT NULL,
            trading_value INTEGER NOT NULL,
            trading_intensity TEXT NOT NULL DEFAULT '보통',
            market_cap INTEGER NOT NULL,
            sector TEXT DEFAULT '',
            score INTEGER NOT NULL DEFAULT 0,
            score_detail TEXT DEFAULT '{}',
            rise_reason TEXT DEFAULT '',
            PRIMARY KEY (date, ticker)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            title TEXT NOT NULL,
            link TEXT NOT NULL,
            source TEXT DEFAULT ''
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sector_cache (
            ticker TEXT PRIMARY KEY,
            sector TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rankings_date ON daily_rankings(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rankings_market ON daily_rankings(date, market)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_date_ticker ON stock_news(date, ticker)")

    conn.commit()
    conn.close()


def insert_rankings(date_str, rankings):
    """일별 순위 데이터 일괄 INSERT"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executemany("""
        INSERT OR REPLACE INTO daily_rankings
        (date, rank, ticker, name, market, close_price, change_amount, change_rate,
         trading_value, trading_intensity, market_cap, sector, score, score_detail, rise_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (
            date_str, r['rank'], r['ticker'], r['name'], r['market'],
            r['close_price'], r['change_amount'], r['change_rate'],
            r['trading_value'], r['trading_intensity'], r['market_cap'],
            r['sector'], r['score'], r['score_detail'], r['rise_reason']
        )
        for r in rankings
    ])
    conn.commit()
    conn.close()


def insert_news(date_str, news_list):
    """종목 뉴스 일괄 INSERT"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM stock_news WHERE date = ?", (date_str,))
    cursor.executemany("""
        INSERT INTO stock_news (date, ticker, title, link, source)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (date_str, n['ticker'], n['title'], n['link'], n.get('source', ''))
        for n in news_list
    ])
    conn.commit()
    conn.close()


def upsert_sector(ticker, sector):
    """섹터 캐시 UPSERT"""
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO sector_cache (ticker, sector, updated_at)
        VALUES (?, ?, ?)
    """, (ticker, sector, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()


def get_cached_sectors(tickers):
    """캐시된 섹터 정보 조회 (dict 반환)"""
    conn = get_connection()
    placeholders = ','.join(['?'] * len(tickers))
    rows = conn.execute(
        f"SELECT ticker, sector FROM sector_cache WHERE ticker IN ({placeholders})",
        tickers
    ).fetchall()
    conn.close()
    return {row['ticker']: row['sector'] for row in rows}


def get_rankings(date_str, market='ALL'):
    """날짜별 순위 조회 (시장 필터 포함)"""
    conn = get_connection()
    if market == 'ALL':
        rows = conn.execute(
            "SELECT * FROM daily_rankings WHERE date = ? ORDER BY rank",
            (date_str,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM daily_rankings WHERE date = ? AND market = ? ORDER BY rank",
            (date_str, market)
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_news_for_date(date_str):
    """날짜별 전체 뉴스 조회 (ticker별 그룹핑용)"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM stock_news WHERE date = ? ORDER BY ticker, id",
        (date_str,)
    ).fetchall()
    conn.close()

    news_map = {}
    for row in rows:
        r = dict(row)
        ticker = r['ticker']
        if ticker not in news_map:
            news_map[ticker] = []
        news_map[ticker].append({
            'title': r['title'],
            'link': r['link'],
            'source': r['source'],
        })
    return news_map


def get_available_dates():
    """조회 가능한 날짜 목록 (최신순)"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT date FROM daily_rankings ORDER BY date DESC"
    ).fetchall()
    conn.close()
    return [row['date'] for row in rows]


def get_latest_date():
    """가장 최근 수집 날짜"""
    conn = get_connection()
    row = conn.execute(
        "SELECT MAX(date) as latest FROM daily_rankings"
    ).fetchone()
    conn.close()
    return row['latest'] if row else None


def cleanup_old_data():
    """90일 초과 데이터 삭제"""
    cutoff = (datetime.now() - timedelta(days=DATA_RETENTION_DAYS)).strftime('%Y%m%d')
    conn = get_connection()
    conn.execute("DELETE FROM daily_rankings WHERE date < ?", (cutoff,))
    conn.execute("DELETE FROM stock_news WHERE date < ?", (cutoff,))
    conn.commit()
    conn.close()
