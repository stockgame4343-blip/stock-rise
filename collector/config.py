"""설정 상수 (Vercel 배포용)"""
import os

# 경로
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'public', 'data'))
COLLECTOR_DIR = os.path.dirname(os.path.abspath(__file__))
SECTOR_CACHE_PATH = os.path.join(COLLECTOR_DIR, 'sector_cache.json')
NEWS_HISTORY_PATH = os.path.join(COLLECTOR_DIR, 'news_history.json')

# 수집 설정
TOP_N = 100
DATA_RETENTION_DAYS = 90
NEWS_HISTORY_DAYS = 7

# 크롤링 설정
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
]
REQUEST_DELAY_MIN = 1.0
REQUEST_DELAY_MAX = 2.5

# ── 거래 강도 설정 ──
# 5일 평균 대비 기준 (%)
TRADING_INTENSITY = {
    '폭발': 500,
    '급증': 300,
    '활발': 150,
    '보통': 0,
}

# 수급 보정계수 (기관/외인 순매수 반영)
SUPPLY_DEMAND_MULTIPLIER = {
    'both':        1.3,   # 기관+외인 동반 순매수
    'institution': 1.1,   # 기관만 순매수
    'foreign':     1.1,   # 외인만 순매수
    'retail':      0.9,   # 개인만
}

# 회전율 보너스 (거래대금/시총 상위 10% → 1등급 업)
TURNOVER_BONUS_PERCENTILE = 10

# ── 호재 점수 설정 ──
# 호재 유형별 기본 점수 (Type 카테고리, 30점 만점)
FAVOR_TYPE_SCORES = {
    '실적': 30, '흑자': 30, '흑자전환': 30, '영업이익': 30, '매출': 28,
    '수주': 25, '계약': 25, '납품': 25, '공급': 25,
    '신약': 25, '임상': 25, '승인': 25, 'FDA': 25,
    '정책': 20, '규제': 20, '정부': 20, '법안': 20,
    'AI': 15, '반도체': 15, 'HBM': 15, 'GPU': 15, '2차전지': 15, '로봇': 15,
    '배당': 12, '자사주': 12, '주주환원': 12,
    '인수': 15, '합병': 15, 'M&A': 15,
    '테마': 10, '관련주': 10, '급등': 10,
}

# 키워드 → 테마 매핑 (동적 가중치용)
KEYWORD_THEME_MAP = {
    'AI': 'AI', '반도체': '반도체', 'HBM': '반도체', 'GPU': 'AI', 'NPU': 'AI',
    '2차전지': '2차전지', '배터리': '2차전지', '양극재': '2차전지',
    '로봇': '로봇', '자율주행': '자율주행', '드론': '드론',
    '신약': '바이오', '임상': '바이오', 'FDA': '바이오', '승인': '바이오',
    '실적': '실적', '흑자': '실적', '영업이익': '실적', '매출': '실적',
    '수주': '수주', '계약': '수주', '납품': '수주',
    '정책': '정책', '정부': '정책', '규제': '정책',
    '배당': '주주환원', '자사주': '주주환원', '주주환원': '주주환원',
}

# 주요 언론사 (Quality 카테고리 가중치)
MAJOR_PRESS = [
    '한국경제', '매일경제', '연합뉴스', '조선비즈', '머니투데이',
    '이데일리', '서울경제', '파이낸셜뉴스', '헤럴드경제', '한국투자증권',
    '삼성증권', 'NH투자증권', '키움증권', 'KB증권',
]

# 금융 감성 사전 (긍정/부정)
SENTIMENT_POSITIVE = [
    '호조', '호실적', '흑자', '흑자전환', '서프라이즈', '깜짝',
    '최대', '최고', '신고가', '신기록', '돌파', '상향', '목표가 상향',
    '매수', '비중확대', '적극매수', '수혜', '호재', '기대감',
    '수주', '계약', '납품', '체결', '성장', '확대', '증가',
    '승인', '허가', '통과', '합격', '선정', '인증',
    '배당', '자사주', '소각', '주주환원', '상장', '공모',
    '반등', '회복', '개선', '턴어라운드', '어닝서프라이즈',
]
SENTIMENT_NEGATIVE = [
    '부진', '악화', '적자', '감소', '하락', '급락', '폭락',
    '쇼크', '어닝쇼크', '실망', '하향', '목표가 하향',
    '매도', '비중축소', '리스크', '우려', '악재', '위기',
    '소송', '제재', '벌금', '과징금', '횡령', '배임',
    '감자', '상폐', '상장폐지', '관리종목', '거래정지',
    '공매도', '반대매매', '마진콜', '유상증자', '오버행',
]

# 뉴스 중복 판단 자카드 유사도 임계값
NEWS_DEDUP_THRESHOLD = 0.5

# 시장 컨텍스트: 동일 테마 N종목 이상이면 시장 전체 테마로 판단
MARKET_THEME_MIN_STOCKS = 10
MARKET_THEME_DISCOUNT = 0.7    # 시장 전체 테마일 때 할인
UNIQUE_THEME_BONUS = 1.2       # 개별 종목만의 호재일 때 보너스

# 업종 등락률 테마 보정 범위
THEME_BOOST_HOT = 1.4    # 업종 등락률 상위
THEME_BOOST_WARM = 1.2   # 업종 등락률 중위
THEME_BOOST_COLD = 0.8   # 업종 등락률 하위
