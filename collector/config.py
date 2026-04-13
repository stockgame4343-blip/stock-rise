"""설정 상수 (Vercel 배포용 — SQLite/Flask 제거)"""
import os

# 경로
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'data'))
SECTOR_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sector_cache.json')

# 수집 설정
TOP_N = 100
DATA_RETENTION_DAYS = 90

# 크롤링 설정
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0',
]
REQUEST_DELAY_MIN = 1.0
REQUEST_DELAY_MAX = 2.5

# 거래 강도 기준 (3거래일 평균 대비 %)
TRADING_INTENSITY = {
    '폭발': 500,
    '급증': 300,
    '활발': 150,
    '보통': 0,
}

# 호재 유형별 점수 (Type 카테고리, 30점 만점)
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

# 주요 언론사 (Quality 카테고리 가중치)
MAJOR_PRESS = [
    '한국경제', '매일경제', '연합뉴스', '조선비즈', '머니투데이',
    '이데일리', '서울경제', '파이낸셜뉴스', '헤럴드경제', '한국투자증권',
    '삼성증권', 'NH투자증권', '키움증권', 'KB증권',
]
