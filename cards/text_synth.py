"""카드 텍스트 합성 + 검열.

원칙:
- LLM 호출 없음 (룰 기반).
- 모든 출력은 사실 서술. 권유성 표현 금지 (유사투자자문업 미신고).
- 외부 데이터(사용자 입력, JSON 텍스트)는 censor() 통과 필수.
"""

from . import config


# ─── 검열 ───────────────────────────────────────────

def censor(text):
    """권유성 표현을 사실 서술로 치환·제거.

    JSON의 `rise_reason` 같은 외부 텍스트가 카드에 들어가기 전 반드시 통과시킬 것.
    """
    if not text:
        return ''
    out = text
    for pattern, replacement in config.CENSORED_PATTERNS:
        out = out.replace(pattern, replacement)
    out = ' '.join(out.split())  # 연속 공백 정리
    return out.strip(' ·,.')


def has_forbidden(text):
    """검열 후 남은 권유성 단어 검증 (QA용)."""
    if not text:
        return []
    return [w for w in config.FORBIDDEN_WORDS if w in text]


# ─── 포맷 유틸 ──────────────────────────────────────

def fmt_won(amount):
    """원 → '1조 2,207억' / '4,376억' / '2,313만' 형식."""
    if amount is None:
        return '-'
    if amount < 100_000_000:
        man = amount // 10_000
        return f"{man:,}만"
    eok = amount // 100_000_000
    jo = eok // 10_000
    eok_rem = eok % 10_000
    if jo == 0:
        return f"{eok:,}억"
    if eok_rem == 0:
        return f"{jo}조"
    return f"{jo}조 {eok_rem:,}억"


def fmt_pct(rate, signed=True, decimals=2):
    """등락률 → '+29.95%' / '-1.20%' / '0.00%'."""
    if rate is None:
        return '-'
    if signed:
        if abs(rate) < 0.005:
            return f"0.{'0' * decimals}%"
        return f"{rate:+.{decimals}f}%"
    return f"{rate:.{decimals}f}%"


def is_limit_up(change_rate):
    return change_rate is not None and change_rate >= config.LIMIT_UP_THRESHOLD


# ─── 카드별 문구 합성 (사실 서술) ───────────────────

def theme_short_note(theme):
    """pre — 키워드 카드 한 줄.

    예: '13종목 · 평균 +18.3% · 대장 본느 상한가'
    """
    parts = [
        f"{theme['count']}종목",
        f"평균 +{theme['avg_rate']:.1f}%",
    ]
    leader = theme['leader']
    if is_limit_up(leader['change_rate']):
        parts.append(f"대장 {leader['name']} 상한가")
    elif leader['change_rate'] >= config.HEAVY_RATE_HIGHLIGHT:
        parts.append(f"대장 {leader['name']} {fmt_pct(leader['change_rate'])}")
    return ' · '.join(parts)


def market_mood(us_indices):
    """pre2 — 미국 시장 분위기 한 줄."""
    sp = us_indices.get('sp500', {}).get('pct', 0)
    nasdaq = us_indices.get('nasdaq', {}).get('pct', 0)
    dow = us_indices.get('dow', {}).get('pct', 0)

    ups = sum(1 for x in (sp, nasdaq, dow) if x > 0)
    downs = sum(1 for x in (sp, nasdaq, dow) if x < 0)

    if ups == 3:
        peak = max(sp, nasdaq, dow)
        leader_name = 'NASDAQ' if nasdaq == peak else ('S&P 500' if sp == peak else 'DOW')
        return f"3대 지수 동반 강세 · {leader_name} +{peak:.2f}% 주도"
    if downs == 3:
        trough = min(sp, nasdaq, dow)
        return f"3대 지수 동반 약세 · 최저 {trough:+.2f}%"
    if nasdaq > 0 and dow < 0:
        return "NASDAQ 강세 · DOW 약세 — 업종별 차별화"
    if dow > 0 and nasdaq < 0:
        return "DOW 강세 · NASDAQ 약세 — 가치주 우위"
    return "혼조 마감"


