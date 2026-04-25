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

# ─── 카드별 표시 개수 ────────────────────────────────
TOP_THEMES_PRE = 4         # pre  — 키워드 카드 수
TOP_HOT_THEMES = 2         # pre  — 강조 hot 처리 상위 N
TOP_THEMES_PRE3 = 4        # pre3 — 테마 수
TOP_STOCKS_PER_THEME = 4   # pre3 — 테마당 종목 수
LEADER_MEMBERS_TOP = 8     # leader2 — 멤버 수
TOP_ISSUES_CLOSE2 = 3      # close2 — 핵심 이슈 수
TOP_SECTORS_CLOSE2 = 6     # close2 — 섹터 카드 수
NY_NOTES_TOP = 2           # pre2  — 한국 시장 관점 노트 수

# ─── 그룹화 임계값 ───────────────────────────────────
MIN_THEME_MEMBERS = 2          # _group_by_theme 일반 임계
MIN_SECTOR_MEMBERS = 2
KEYWORD_MIN_THEME_MEMBERS = 5  # pre/pre3 카드 키워드 — 의미 있는 큰 테마만 (종목수 ≥ N)
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

# ─── 요일 라벨 ───────────────────────────────────────
WEEKDAY_KO = ['월', '화', '수', '목', '금', '토', '일']
WEEKDAY_EN = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']

# ─── 시리즈 컬러 토큰 (Phase 2 템플릿에서 사용) ─────
COLOR_TOKENS = {
    'pre': {
        'bg1': '#0a0f2a', 'bg2': '#0e1a4a', 'bg3': '#1a2e6a',
        'accent': '#ffa64d', 'accent2': '#ff6b6b',
        'muted': '#a6bce0', 'text_dim': '#6a82b0',
        'card_bg': 'rgba(255,255,255,.06)', 'card_border': 'rgba(255,255,255,.12)',
        'hot_bg1': 'rgba(255,166,77,.18)', 'hot_bg2': 'rgba(255,107,107,.04)',
        'hot_border': 'rgba(255,166,77,.45)',
    },
    'leader': {
        'bg1': '#1a0505', 'bg2': '#330808', 'bg3': '#4a0f0f',
        'accent': '#ffd166', 'accent2': '#ff6b6b',
        'muted': '#e8bcbc', 'text_dim': '#8a6a6a',
        'card_bg': 'rgba(255,255,255,.06)', 'card_border': 'rgba(255,255,255,.12)',
        'hot_bg1': 'rgba(255,209,102,.22)', 'hot_bg2': 'rgba(255,107,107,.08)',
        'hot_border': 'rgba(255,209,102,.45)',
    },
    'close': {
        'bg1': '#1a0a2a', 'bg2': '#2a1040', 'bg3': '#3a1550',
        'accent': '#c7a3ff', 'accent2': '#ff6b6b',
        'muted': '#b8a3d8', 'text_dim': '#7a6a99',
        'card_bg': 'rgba(255,255,255,.06)', 'card_border': 'rgba(255,255,255,.12)',
        'hot_bg1': 'rgba(255,107,107,.18)', 'hot_bg2': 'rgba(255,107,107,.02)',
        'hot_border': 'rgba(255,107,107,.4)',
    },
}
