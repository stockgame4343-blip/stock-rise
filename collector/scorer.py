"""호재 점수 산출 v2, 거래 강도 레이블, 상승 이유 텍스트 생성

v2 개선사항:
- 뉴스 중복 제거 (자카드 유사도)
- 금융 감성분석 (사전 기반)
- 동적 키워드 가중치 (업종 등락률 연동)
- 7일 뉴스 이력 기반 지속성 판단
- 시장 컨텍스트 (전체 테마 vs 개별 호재)
- 증권사 리포트 반영
- 거래 강도: 5일 평균 + 수급 보정 + 회전율
"""
import re
import logging

from config import (
    FAVOR_TYPE_SCORES, MAJOR_PRESS, TRADING_INTENSITY,
    SUPPLY_DEMAND_MULTIPLIER, TURNOVER_BONUS_PERCENTILE,
    SENTIMENT_POSITIVE, SENTIMENT_NEGATIVE, NEWS_DEDUP_THRESHOLD,
    KEYWORD_THEME_MAP,
    MARKET_THEME_MIN_STOCKS, MARKET_THEME_DISCOUNT, UNIQUE_THEME_BONUS,
    THEME_BOOST_HOT, THEME_BOOST_WARM, THEME_BOOST_COLD,
)

logger = logging.getLogger(__name__)

# ── Toss 스타일 상승 이유 생성 ──
# 뉴스 제목에서 액션 키워드를 추출하여 "{주제} {액션}" 패턴으로 결합
# 예: "반도체 투자 확대", "광통신 테마 강세", "신약 승인 기대"

# (키워드, 액션 텍스트, 우선도) — 우선도가 높을수록 먼저 선택
_ACTION_TABLE = [
    # 실적/재무
    ('흑자전환',   '흑자 전환',       8),
    ('어닝서프라이즈', '실적 서프라이즈', 8),
    ('흑자',       '흑자 전환 기대',   7),
    ('영업이익',   '실적 호조',       7),
    ('순이익',     '실적 개선',       6),
    ('매출',       '매출 성장 기대',   5),
    ('실적',       '실적 개선 기대',   5),
    # 수주/계약
    ('수주',       '수주 확대',       7),
    ('납품',       '납품 계약 체결',   7),
    ('공급 계약',  '공급 계약 체결',   8),
    ('계약 체결',  '계약 체결',       7),
    ('계약',       '신규 계약 기대',   5),
    ('공급',       '공급 확대',       4),
    # 바이오/신약
    ('FDA',        'FDA 승인 기대',   8),
    ('허가',       '허가 기대',       7),
    ('임상 3상',   '임상 3상 진입',   8),
    ('임상',       '임상 진전',       6),
    ('신약',       '신약 모멘텀',     6),
    ('승인',       '승인 기대',       6),
    # 투자/사업
    ('설비 투자',  '설비 투자 확대',   7),
    ('투자 확대',  '투자 확대',       7),
    ('증설',       '생산 증설',       7),
    ('양산',       '양산 본격화',     7),
    ('착공',       '착공 기대',       6),
    ('수출',       '수출 확대 기대',   6),
    ('진출',       '해외 진출 기대',   5),
    ('투자',       '투자 기대',       3),
    # 기업 이벤트
    ('인수',       '인수 기대감',     6),
    ('합병',       '합병 기대감',     6),
    ('M&A',        'M&A 기대감',     6),
    ('MOU',        'MOU 체결',       6),
    ('대표이사',   '경영진 교체',     5),
    ('특허',       '특허 취득',       6),
    ('기술이전',   '기술이전 기대',   7),
    ('라이선스',   '라이선스 계약',   6),
    ('지분',       '지분 투자 이슈',   5),
    ('자사주',     '자사주 매입',     6),
    ('소각',       '자사주 소각',     7),
    ('배당',       '배당 기대',       5),
    ('주주환원',   '주주환원 정책',   6),
    ('상장',       '상장 이슈',       5),
    ('분할',       '기업 분할 이슈',   5),
    ('협력',       '사업 협력 기대',   4),
    # 정책/규제
    ('국책',       '국책사업 수혜',   6),
    ('보조금',     '정부 보조금 수혜', 6),
    ('정부',       '정부 정책 수혜',   4),
    ('정책',       '정책 수혜 기대',   4),
    # 수급
    ('외국인',     '외국인 매수세',   3),
    ('기관',       '기관 매수세',     3),
    ('순매수',     '수급 유입',       3),
    # 시장/테마 일반
    ('강세',       '테마 강세',       2),
    ('급등',       '급등세',         2),
    ('관련주',     '테마 부각',       2),
    ('상한가',     '상한가 기록',     2),
]