def ny_notes(us_indices, top_themes):
    """pre2 — 한국 시장 관점 노트 (사실 위주, 최대 N개)."""
    notes = []
    nasdaq = us_indices.get('nasdaq', {}).get('pct', 0)
    dow = us_indices.get('dow', {}).get('pct', 0)

    semi_themes = [t for t in top_themes if any(k in t['tag'] for k in ('반도체', 'AI', '디스플레이'))]
    if semi_themes:
        if nasdaq > 0:
            names = ' · '.join(t['tag'] for t in semi_themes[:2])
            counts = sum(t['count'] for t in semi_themes[:2])
            notes.append({
                'title': f"NASDAQ 강세 · 한국 {names} 동반",
                'tag': '연관',
                'desc': f"{counts}종목 동반 상승 · 평균 +{semi_themes[0]['avg_rate']:.1f}%",
            })
        elif nasdaq < 0:
            t = semi_themes[0]
            notes.append({
                'title': "NASDAQ 약세 · 한국 반도체 흐름 분리",
                'tag': '비교',
                'desc': f"한국 {t['tag']} {t['count']}종목 평균 +{t['avg_rate']:.1f}%",
            })

    if dow < 0:
        notes.append({
            'title': "DOW 약세 · 산업재 / 경기방어 압력",
            'tag': '참고',
            'desc': "한국 시장 별다른 동반 흐름 미관측",
        })

    if not notes:
        notes.append({
            'title': '미국 ↔ 한국 직접 연동성 미관측',
            'tag': '참고',
            'desc': '한국 시장 자체 테마 흐름 우위',
        })
    return notes[:config.NY_NOTES_TOP]


def issue_text(theme):
    """close2 — 핵심 이슈 한 줄."""
    parts = [
        f"{theme['count']}종목 동반 상승",
        f"평균 +{theme['avg_rate']:.1f}%",
    ]
    limit_ups = [s for s in theme['members'] if is_limit_up(s['change_rate'])]
    if limit_ups:
        names = ' · '.join(s['name'] for s in limit_ups[:3])
        parts.append(f"{names} 상한가")
    elif theme['leader']['change_rate'] >= config.HEAVY_RATE_HIGHLIGHT:
        leader = theme['leader']
        parts.append(f"{leader['name']} {fmt_pct(leader['change_rate'])}")
    return ' · '.join(parts)


def leader_why(stock, theme):
    """leader — 대장주 이유 한 줄.

    예: "시스템반도체 13종목 동반 상승 · 거래대금 1조 2,207억 · 테마 1위 · 상한가 마감"
    격조사("로/으로") 회피 위해 모든 절은 ' · '로만 연결.
    """
    parts = [f"{theme['tag']} {theme['count']}종목 동반 상승"]
    rank_in_theme = next(
        (i + 1 for i, s in enumerate(theme['members']) if s['ticker'] == stock['ticker']),
        None,
    )
    if rank_in_theme:
        parts.append(f"거래대금 {fmt_won(stock['trading_value'])}")
        parts.append(f"테마 {rank_in_theme}위")
    if is_limit_up(stock['change_rate']):
        parts.append("상한가 마감")
    return censor(' · '.join(parts))


def theme_story_why(theme):
    """leader2 — WHY TODAY 한 줄."""
    parts = [f"테마 {theme['count']}종목 평균 +{theme['avg_rate']:.1f}% 동반 상승"]
    if theme.get('total_value'):
        parts.append(f"거래대금 합계 {fmt_won(theme['total_value'])}")
    return censor(' · '.join(parts))


def theme_flow_text(theme):
    """leader2 — FLOW (자금 흐름) 한 줄."""
    members = theme['members']
    if not members:
        return ''
    total = sum(s['trading_value'] for s in members)
    top2 = members[:2]
    if total <= 0:
        return ''
    top_share = sum(s['trading_value'] for s in top2) / total
    if top_share >= config.TOP_SHARE_FOR_FLOW:
        names = ' · '.join(f"{s['name']} {fmt_won(s['trading_value'])}" for s in top2)
        return censor(f"{names} 거래대금 상위 2종목에 자금 집중")
    leader = members[0]
    return censor(
        f"테마 거래대금 {fmt_won(total)} 중 대장 {leader['name']} {fmt_won(leader['trading_value'])}"
    )
