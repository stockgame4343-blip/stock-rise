"""새벽 브리핑 — 네이버 금융 메인뉴스 헤드라인 + 매크로 지수.

운영 정책:
- 네이버 금융 메인뉴스에서 큐레이션된 헤드라인 TOP N 수집
- 키워드 매칭으로 "국장 영향 한 줄" 자동 부착 (매핑 없으면 빈 문자열)
- yfinance 로 NASDAQ / S&P / USD-KRW / VIX 매크로 한 줄
- fetch 실패 시 None 또는 빈 dict 반환 → 카드 자체는 그래도 렌더 (가능한 영역만)
"""

import html as html_unescape
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from . import config
from . import text_synth as ts

try:
    import yfinance as yf
except ImportError:
    yf = None


log = logging.getLogger(__name__)

# 네이버 금융 — 해외증시 > 미국주식 카테고리 (section_id2=262, section_id3=259)
# 메인 헤드라인 페이지(mainnews) 와 달리 글로벌 시장에 집중된 풀 텍스트 헤드라인 제공.
NAVER_NEWS_URL = (
    'https://finance.naver.com/news/news_list.naver'
    '?mode=LSS3D&section_id=101&section_id2=262&section_id3=259'
)
NEWS_TIMEOUT = 10
HEADLINE_MIN_LEN = 10
HEADLINE_MAX_LEN = 70
HEADLINE_LIMIT = config.TOP_DAWN_HEADLINES if hasattr(config, 'TOP_DAWN_HEADLINES') else 3

MACRO_TICKERS = {
    'nasdaq': '^IXIC',
    'sp500':  '^GSPC',
    'usdkrw': 'KRW=X',
    'vix':    '^VIX',
}
MACRO_LOOKBACK_DAYS = 14


def _fetch_naver_headlines():
    """네이버 금융 — 미국주식 카테고리 헤드라인.

    이 카테고리는 편집자가 큐레이션한 미증시·글로벌 시장 뉴스만 모음.
    `articleSubject` 셀의 title 속성에 풀 텍스트 헤드라인이 들어 있어 트렁케이션 없음.

    Returns: list of {'title': str}. 실패 시 빈 리스트.
    """
    req = urllib.request.Request(
        NAVER_NEWS_URL,
        headers={'User-Agent': 'Mozilla/5.0'},
    )
    try:
        with urllib.request.urlopen(req, timeout=NEWS_TIMEOUT) as resp:
            raw = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        log.warning("네이버 헤드라인 fetch 실패: %s", exc)
        return []

    # 네이버 금융은 EUC-KR (CP949)
    for enc in ('euc-kr', 'cp949', 'utf-8'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        log.warning("네이버 헤드라인 디코딩 실패")
        return []

    # `<dd class="articleSubject"><a ... title="...">` 패턴 — 풀 텍스트 헤드라인
    pattern = r'<dd class="articleSubject"[^>]*>\s*<a[^>]*title="([^"]+)"'
    seen = set()
    out = []
    for raw_title in re.findall(pattern, text):
        title = html_unescape.unescape(raw_title).strip()
        if len(title) < HEADLINE_MIN_LEN or title in seen:
            continue
        seen.add(title)
        # 검열: 유사투자자문업 미신고 → 권유성 표현 자동 치환
        title = ts.censor(title).strip()
        if not title or ts.has_forbidden(title):
            continue
        out.append({'title': title[:HEADLINE_MAX_LEN]})
        if len(out) >= HEADLINE_LIMIT:
            break
    return out


def _impact_for(title):
    """헤드라인 → 국장 영향 한 줄 (config.DAWN_IMPACT_MAP 키워드 매칭)."""
    impacts = getattr(config, 'DAWN_IMPACT_MAP', None) or []
    title_lc = title.lower()
    for keywords, impact_text in impacts:
        for kw in keywords:
            if kw.lower() in title_lc:
                return impact_text
    return ''


def _fetch_macro():
    """매크로 지수 4종 (NASDAQ / S&P / USD-KRW / VIX)."""
    if yf is None:
        log.warning("yfinance 미설치 — 매크로 fetch 스킵")
        return {}

    end_dt = datetime.now() + timedelta(days=1)
    start_dt = end_dt - timedelta(days=MACRO_LOOKBACK_DAYS)
    out = {}
    for key, ticker in MACRO_TICKERS.items():
        try:
            df = yf.download(
                ticker,
                start=start_dt.strftime('%Y-%m-%d'),
                end=end_dt.strftime('%Y-%m-%d'),
                progress=False,
                auto_adjust=False,
            )
            if df.empty or len(df) < 2:
                log.warning("yfinance: %s 데이터 부족", ticker)
                continue
            close_col = df['Close']
            if hasattr(close_col, 'columns'):
                series = close_col[close_col.columns[0]]
            else:
                series = close_col
            today = float(series.iloc[-1])
            prev = float(series.iloc[-2])
            change = today - prev
            pct = (change / prev * 100) if prev else 0.0
            out[key] = {'close': today, 'change': change, 'pct': pct}
        except Exception as exc:
            log.warning("yfinance %s 실패: %s", ticker, exc)
    return out


def fetch():
    """헤드라인 + 매크로 묶음 dict 반환.

    Returns:
        {'headlines': [...], 'macro': {...}}
        둘 다 비어있을 수 있음 — 빈 영역은 템플릿이 알아서 표시 안 함.
    """
    headlines = _fetch_naver_headlines()
    for h in headlines:
        h['impact'] = _impact_for(h['title'])
    return {
        'headlines': headlines,
        'macro': _fetch_macro(),
    }