# ══════════════════════════════════════
# 뉴스 전처리
# ══════════════════════════════════════

def _jaccard_similarity(title_a, title_b):
    """두 제목의 자카드 유사도 (단어 집합 기반)"""
    words_a = set(title_a.split())
    words_b = set(title_b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def deduplicate_news(articles):
    """뉴스 중복 제거 — 자카드 유사도 기반"""
    if not articles:
        return []

    unique = [articles[0]]
    for article in articles[1:]:
        is_dup = False
        for existing in unique:
            if _jaccard_similarity(article['title'], existing['title']) >= NEWS_DEDUP_THRESHOLD:
                is_dup = True
                break
        if not is_dup:
            unique.append(article)

    removed = len(articles) - len(unique)
    if removed > 0:
        logger.debug(f"  중복 뉴스 {removed}건 제거 ({len(articles)} → {len(unique)})")

    return unique


# ══════════════════════════════════════
# 호재 점수 v2
# ══════════════════════════════════════

def _score_buzz(articles):
    """뉴스 양 (Buzz) — 20점 만점 (중복 제거 후)"""
    n = len(articles)
    if n == 0:
        return 0
    elif n <= 2:
        return 8
    elif n <= 4:
        return 13
    elif n <= 6:
        return 17
    else:
        return 20


def _score_quality(articles):
    """뉴스 질 (Quality) — 25점 만점"""
    if not articles:
        return 0

    major_count = sum(
        1 for a in articles
        if any(press in a.get('source', '') for press in MAJOR_PRESS)
    )
    major_ratio = major_count / len(articles)
    source_score = round(major_ratio * 15)

    numeric_pattern = re.compile(r'\d+[\.\d]*\s*(억|조|%|만|원|달러|건)')
    numeric_count = sum(
        1 for a in articles
        if numeric_pattern.search(a.get('title', ''))
    )
    numeric_ratio = numeric_count / len(articles)
    numeric_score = round(numeric_ratio * 10)

    return min(source_score + numeric_score, 25)


def _score_type(articles, sector_performance=None):
    """호재 유형 (Type) — 30점 만점, 동적 테마 가중치 적용"""
    if not articles:
        return 0

    all_titles = ' '.join(a.get('title', '') for a in articles)

    max_score = 0
    matched_theme = None

    for keyword, score in FAVOR_TYPE_SCORES.items():
        if keyword in all_titles:
            if score > max_score:
                max_score = score
                matched_theme = KEYWORD_THEME_MAP.get(keyword)

    # 동적 테마 가중치: 업종 등락률 연동
    if max_score > 0 and matched_theme and sector_performance:
        theme_boost = _get_theme_boost(matched_theme, sector_performance)
        max_score = min(round(max_score * theme_boost), 30)

    return max_score


def _get_theme_boost(theme, sector_performance):
    """업종 등락률 기반 테마 보정계수"""
    if not sector_performance:
        return 1.0

    rates = sorted(sector_performance.values(), reverse=True)
    if not rates:
        return 1.0

    # 테마에 해당하는 업종 찾기
    theme_rate = None
    for sector_name, rate in sector_performance.items():
        if theme in sector_name or sector_name in theme:
            theme_rate = rate
            break

    if theme_rate is None:
        return 1.0

    # 상위/중위/하위 판단
    top_third = len(rates) // 3
    if theme_rate >= rates[min(top_third, len(rates) - 1)]:
        return THEME_BOOST_HOT
    elif theme_rate >= rates[min(top_third * 2, len(rates) - 1)]:
        return THEME_BOOST_WARM
    else:
        return THEME_BOOST_COLD


def _score_durability(articles, ticker, news_history=None):
    """지속성 (Durability) — 25점 만점
    7일 뉴스 이력과 비교하여 지속적 관심 vs 일회성 판단
    """
    if not articles:
        return 0

    today_count = len(articles)

    if not news_history or ticker not in news_history:
        # 이력 없으면 기존 로직
        if today_count >= 5:
            return 20
        elif today_count >= 3:
            return 12
        elif today_count >= 1:
            return 5
        return 0

    history = news_history[ticker]
    past_counts = [day.get('count', 0) for day in history]

    if not past_counts:
        if today_count >= 5:
            return 20
        elif today_count >= 3:
            return 12
        return 5

    avg_past = sum(past_counts) / len(past_counts)
    consecutive_days = sum(1 for c in past_counts if c > 0)

    score = 0

    # 기본 점수 (오늘 뉴스 수)
    if today_count >= 5:
        score += 10
    elif today_count >= 3:
        score += 7
    else:
        score += 3

    # 연속성 보너스 (최근 7일 중 뉴스가 있었던 날)
    if consecutive_days >= 5:
        score += 10  # 5일 이상 지속 관심
    elif consecutive_days >= 3:
        score += 7   # 3일 이상
    elif consecutive_days >= 1:
        score += 3   # 간헐적

    # 증가 추세 보너스
    if avg_past > 0 and today_count > avg_past * 1.5:
        score += 5   # 관심 급증

    return min(score, 25)


def _score_sentiment(articles):
    """감성 분석 (Sentiment) — 10점 만점
    금융 사전 기반 긍정/부정 비율
    """
    if not articles:
        return 5  # 중립

    pos_count = 0
    neg_count = 0

    for a in articles:
        title = a.get('title', '')
        for word in SENTIMENT_POSITIVE:
            if word in title:
                pos_count += 1
                break
        for word in SENTIMENT_NEGATIVE:
            if word in title:
                neg_count += 1
                break

    total = pos_count + neg_count
    if total == 0:
        return 5  # 중립

    pos_ratio = pos_count / total

    if pos_ratio >= 0.8:
        return 10
    elif pos_ratio >= 0.6:
        return 8
    elif pos_ratio >= 0.4:
        return 5  # 혼재
    elif pos_ratio >= 0.2:
        return 2
    else:
        return 0  # 대부분 부정


def _score_analyst(reports, close_price):
    """증권사 리포트 점수 — 15점 만점
    목표가 괴리율 + 투자의견 기반
    """
    if not reports or close_price <= 0:
        return 0

    score = 0

    # 최근 리포트의 투자의견
    opinion_scores = {'매수': 5, '적극매수': 5, 'BUY': 5, 'Strong Buy': 5,
                      '비중확대': 4, 'Overweight': 4,
                      '중립': 2, 'Neutral': 2, 'Hold': 2, '시장수익률': 2,
                      '비중축소': 0, '매도': 0, 'Sell': 0, 'Underweight': 0}

    best_opinion = 0
    target_prices = []

    for r in reports[:3]:  # 최근 3개만
        opinion = r.get('opinion', '')
        for key, val in opinion_scores.items():
            if key in opinion:
                best_opinion = max(best_opinion, val)
                break

        tp = r.get('target_price', 0)
        if tp > 0:
            target_prices.append(tp)

    score += best_opinion

    # 목표가 괴리율 (현재가 대비 상승 여력)
    if target_prices:
        avg_target = sum(target_prices) / len(target_prices)
        upside = ((avg_target - close_price) / close_price) * 100

        if upside >= 50:
            score += 10
        elif upside >= 30:
            score += 8
        elif upside >= 15:
            score += 5
        elif upside >= 0:
            score += 2
        # 목표가 < 현재가이면 0점

    return min(score, 15)


def _score_turnover(turnover_rank_pct):
    """시총 대비 거래대금 (Turnover) — 25점 만점
    상위 종목 내 상대 비교 (백분위 기반)
    """
    if turnover_rank_pct <= 10:
        return 25
    elif turnover_rank_pct <= 25:
        return 20
    elif turnover_rank_pct <= 50:
        return 15
    elif turnover_rank_pct <= 75:
        return 10
    else:
        return 5


def calculate_score(articles, date_str, ticker, close_price=0,
                    sector_performance=None, turnover_rank_pct=50):
    """호재 점수 종합 산출 v3
    B(20) + Q(25) + T(30) + TV(25) = 100점

    Returns:
        dict: {'total': int, 'detail': {...}}
    """
    deduped = deduplicate_news(articles)

    buzz = _score_buzz(deduped)
    quality = _score_quality(deduped)
    type_score = _score_type(deduped, sector_performance)
    turnover = _score_turnover(turnover_rank_pct)

    total = min(buzz + quality + type_score + turnover, 100)

    return {
        'total': total,
        'detail': {
            'buzz': buzz,
            'quality': quality,
            'type': type_score,
            'turnover': turnover,
        }
    }


def _market_context_multiplier(articles, ticker, all_news_map):
    """시장 컨텍스트 보정계수
    같은 테마 뉴스가 많은 종목에 걸쳐 있으면 시장 전체 테마 → 할인
    개별 종목에만 집중되면 → 보너스
    """
    if not articles or not all_news_map:
        return 1.0

    # 이 종목의 주요 키워드 추출
    all_titles = ' '.join(a.get('title', '') for a in articles)
    my_themes = set()
    for keyword, theme in KEYWORD_THEME_MAP.items():
        if keyword in all_titles:
            my_themes.add(theme)

    if not my_themes:
        return 1.0

    # 동일 테마를 가진 다른 종목 수 카운트
    theme_stock_count = {}
    for theme in my_themes:
        count = 0
        for other_ticker, other_articles in all_news_map.items():
            if other_ticker == ticker:
                continue
            other_titles = ' '.join(a.get('title', '') for a in other_articles)
            for keyword, t in KEYWORD_THEME_MAP.items():
                if t == theme and keyword in other_titles:
                    count += 1
                    break
        theme_stock_count[theme] = count

    # 가장 많이 공유된 테마 기준으로 판단
    max_shared = max(theme_stock_count.values()) if theme_stock_count else 0

    if max_shared >= MARKET_THEME_MIN_STOCKS:
        return MARKET_THEME_DISCOUNT  # 시장 전체 테마 → 할인
    elif max_shared <= 2:
        return UNIQUE_THEME_BONUS     # 개별 종목 호재 → 보너스
    else:
        return 1.0


# ══════════════════════════════════════
# 테마 태그 추출 (기사 본문 기반 동적 추출)
# ══════════════════════════════════════

_THEME_PATTERNS = [
    re.compile(r'([가-힣A-Za-z0-9/]{2,10})\s*관련주'),
    re.compile(r'([가-힣A-Za-z0-9/]{2,10})\s*테마주'),
    re.compile(r'([가-힣A-Za-z0-9/]{2,10})\s*테마(?:[^주]|$)'),
    re.compile(r'([가-힣A-Za-z0-9/]{2,10})\s*수혜주'),
    re.compile(r'([가-힣A-Za-z0-9/]{2,10})\s*대장주'),
    re.compile(r'([가-힣A-Za-z0-9/]{2,10})주(?:가|는|도|의)?\s*(?:강세|급등|상한가|상승|올라|치솟|폭등)'),
    re.compile(r'([가-힣A-Za-z0-9/]{2,10})\s*(?:업종|종목|섹터)(?:은|이|도|의)?\s*(?:\d|강세|급등|상승|상한가|올라|폭등)'),
    # 추가 패턴
    re.compile(r'([가-힣A-Za-z0-9/]{2,10})\s*관련\s*종목'),
    re.compile(r'([가-힣A-Za-z0-9/]{2,10})\s*핵심주'),
    re.compile(r'([가-힣A-Za-z0-9/]{2,10})\s*대표주'),
    re.compile(r'([가-힣A-Za-z0-9/]{2,10})\s*열풍'),
    re.compile(r'([가-힣A-Za-z0-9/]{2,10})\s*산업(?:이|은|도)?\s*(?:강세|급등|상승|성장|확대|호조)'),
]

_THEME_NOISE = {
    '해당', '전체', '국내', '일부', '다수', '특정', '대형', '중소형',
    '관련', '소형', '시장', '증시', '주식', '코스피', '코스닥',
    '개별', '상승', '하락', '주요', '이날', '오늘', '어제',
    '우리', '이번', '종목', '투자', '매수', '매도', '최근',
    '해외', '글로벌', '전일', '금일', '장중', '오전', '오후',
    '올해', '내년', '지난', '이달', '연속', '이후', '거래',
    '우려', '직접적', '직접', '가능성', '전망', '기대', '불안', '부진',
    '전쟁', '긴장', '불확실성', '위기', '리스크', '충돌', '갈등',
    '일제히', '줄줄이', '동반', '동시', '변동성',
    '중심으로', '제외한', '포함한', '대비', '경쟁',
    '주도', '주목', '성장', '확대', '강화', '촉진',
    '중동', '미국', '중국', '유럽', '일본', '북한',
    '스테이블코', '스테이블코인',
    # 추가 노이즈
    '서울', '한국', '아시아', '세계', '테마', '섹터', '업종',
    '속보', '단독', '기사', '보도', '뉴스',
    '실시간', '오전장', '오후장', '마감',
    '하반기', '상반기', '분기', '연간',
    '대규모', '소규모', '초대형', '중대형',
    '소식통', '관계자', '전문가', '애널리스트',
}


def _clean_theme_tag(raw):
    """추출된 태그에서 조사/접미사/용언어미 제거"""
    tag = raw.strip().strip('·')
    # 가운데점 연결 → 첫 번째 부분만
    if '·' in tag:
        parts = [p.strip() for p in tag.split('·') if len(p.strip()) >= 2]
        tag = parts[0] if parts else tag
    # 용언 어미 제거 (하는, 되는, 있는 등)
    tag = re.sub(r'(?:하는|되는|있는|없는|적인|에서|부터|까지|으로|에의)$', '', tag)
    # 한글 조사/접미사 제거 (2회 반복)
    tag = re.sub(r'[에을를은는의이가와과도로서께한인적하]$', '', tag)
    tag = re.sub(r'[에을를은는의이가와과도로서께한인적하]$', '', tag)
    return tag


def _extract_themes_from_text(text):
    """텍스트에서 테마 패턴 추출 → Counter"""
    from collections import Counter
    counts = Counter()
    for pattern in _THEME_PATTERNS:
        for m in pattern.finditer(text):
            tag = _clean_theme_tag(m.group(1))
            if len(tag) >= 2 and tag not in _THEME_NOISE:
                counts[tag] += 1
    return counts


def extract_theme_tag(articles, article_bodies=None, stock_name=''):
    """기사 본문에서 테마 태그를 동적 추출

    전략:
    1. 기사 본문에서 종목명이 등장하는 문단을 우선 분석
    2. 종목명 근처의 테마 패턴이 가장 정확함
    3. 매치 없으면 전체 본문 → 제목 순으로 fallback

    Args:
        articles: 뉴스 기사 목록 (title 포함)
        article_bodies: 기사 본문 텍스트 리스트
        stock_name: 종목명 (문단 필터링용)

    Returns:
        str: 테마 태그 (예: '광통신', '알루미늄', '방산')
    """
    bodies = [b for b in (article_bodies or []) if b]

    # 전략 1: 종목명 근처 200자 윈도우에서 추출 (가장 정확)
    if bodies and stock_name:
        windows = []
        for body in bodies:
            idx = 0
            while True:
                pos = body.find(stock_name, idx)
                if pos == -1:
                    break
                start = max(0, pos - 100)
                end = min(len(body), pos + len(stock_name) + 100)
                windows.append(body[start:end])
                idx = pos + 1
        if windows:
            counts = _extract_themes_from_text('\n'.join(windows))
            if counts:
                return counts.most_common(1)[0][0]

    # 전략 2: 전체 본문에서 추출
    if bodies:
        counts = _extract_themes_from_text('\n'.join(bodies))
        if counts:
            return counts.most_common(1)[0][0]

    # 전략 3: 제목에서 추출 (fallback)
    if articles:
        titles = ' '.join(a.get('title', '') for a in articles)
        counts = _extract_themes_from_text(titles)
        if counts:
            return counts.most_common(1)[0][0]

    return ''


# ══════════════════════════════════════
# 상승 이유 텍스트 생성
# ══════════════════════════════════════

def _find_best_action(titles_text):
    """뉴스 제목 텍스트에서 가장 구체적인 액션 키워드를 찾는다.

    Returns:
        tuple: (action_text, priority) or (None, 0)
    """
    best = (None, 0)
    for keyword, action, priority in _ACTION_TABLE:
        if keyword in titles_text and priority > best[1]:
            best = (action, priority)
    return best


# 의미 없는 theme_tag 필터 (테마 추출 오류로 잡힌 일반어)
_BAD_THEME_TAGS = {
    '이전', '이후', '관련', '전체', '국내', '해당', '특정', '일부',
    '다수', '대형', '소형', '시장', '증시', '종합', '기타', '상승',
    '하락', '오늘', '어제', '지금', '우리', '이번', '최근', '주요',
    '거래', '투자', '매수', '매도', '전망', '기대', '불안', '전일',
    '금일', '장중', '오전', '오후', '마감', '속보', '단독', '경제',
    '지목하면', '중심으로', '포함한', '제외한', '동시에',
    '대표', '사장', '회장', '부사장', '이사', '선임', '신임',
    '상장폐지', '거래정지', '관리종목',
    '정치', '검색', '다양', '밸류', '계속', '이용', '정보', '결과',
    '이용자', '활용', '방법', '성과', '현재', '상태', '변화', '수준',
    '현황', '분위기', '소식', '자체', '문제', '경우', '내용', '부분',
    '사업', '상품', '사실', '과정', '조건', '상황', '수요', '쪽',
}


def _is_valid_theme_tag(tag):
    """theme_tag가 상승 이유에 쓸 만한지 판별"""
    if not tag or len(tag) < 2:
        return False
    if tag in _BAD_THEME_TAGS:
        return False
    # 순수 숫자만인 경우 제외
    if tag.isdigit():
        return False
    # 용언/형용사 어미로 끝나면 제외 (동사형 잘못 추출)
    bad_suffixes = ('하면', '하는', '되는', '있는', '없는', '들이', '자들', '에서',
                    '해서', '에게', '까지', '에도', '지만', '속해', '해')
    if any(tag.endswith(s) for s in bad_suffixes):
        return False
    # 잘못 추출되기 쉬운 접미어
    bad_prefixes = ('계속', '밸류체', '정치인')
    if tag in bad_prefixes:
        return False
    return True


def extract_theme_from_reason(reason_text):
    """상승 이유 텍스트에서 테마 키워드 추출 (fallback)

    Toss AI 상승이유나 generate_rise_reason 결과에서 핵심 테마만 추출.
    예: '반도체 투자 확대' → '반도체'
        '원전 수주 확대' → '원전'
        '광통신 테마 강세' → '광통신'
        '실적 호조' → '' (테마 아닌 일반 사유)
    """
    if not reason_text:
        return ''

    _ACTION_WORDS = {
        '투자', '확대', '수주', '수출', '강세', '급등', '호조', '개선', '전환',
        '성장', '증설', '본격화', '모멘텀', '부각', '수혜', '급증', '유입',
        '기대', '돌파', '체결', '진입', '진전', '취득', '매입', '소각', '기록',
        '급등세', '교체', '이슈', '테마', '관련', '시장', '관심', '증가',
        '거래', '증권사', '매수', '의견', '정책', '정부', '보조금',
        '외국인', '기관', '순매수', '매수세', '수급', '상한가',
        '설비', '생산', '해외', '진출', '착공', '납품', '공급', '계약', '신규',
        '실적', '서프라이즈', '영업이익', '순이익', '매출',
        '인수', '합병', '기대감', '경영진', '특허', '지분',
        '자사주', '배당', '주주환원', '상장', '분할', '협력', '사업',
        '허가', '임상', '승인', '양산',
    }

    words = reason_text.split()
    for w in words:
        if w not in _ACTION_WORDS and _is_valid_theme_tag(w):
            return w
    return ''


def _extract_subject_from_titles(articles, stock_name=''):
    """뉴스 제목에서 핵심 주제어를 추출한다.
    종목명/일반어를 제외한 2~6자 고유명사를 찾는다.
    """
    import re as _re

    # "OOO 관련주", "OOO 테마" 패턴에서 OOO 추출
    all_titles = ' '.join(a.get('title', '') for a in articles)
    subject_pattern = _re.compile(r'([가-힣A-Za-z0-9]{2,8})\s*(?:관련주|테마주|테마|수혜주|대장주)')
    for m in subject_pattern.finditer(all_titles):
        candidate = m.group(1).strip()
        # _BAD_THEME_TAGS와 동일한 필터 적용
        if _is_valid_theme_tag(candidate) and candidate != stock_name:
            return candidate

    return ''


def generate_rise_reason(articles, analyst_reports=None, theme_tag='', stock_name=''):
    """Toss 스타일 간결한 상승 이유 생성

    출력 예시:
    - "반도체 투자 확대"
    - "광통신 테마 강세"
    - "신약 FDA 승인 기대"
    - "실적 개선 기대"
    - "자사주 소각"
    """
    all_titles = ''
    if articles:
        all_titles = ' '.join(a.get('title', '') for a in articles)

    action_text, action_priority = _find_best_action(all_titles)

    # ── Priority 1: theme_tag + 구체적 액션 ──
    valid_tag = _is_valid_theme_tag(theme_tag)
    if valid_tag:
        if action_text and action_priority >= 4:
            # 테마와 액션이 겹치면 액션만 사용
            if theme_tag in action_text:
                return action_text
            return f'{theme_tag} {action_text}'
        # 액션이 약하면 "테마 강세"
        return f'{theme_tag} 테마 강세'

    # ── Priority 2: 뉴스 제목에서 주제어 추출 + 액션 ──
    subject = _extract_subject_from_titles(articles, stock_name) if articles else ''
    if subject and action_text and action_priority >= 4:
        if subject in action_text:
            return action_text
        return f'{subject} {action_text}'

    # ── Priority 3: 액션만 사용 ──
    if action_text and action_priority >= 3:
        return action_text

    # ── Priority 4: 증권사 리포트 ──
    if analyst_reports:
        buy_reports = [r for r in analyst_reports[:3]
                       if any(w in r.get('opinion', '') for w in ['매수', 'BUY', '비중확대'])]
        if buy_reports:
            return '증권사 매수 의견'

    # ── Fallback ──
    if articles and len(articles) >= 3:
        return '시장 관심 증가'

    return '거래 급증'


# ══════════════════════════════════════
# 거래 강도 v2
# ══════════════════════════════════════

def calculate_trading_intensity(today_value, avg_5day_value,
                                inst_net=0, foreign_net=0,
                                turnover_rank_pct=50):
    """거래 강도 레이블 산출 v2

    Args:
        today_value: 오늘 거래대금
        avg_5day_value: 5일 평균 거래대금
        inst_net: 기관 순매수 금액
        foreign_net: 외국인 순매수 금액
        turnover_rank_pct: 회전율 백분위 (0=최고, 100=최저)

    Returns:
        tuple: (레이블, 상세dict)
    """
    if avg_5day_value <= 0 or today_value <= 0:
        return '보통', {'ratio': 0, 'supply': 'N/A', 'turnover_pct': turnover_rank_pct}

    ratio_pct = (today_value / avg_5day_value) * 100

    # 수급 보정
    if inst_net > 0 and foreign_net > 0:
        supply_type = 'both'
    elif inst_net > 0:
        supply_type = 'institution'
    elif foreign_net > 0:
        supply_type = 'foreign'
    else:
        supply_type = 'retail'

    multiplier = SUPPLY_DEMAND_MULTIPLIER.get(supply_type, 1.0)
    adjusted_ratio = ratio_pct * multiplier

    # 회전율 보너스 (상위 10%이면 1등급 업)
    turnover_bonus = turnover_rank_pct <= TURNOVER_BONUS_PERCENTILE

    # 등급 판정
    if adjusted_ratio >= TRADING_INTENSITY['폭발']:
        label = '폭발'
    elif adjusted_ratio >= TRADING_INTENSITY['급증']:
        label = '급증'
    elif adjusted_ratio >= TRADING_INTENSITY['활발']:
        label = '활발'
    else:
        label = '보통'

    # 회전율 보너스 적용 (1등급 업)
    if turnover_bonus and label != '폭발':
        upgrade = {'보통': '활발', '활발': '급증', '급증': '폭발'}
        label = upgrade.get(label, label)

    detail = {
        'ratio': round(ratio_pct, 1),
        'adjusted_ratio': round(adjusted_ratio, 1),
        'supply': supply_type,
        'multiplier': multiplier,
        'turnover_pct': turnover_rank_pct,
        'turnover_bonus': turnover_bonus,
    }

    return label, detail
