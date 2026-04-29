"""카드 모듈 설정 — 모든 매직 넘버는 여기서만.

`collector/config.py`와 분리: 카드 전용 설정.
"""
import os

# ─── 경로 ────────────────────────────────────────────
CARDS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CARDS_DIR)
DATA_DIR = os.environ.get(
    'CARDS_DATA_DIR',
    os.path.join(PROJECT_ROOT, 'public', 'data'),
)
OUTPUT_DIR = os.environ.get(
    'CARDS_OUTPUT_DIR',
    os.path.join(PROJECT_ROOT, 'public', 'cards'),
)
# 중간 산출물(HTML)은 public 외부 — Vercel 배포에 포함되지 않음
HTML_OUT_DIR = os.environ.get(
    'CARDS_HTML_DIR',
    os.path.join(CARDS_DIR, '_render'),
)
TEMPLATE_DIR = os.path.join(CARDS_DIR, 'templates')

# ─── 카드 출력 크기 ──────────────────────────────────
CARD_WIDTH = 1080
CARD_HEIGHT = 1080

# ─── 점수 정규화 (collector/scorer.calculate_daejang_score 와 일치) ─
# tp(테마강도) + tl(대장성) + ti(거래강도) = 100
TP_MAX = 35
TL_MAX = 45
TI_MAX = 20
SCORE_NORMALIZED_MAX = 100

# ─── 카드별 표시 개수 (카드뉴스 원칙: 한 장 = 한 메시지, 정보 최소) ─
TOP_DAWN_HEADLINES = 3     # pre0 — 새벽 브리핑 헤드라인 수
PRE2_HEADLINES_TOP = 2     # pre2(뉴욕 마감) — 마켓 무빙 헤드라인 수
DAWN_FETCH_POOL = 30       # 네이버 RANK 에서 가져올 후보 수 (필터 통과 후 상위 N 선택)

# 글로벌 시장 영향 키워드 화이트리스트 — 새벽 브리핑·뉴욕 마감 헤드라인 필터
# 매치 안 되면 제외 (한국 미시 뉴스·종목별 단독 뉴스 등 차단)
DAWN_WHITELIST = [
    # US 시장·정책
    'fed', 'fomc', '연준', '금리', 'cpi', '인플레', '파월', '미국채',
    '나스닥', '다우', 's&p', 'sp500', '뉴욕', 'ny', '미증시', '미국',
    # 빅테크·반도체
    '엔비디아', 'nvidia', 'nvda', 'tsmc', '애플', 'apple', 'aapl',
    '테슬라', 'tesla', 'tsla', '아마존', 'amzn', '메타', 'meta',
    '마이크로소프트', 'msft', '구글', 'google', 'goog',
    '빅테크', 'ai', 'hbm', '반도체', 'asml', '브로드컴',
    # 에너지·원자재
    '유가', 'wti', '브렌트', 'opec', '아람코', '사우디', '원유',
    '천연가스', 'lng', '구리', '금값', '귀금속',
    # 지정학·정책
    '트럼프', '관세', 'tariff', '무역분쟁', '무역전쟁',
    '우크라', '러시아', '이란', '중동', '북한', '미사일', '지정학',
    # 중국·유럽
    '중국', '시진핑', 'catl', 'byd', '알리바바', '항셍',
    'ecb', '유럽', '독일', '영국',
    # 환율·암호화폐·실적
    '달러', '환율', '엔화', '위안화',
    '비트코인', 'btc', '이더리움',
    '실적', '어닝', 'earnings',
]

