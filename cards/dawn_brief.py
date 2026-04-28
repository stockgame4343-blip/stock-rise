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

# 네이버 금융 — 인기 랭크 (조회수·인용 기준 큐레이션)
# 미국주식 카테고리(section_id3=259) 보다 마켓 무빙 헤드라인 비중이 높음.
NAVER_NEWS_URL = 'https://finance.naver.com/news/news_list.naver?mode=RANK'
NEWS_TIMEOUT = 10
HEADLINE_MIN_LEN = 15
HEADLINE_MAX_LEN = 70
FETCH_POOL = getattr(config, 'DAWN_FETCH_POOL', 30)

MACRO_TICKERS = {
    'nasdaq': '^IXIC',
    'sp500':  '^GSPC',
    'usdkrw': 'KRW=X',
    'vix':    '^VIX',
}
MACRO_LOOKBACK_DAYS = 14


def _clean_title(title):
    """헤드라인 노이즈 정리 — `[종목+]`, `[fn마켓워치]` 등 대괄호 미디어 태그 제거."""
    # [...]·[종목+] 형태 제거 (1~20자 내). `[속보]` 같은 것도 잘림.
    cleaned = re.sub(r'\s*\[[^\]]{1,20}\]\s*', ' ', title)
    # 다중 공백 → 하나
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _passes_filters(title):
    """글로벌 시장 무빙 헤드라인만 통과.

    - 화이트리스트 (DAWN_WHITELIST) 키워드 1개 이상 매치 필수
    - 블랙리스트 (DAWN_BLACKLIST) 키워드 매치되면 즉시 제외
    """
    title_lc = title.lower()
    blacklist = getattr(config, 'DAWN_BLACKLIST', []) or []
    for bad in blacklist:
        if bad.lower() in title_lc:
            return False
    whitelist = getattr(config, 'DAWN_WHITELIST', []) or []
    if not whitelist:
        return True  # 화이트리스트 미설정 시 전부 통과
    for kw in whitelist:
        if kw.lower() in title_lc:
            return True
    return False


def _is_duplicate(title, accepted):
    """간단 중복 검출 — 핵심 단어(2자 이상 한국어 명사) 60% 이상 겹치면 중복.

    예: '한은 금통위 7연속 동결 ...' 와 '7연속 동결 금통위 ...' 는 같은 사건.
    """
    def keywords(s):
        # 2자 이상 한글·영문·숫자 토큰
        return set(re.findall(r'[가-힣A-Za-z0-9]{2,}', s.lower()))
    cur = keywords(title)
    if not cur:
        return False
    for prev in accepted:
        prev_kw = keywords(prev)
        if not prev_kw:
            continue
        overlap = len(cur & prev_kw) / max(len(cur), len(prev_kw))
        if overlap >= 0.6:
            return True
    return False


def _fetch_naver_headlines(limit):
    """네이버 금융 인기랭크 → 글로벌 시장 무빙 헤드라인 N개.

    화이트리스트(키워드 매치) + 블랙리스트(국내 미시뉴스 제거) + 중복 제거 적용.
    """
    req = urllib.request.Request(NAVER_NEWS_URL, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=NEWS_TIMEOUT) as resp:
            raw = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        log.warning("네이버 헤드라인 fetch 실패: %s", exc)
        return []

    for enc in ('euc-kr', 'cp949', 'utf-8'):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        log.warning("네이버 헤드라인 디코딩 실패")
        return []

    # 인기랭크 페이지의 헤드라인 (a title 속성)
    pattern = r'<a[^>]+title="([^"]{15,80})"[^>]*>'
    accepted_titles = []
    out = []

    for raw_title in re.findall(pattern, text)[:FETCH_POOL]:
        title = html_unescape.unescape(raw_title).strip()
        title = _clean_title(title)
        if len(title) < HEADLINE_MIN_LEN:
            continue
        if not _passes_filters(title):
            continue
        # 검열: 유사투자자문업 → 권유성 표현 치환
        title = ts.censor(title).strip()
        if not title or ts.has_forbidden(title):
            continue
        if _is_duplicate(title, accepted_titles):
            continue
        accepted_titles.append(title)
        out.append({'title': title[:HEADLINE_MAX_LEN]})
        if len(out) >= limit:
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


def fetch(headline_limit=None):
    """헤드라인 + 매크로 묶음 dict.

    Args:
        headline_limit: 헤드라인 수 — 기본 TOP_DAWN_HEADLINES (3)
    Returns:
        {'headlines': [...], 'macro': {...}}
    """
    if headline_limit is None:
        headline_limit = config.TOP_DAWN_HEADLINES
    # pre0(3장) 와 pre2(2장) 동시에 쓰기 위해 넉넉히 가져옴 — 어느쪽이든 앞에서 자름
    pool_limit = max(headline_limit, getattr(config, 'PRE2_HEADLINES_TOP', 2)) + 2
    headlines = _fetch_naver_headlines(pool_limit)
    for h in headlines:
        h['impact'] = _impact_for(h['title'])
    return {
        'headlines': headlines,
        'macro': _fetch_macro(),
    }
