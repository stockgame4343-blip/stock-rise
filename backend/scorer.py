"""호재 점수 산출, 거래 강도 레이블, 상승 이유 텍스트 생성"""
import re
import logging

from config import FAVOR_TYPE_SCORES, MAJOR_PRESS, TRADING_INTENSITY

logger = logging.getLogger(__name__)

# 상승 이유 텍스트 매핑 (키워드 그룹 → 이유 문장)
_REASON_MAP = [
    (['실적', '흑자', '흑자전환', '영업이익', '매출', '순이익'], '실적 호조 기대감'),
    (['수주', '계약', '납품', '공급'], '신규 수주/계약 체결'),
    (['신약', '임상', '승인', 'FDA', '허가'], '신약/임상 관련 호재'),
    (['AI', '반도체', 'HBM', 'GPU', 'NPU'], 'AI/반도체 테마 수혜'),
    (['2차전지', '배터리', '양극재', '음극재', '전해질'], '2차전지/배터리 테마'),
    (['로봇', '자율주행', '드론', '모빌리티'], '로봇/자율주행 테마'),
    (['정책', '규제', '정부', '법안', '국책'], '정부 정책/규제 수혜'),
    (['배당', '자사주', '주주환원', '소각'], '주주환원 정책 기대'),
    (['인수', '합병', 'M&A', '지분'], 'M&A 관련 이슈'),
    (['테마', '관련주', '급등', '상한가'], '테마/시장 이슈 부각'),
    (['외국인', '기관', '매수', '순매수'], '기관/외국인 수급 유입'),
]


def _count_keyword_matches(text, keywords):
    """텍스트에서 키워드 매치 수 반환"""
    count = 0
    for kw in keywords:
        if kw in text:
            count += 1
    return count


def _score_buzz(articles):
    """뉴스 양 (Buzz) — 20점 만점"""
    n = len(articles)
    if n == 0:
        return 0
    elif n <= 2:
        return 8
    elif n <= 5:
        return 14
    else:
        return 20


def _score_quality(articles):
    """뉴스 질 (Quality) — 25점 만점
    - 주요 언론사 비율: 최대 15점
    - 구체적 수치 포함: 최대 10점
    """
    if not articles:
        return 0

    # 주요 언론사 비율 (15점)
    major_count = 0
    for a in articles:
        source = a.get('source', '')
        if any(press in source for press in MAJOR_PRESS):
            major_count += 1

    major_ratio = major_count / len(articles) if articles else 0
    source_score = round(major_ratio * 15)

    # 구체적 수치 포함 여부 (10점) — 숫자+단위 패턴 탐지
    numeric_pattern = re.compile(r'\d+[\.\d]*\s*(억|조|%|만|원|달러|건)')
    numeric_count = 0
    for a in articles:
        title = a.get('title', '')
        if numeric_pattern.search(title):
            numeric_count += 1

    numeric_ratio = numeric_count / len(articles) if articles else 0
    numeric_score = round(numeric_ratio * 10)

    return min(source_score + numeric_score, 25)


def _score_type(articles):
    """호재 유형 (Type) — 30점 만점
    뉴스 제목에서 가장 높은 호재 유형 점수를 반환
    """
    if not articles:
        return 0

    max_score = 0
    all_titles = ' '.join(a.get('title', '') for a in articles)

    for keyword, score in FAVOR_TYPE_SCORES.items():
        if keyword in all_titles:
            max_score = max(max_score, score)

    return max_score


def _score_durability(articles, date_str, ticker):
    """지속성 (Durability) — 25점 만점
    현재는 당일 뉴스 수 기반 간이 판단.
    TODO: 과거 3일 뉴스 데이터 연동 시 정확도 향상 가능
    """
    if not articles:
        return 0

    # 뉴스가 많을수록 지속적 관심 가능성 높음 (간이 로직)
    n = len(articles)
    if n >= 5:
        return 25
    elif n >= 3:
        return 15
    elif n >= 1:
        return 5
    return 0


def calculate_score(articles, date_str, ticker):
    """호재 점수 종합 산출 (100점 만점)

    Returns:
        dict: {'total': int, 'detail': {'buzz': int, 'quality': int, 'type': int, 'durability': int}}
    """
    buzz = _score_buzz(articles)
    quality = _score_quality(articles)
    type_score = _score_type(articles)
    durability = _score_durability(articles, date_str, ticker)

    total = buzz + quality + type_score + durability

    return {
        'total': min(total, 100),
        'detail': {
            'buzz': buzz,
            'quality': quality,
            'type': type_score,
            'durability': durability,
        }
    }


def generate_rise_reason(articles):
    """뉴스 제목 키워드 기반 상승 이유 텍스트 자동 생성"""
    if not articles:
        return '거래 급증에 따른 상승'

    all_titles = ' '.join(a.get('title', '') for a in articles)
    best_reason = '거래 급증에 따른 상승'
    best_count = 0

    for keywords, reason in _REASON_MAP:
        count = _count_keyword_matches(all_titles, keywords)
        if count > best_count:
            best_count = count
            best_reason = reason

    return best_reason


def calculate_trading_intensity(today_value, prev_3day_avg):
    """거래 강도 레이블 산출 (3거래일 평균 대비)

    Args:
        today_value: 당일 거래대금
        prev_3day_avg: 직전 3거래일 평균 거래대금

    Returns:
        str: '폭발' / '급증' / '활발' / '보통'
    """
    if prev_3day_avg <= 0 or today_value <= 0:
        return '보통'

    ratio_pct = (today_value / prev_3day_avg) * 100

    # TRADING_INTENSITY: {'폭발': 500, '급증': 300, '활발': 150, '보통': 0}
    if ratio_pct >= TRADING_INTENSITY['폭발']:
        return '폭발'
    elif ratio_pct >= TRADING_INTENSITY['급증']:
        return '급증'
    elif ratio_pct >= TRADING_INTENSITY['활발']:
        return '활발'
    else:
        return '보통'