# 블랙리스트 — 글로벌·마켓 키워드 매치돼도 이 단어 들어가면 제외
# (한국 증권사 분석·국내 종목·신규 상품 등 글로벌 마켓 무빙 아닌 노이즈 차단)
DAWN_BLACKLIST = [
    # 한국 증권사 리포트·분석
    'ibk', 'ibk투자', 'kb증권', 'kb투자', '한국투자', '한투', '미래에셋', '한화투자',
    '대신증권', 'nh투자', '키움', '신한투자', '삼성증권', 'sk증권',
    # 국내 종목 분석성 키워드
    '삼성sdi', '삼성바이오', '삼성전기', '삼성에스디아이',
    'sk이노', 'sk바이오', '셀트리온', '카카오', '네이버주', 'lg에너지',
    # 한국 시장·매크로 (글로벌 헤드라인이 아님)
    '국장', '한국증시', '한국 증시', '코스닥', '코스피', '개미', '동학개미',
    # 신규 상품·미시뉴스
    'etn', 'etf 상장', 'etf 출시', 'etf 신규',
    '리츠', '회생절차', '미상환', '사채', '단독]',
    '제이알', '청약', '공모주', '신고가', '관리종목',
]
TOP_THEMES_PRE = 4         # pre  — 키워드 카드 수
TOP_HOT_THEMES = 2         # pre  — 강조 hot 처리 상위 N
TOP_THEMES_PRE3 = 4        # pre3 — 테마 수
TOP_STOCKS_PER_THEME = 1   # pre3 — 테마당 대장 1명만 (이전 4 → 1)
LEADER_MEMBERS_TOP = 5     # leader2 — 멤버 수 (이전 8 → 5)
TOP_ISSUES_CLOSE2 = 3      # close2 — 핵심 이슈 수
TOP_SECTORS_CLOSE2 = 0     # close2 — 섹터 영역 제거 (한 카드 = 한 메시지)
NY_NOTES_TOP = 0           # pre2  — 한국 시장 관점 노트 제거

# ─── 그룹화 임계값 ───────────────────────────────────
MIN_THEME_MEMBERS = 2          # _group_by_theme 일반 임계
MIN_SECTOR_MEMBERS = 2
KEYWORD_MIN_THEME_MEMBERS = 5  # pre/pre3 카드 키워드 — 의미 있는 큰 테마만 (종목수 ≥ N)
KEYWORD_FALLBACK_STEPS = (4, 3, 2)  # 위 임계로 슬롯 못 채우면 단계적 완화
LEADER2_RICH_THEME_MIN = 4     # leader2 — 대장주 테마 멤버 < N 이면 day 풍부한 테마로 대체
LIMIT_UP_THRESHOLD = 29.5     # 상한가 (KOSPI/KOSDAQ 30%, 노이즈 여유 0.5%p)
LEADER_MIN_RATE = 15.0        # 대장주 후보 강세 임계 (이상 종목 중 거래대금 1위 = 그 날 대장주)
STRONG_THEME_AVG = 5.0        # close.png "강세 테마" 카운팅 임계
SECTOR_INTENSITY_STRONG = 8.0 # close2.png 섹터 강한 강세 임계
HEAVY_RATE_HIGHLIGHT = 20.0   # 노트에 종목 등락률 부각하는 임계
TOP_SHARE_FOR_FLOW = 0.5      # 상위 2종목 거래대금 비중 ≥ 50% 이면 자금 집중 멘트

# ─── 검열: 유사투자자문업 미신고 → 권유성 표현 금지 ─
# (찾을 패턴, 대체 문자열). 순서 중요 — 긴 패턴 먼저.
CENSORED_PATTERNS = [
    ('매수 의견', '리포트 공개'),
    ('매도 의견', '리포트 공개'),
    ('매수세 유입', '거래 활발'),
    ('급등 임박', ''),
    ('재료 발생', '재료 공개'),
    ('기대감', ''),
    ('낙폭과대', '하락'),
    ('수혜주', '관련주'),
    ('매수세', '거래'),
    ('매도세', '거래'),
    ('수혜', '관련'),
    ('수익률', '등락률'),
    ('기대', ''),
    ('전망', '동향'),
    ('추천', ''),
    ('목표가', ''),
    ('수익', '손익'),
    ('매수', ''),
    ('매도', ''),
    ('호재', '재료'),
    ('악재', '이슈'),
    ('강추', ''),
    ('필승', ''),
    ('대박', ''),
    ('급등', '상승'),
    ('폭등', '상승'),
]

# 검열 후 카드 텍스트에 등장하면 검증 실패로 간주할 단어
FORBIDDEN_WORDS = [
    '기대', '수혜', '매수', '매도', '추천', '목표가', '수익',
    '전망', '강추', '필승', '대박', '호재', '악재',
]

# ─── 새벽 브리핑(pre0) — 헤드라인 키워드 → 국장 영향 한 줄 매핑 ─
# 첫 매치만 사용. 매치 없으면 영향 줄 비움.
DAWN_IMPACT_MAP = [
    # 우선순위 위 → 아래. 더 구체적인 것 먼저.
    (['철강', '소재'],
     '국내 철강·소재주 영향'),
    (['아람코', '사우디', '유가', 'wti', '브렌트', '석유', 'opec', '천연가스', 'lng'],
     '정유·조선·에너지 영향'),
    (['catl', 'byd', '배터리', '전기차', 'tesla', '테슬라', 'tsla'],
     '2차전지 섹터 영향'),
    (['엔비디아', 'nvidia', 'nvda', 'tsmc', 'hbm', '파운드리', 'ai 칩', 'asml', 'sk하이닉스'],
     'HBM·반도체 섹터 영향'),
    (['반도체', '브로드컴'],
     '반도체 섹터 영향'),
    (['fomc', 'fed', '연준', '파월', 'cpi', '인플레', '미국채'],
     '환율·코스피 영향'),
    (['금리 인하', '금리 인상', '금리 동결', '금리'],
     '환율·증시 변동성 영향'),
    (['관세', 'tariff', '트럼프', '무역분쟁', '무역전쟁'],
     '수출주·환율 영향'),
    (['우크라', '러시아', '이란', '중동', '북한', '미사일', '지정학'],
     '방산·에너지 영향'),
    (['애플', 'apple', 'aapl', 'amazon', 'amzn', 'meta', 'msft', 'google', 'goog'],
     '국내 빅테크 동조 가능'),
    (['삼성', '삼성전자'],
     '국내 대형 기술주 영향'),
    (['실적', '어닝', 'earnings'],
     '글로벌 동조 가능'),
]

# ─── 요일 라벨 ───────────────────────────────────────
WEEKDAY_KO = ['월', '화', '수', '목', '금', '토', '일']
WEEKDAY_EN = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']

# ─── 시리즈 컬러 토큰 (Phase 2 템플릿에서 사용) ─────
COLOR_TOKENS = {
    # 새벽·장전 = 차분한 네이비 + 오렌지 액센트 (정보 수용 분위기)
    'pre': {
        'bg1': '#0a1130', 'bg2': '#0e1a4a', 'bg3': '#172a5a',
        'accent': '#ffb868', 'accent2': '#ff6b6b',
        'muted': '#a6bce0', 'text_dim': '#6a82b0',
        'card_bg': 'rgba(255,255,255,.05)', 'card_border': 'rgba(255,255,255,.10)',
        'hot_bg1': 'rgba(255,184,104,.16)', 'hot_bg2': 'rgba(255,107,107,.04)',
        'hot_border': 'rgba(255,184,104,.36)',
    },
    # 대장주 = 와인-자홍 (강세 강조, 갈색기 빼고 채도 ↑)
    'leader': {
        'bg1': '#1f0717', 'bg2': '#3a0e1c', 'bg3': '#54142a',
        'accent': '#ffd166', 'accent2': '#ff5577',
        'muted': '#f0c4c8', 'text_dim': '#8a6a72',
        'card_bg': 'rgba(255,255,255,.05)', 'card_border': 'rgba(255,255,255,.10)',
        'hot_bg1': 'rgba(255,209,102,.18)', 'hot_bg2': 'rgba(255,85,119,.06)',
        'hot_border': 'rgba(255,209,102,.36)',
    },
    # 마감 = 청보라 (정리·마감 분위기, 푸른기 살짝 추가)
    'close': {
        'bg1': '#181436', 'bg2': '#2a2052', 'bg3': '#3a2c66',
        'accent': '#c7a3ff', 'accent2': '#ff6b6b',
        'muted': '#b8a3d8', 'text_dim': '#7a6a99',
        'card_bg': 'rgba(255,255,255,.05)', 'card_border': 'rgba(255,255,255,.10)',
        'hot_bg1': 'rgba(199,163,255,.18)', 'hot_bg2': 'rgba(255,107,107,.04)',
        'hot_border': 'rgba(199,163,255,.36)',
    },
}
