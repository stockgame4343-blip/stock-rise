"""public/data/*.json + 외부 지수 → 카드 7장 입력 dict.

각 빌더는 1장 카드의 dict를 반환. `build_all()`이 dict 7장 묶음을 반환.
입력 데이터가 부족하면 None 반환 (해당 카드 스킵).
"""

import json
import os
from collections import defaultdict
from datetime import datetime

from . import config
from . import text_synth as ts


# ─── 날짜 ────────────────────────────────────────────

def _yyyymmdd_to_dt(yyyymmdd):
    return datetime.strptime(yyyymmdd, '%Y%m%d')


def _date_kr_full(yyyymmdd):
    """20260424 → '04.24 (금)'."""
    dt = _yyyymmdd_to_dt(yyyymmdd)
    return f"{dt.strftime('%m.%d')} ({config.WEEKDAY_KO[dt.weekday()]})"


def _date_kr_short(yyyymmdd):
    """20260424 → '4월 24일'."""
    dt = _yyyymmdd_to_dt(yyyymmdd)
    return f"{dt.month}월 {dt.day}일"


def _weekday_ko(yyyymmdd):
    return config.WEEKDAY_KO[_yyyymmdd_to_dt(yyyymmdd).weekday()]


def _weekday_en(yyyymmdd):
    return config.WEEKDAY_EN[_yyyymmdd_to_dt(yyyymmdd).weekday()]


# ─── 점수 정규화 ────────────────────────────────────

def _normalize_scores(detail):
    """score_detail {tp,tl,ti} → {leadership/momentum/theme_power} 100점 정규화.

    collector/scorer.py: tp(0~35) + tl(0~45) + ti(0~20) = 100.
    """
    tp = detail.get('tp', 0) or 0
    tl = detail.get('tl', 0) or 0
    ti = detail.get('ti', 0) or 0
    cap = config.SCORE_NORMALIZED_MAX
    return {
        'leadership':  min(round(tl / config.TL_MAX * cap), cap),
        'momentum':    min(round(ti / config.TI_MAX * cap), cap),
        'theme_power': min(round(tp / config.TP_MAX * cap), cap),
    }


# ─── 그룹화 ─────────────────────────────────────────

def _group_by_theme(rankings):
    """`theme_tag` 단일 키 그룹화. 단일 종목 / 빈 태그 제외."""
    by_tag = defaultdict(list)
    for s in rankings:
        tag = s.get('theme_tag')
        if not tag or tag == '기타':
            continue
        by_tag[tag].append(s)

    groups = []
    for tag, members in by_tag.items():
        if len(members) < config.MIN_THEME_MEMBERS:
            continue
        members_sorted = sorted(members, key=lambda x: -x.get('trading_value', 0))
        groups.append({
            'tag': tag,
            'members': members_sorted,
            'count': len(members),
            'avg_rate': sum(s['change_rate'] for s in members) / len(members),
            'leader': members_sorted[0],
            'total_value': sum(s.get('trading_value', 0) for s in members),
        })
    return sorted(groups, key=lambda g: -g['avg_rate'])


def _select_leader_stock(rankings):
    """대장주 1개 선정.

    룰: change_rate ≥ LEADER_MIN_RATE 인 종목 중 거래대금 1위.
    강세 종목이 없으면 거래대금 단순 1위.
    """
    candidates = [s for s in rankings if s.get('change_rate', 0) >= config.LEADER_MIN_RATE]
    pool = candidates if candidates else rankings
    if not pool:
        return None
    return max(pool, key=lambda s: s.get('trading_value', 0))


def _theme_group_for(stock, themes):
    """대장주 종목의 theme_tag와 일치하는 테마 그룹.

    그룹화 임계 미달이면 단일 종목 가짜 그룹.
    """
    tag = stock.get('theme_tag') or '기타'
    for t in themes:
        if t['tag'] == tag:
            return t
    return {
        'tag': tag,
        'count': 1,
        'avg_rate': stock.get('change_rate', 0),
        'leader': stock,
        'members': [stock],
        'total_value': stock.get('trading_value', 0),
    }


def _group_by_sector(rankings):
    by_sec = defaultdict(list)
    for s in rankings:
        sec = s.get('sector')
        if not sec or sec == '기타':
            continue
        by_sec[sec].append(s)

    groups = []
    for sec, members in by_sec.items():
        if len(members) < config.MIN_SECTOR_MEMBERS:
            continue
        members_sorted = sorted(members, key=lambda x: -x['change_rate'])
        groups.append({
            'name': sec,
            'members': members_sorted,
            'count': len(members),
            'avg_rate': sum(s['change_rate'] for s in members) / len(members),
        })
    return sorted(groups, key=lambda g: -g['avg_rate'])


# ─── 로드 ───────────────────────────────────────────

def load_day(yyyymmdd):
    path = os.path.join(config.DATA_DIR, f'{yyyymmdd}.json')
    if not os.path.exists(path):
        raise FileNotFoundError(f'data file not found: {path}')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    rankings = data.get('rankings', [])
    return {
        'date': yyyymmdd,
        'date_kr': _date_kr_full(yyyymmdd),
        'date_kr_short': _date_kr_short(yyyymmdd),
        'weekday_ko': _weekday_ko(yyyymmdd),
        'weekday_en': _weekday_en(yyyymmdd),
        'rankings': rankings,
        'themes': _group_by_theme(rankings),
        'sectors': _group_by_sector(rankings),
        'is_final': data.get('is_final', False),
        'mode': data.get('mode', 'unknown'),
    }


def load_summary(yyyymmdd):
    path = os.path.join(config.DATA_DIR, 'summary.json')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        for entry in json.load(f):
            if entry.get('date') == yyyymmdd:
                return entry
    return None


# ─── 카드별 빌더 ────────────────────────────────────

def _big_themes(day):
    """키워드 카드용 — 종목수 ≥ KEYWORD_MIN_THEME_MEMBERS 테마만."""
    return [t for t in day['themes'] if t['count'] >= config.KEYWORD_MIN_THEME_MEMBERS]


def build_pre(day):
    """카드 1 — 키워드 4개 (테마). 하단 중복 strip 제거."""
    top = _big_themes(day)[:config.TOP_THEMES_PRE]
    if not top:
        return None
    return {
        'series': 'pre',
        'date_kr': day['date_kr'],
        'date_kr_short': day['date_kr_short'],
        'weekday_en': day['weekday_en'],
        'weekday_ko': day['weekday_ko'],
        'eyebrow': f"★ {day['weekday_en']} KEYWORDS",
        'time_text': f"{day['date_kr']} 마감",
        'title_top': f"{day['weekday_ko']}요일 달궜던",
        'title_em': '키워드',
        'sub': f"{day['date_kr_short']}, 가장 강했던 {len(top)}가지 테마",
        'keywords': [
            {
                'rank': f"{i + 1:02d}",
                'tag': t['tag'],
                'note': ts.theme_short_note(t),
                'hot': i < config.TOP_HOT_THEMES,
            }
            for i, t in enumerate(top)
        ],
    }


def build_pre2(day, us_indices):
    """카드 2 — 미국 마감. us_indices가 없으면 None."""
    if not us_indices:
        return None
    return {
        'series': 'pre',
        'date_kr': day['date_kr'],
        'time_text': f"NY · {day['date_kr']} 마감",
        'label': 'US MARKET',
        'title_top': '뉴욕',
        'title_em': '마감과',
        'title_bot': '오늘의 한국',
        'sub': '미국 3대 지수 · 한국 시장 관점',
        'indices': [
            {'name': name, 'value': v['close'], 'change': v['change'], 'pct': v['pct'], 'up': v['pct'] > 0}
            for name, v in [
                ('S&P 500', us_indices.get('sp500', {})),
                ('NASDAQ',  us_indices.get('nasdaq', {})),
                ('DOW',     us_indices.get('dow', {})),
            ]
            if v
        ],
        'mood_label': 'MARKET MOOD',
        'mood_text': ts.market_mood(us_indices),
        'notes_label': '한국 시장 관점',
        'notes': ts.ny_notes(us_indices, day['themes']),
    }


def build_pre3(day):
    """카드 3 — 4테마별 거래대금 상위 종목."""
    top = _big_themes(day)[:config.TOP_THEMES_PRE3]
    if not top:
        return None
    return {
        'series': 'pre',
        'date_kr': day['date_kr'],
        'time_text': f"{day['date_kr']} 마감",
        'label': '★ 주도 종목',
        'title_top': f"{day['weekday_ko']}요일",
        'title_em': '이 종목',
        'title_bot': '이 움직였다',
        'sub': f"{len(top)}개 테마별 거래대금 상위 종목",
        'themes': [
            {
                'rank': f"{i + 1:02d}",
                'tag': t['tag'],
                'count': t['count'],
                'avg_rate': t['avg_rate'],
                'hot': i < config.TOP_HOT_THEMES,
                'tag_label': '대장 테마' if i == 0 else ('동반 강세' if t['avg_rate'] >= config.STRONG_THEME_AVG else '관찰'),
                'stocks': [
                    {
                        'name': s['name'],
                        'ticker': s['ticker'],
                        'rate': s['change_rate'],
                        'is_leader': j == 0,
                    }
                    for j, s in enumerate(t['members'][:config.TOP_STOCKS_PER_THEME])
                ],
            }
            for i, t in enumerate(top)
        ],
        'note': '★ = 각 테마 거래대금 1위 (사후 집계)',
    }


def build_leader(day):
    """카드 4 — 대장주 1개.

    선정: 강세(>=LEADER_MIN_RATE) 종목 중 거래대금 1위. 사용자 직관과 일치
    (e.g. 04.24 → 시스템반도체 고영 1.2조).
    """
    leader = _select_leader_stock(day['rankings'])
    if not leader:
        return None
    top_theme = _theme_group_for(leader, day['themes'])
    return {
        'series': 'leader',
        'date_kr': day['date_kr'],
        'weekday_ko': day['weekday_ko'],
        'time_text': f"{day['date_kr']} 마감",
        'eyebrow': f"★ {day['weekday_en']} LEADER",
        'title_top': f"{day['weekday_ko']}요일의",
        'title_em': '대장주',
        'sub': '가장 강했던 테마의 가장 강했던 종목',
        'badge': f"★ LEADER · {top_theme['tag']}",
        'name': leader['name'],
        'code': leader['ticker'],
        'market': leader['market'],
        'rate': leader['change_rate'],
        'is_limit_up': ts.is_limit_up(leader['change_rate']),
        'trading_value_text': ts.fmt_won(leader.get('trading_value', 0)),
        'market_cap_text': ts.fmt_won(leader.get('market_cap', 0)),
        'scores': _normalize_scores(leader.get('score_detail', {})),
        'why_text': ts.leader_why(leader, top_theme),
    }


def build_leader2(day):
    """카드 5 — 대장 테마 멤버 + 자금 흐름.

    `build_leader`가 선정한 대장주의 theme_tag 그룹을 사용 (두 카드 일관성).
    멤버 부족하면 None (스토리 카드 의미 없음).
    """
    leader = _select_leader_stock(day['rankings'])
    if not leader:
        return None
    top_theme = _theme_group_for(leader, day['themes'])
    if top_theme['count'] < config.MIN_THEME_MEMBERS:
        return None
    members = top_theme['members'][:config.LEADER_MEMBERS_TOP]
    return {
        'series': 'leader',
        'date_kr': day['date_kr'],
        'time_text': f"{day['date_kr']} 마감",
        'label': f"★ {top_theme['tag']} 스토리",
        'title_top': f"{day['weekday_ko']}요일",
        'title_em': '이 테마',
        'title_bot': '의 흐름',
        'sub': f"대장 테마 배경과 {top_theme['count']}종목 멤버 요약",
        'story_label': 'WHY TODAY',
        'story_text': ts.theme_story_why(top_theme),
        'members_label': f"MEMBERS TOP {len(members)}",
        'members_summary': f"전체 {top_theme['count']}종목 · 평균 +{top_theme['avg_rate']:.1f}%",
        'members': [
            {
                'rank': i + 1,
                'name': m['name'],
                'code': m['ticker'],
                'rate': m['change_rate'],
                'is_limit_up': ts.is_limit_up(m['change_rate']),
                'is_leader': i == 0,
            }
            for i, m in enumerate(members)
        ],
        'flow_label': 'FLOW',
        'flow_text': ts.theme_flow_text(top_theme),
    }


def build_close(day, kr_indices):
    """카드 6 — 마감 한 줄 요약.

    대장 테마는 큰 테마(>=KEYWORD_MIN_THEME_MEMBERS) 우선,
    TOP 거래대금은 거래대금 정렬 1위 (등락률 정렬과 다름).
    """
    big = _big_themes(day)
    if not big:
        return None
    top_theme = big[0]
    top_stock_by_volume = (
        max(day['rankings'], key=lambda s: s.get('trading_value', 0))
        if day['rankings'] else None
    )
    limit_ups = sum(1 for s in day['rankings'] if ts.is_limit_up(s['change_rate']))
    strong_themes = sum(1 for t in day['themes'] if t['avg_rate'] >= config.STRONG_THEME_AVG)

    indices = []
    if kr_indices:
        for key, name in [('kospi', 'KOSPI'), ('kosdaq', 'KOSDAQ')]:
            idx = kr_indices.get(key)
            if not idx:
                continue
            indices.append({
                'name': name,
                'value': idx['close'],
                'change': idx['change'],
                'pct': idx['pct'],
                'up': idx['pct'] > 0.05,
                'flat': abs(idx['pct']) <= 0.05,
            })

    return {
        'series': 'close',
        'date_kr': day['date_kr'],
        'time_text': f"{day['date_kr']} 마감",
        'eyebrow': '★ MARKET CLOSE',
        'title_top': '장 마감,',
        'title_em': '한 줄',
        'title_bot': '요약',
        'sub': f"{top_theme['tag']} 주도 · 거래상위 자금 집중",
        'indices': indices,
        'stats': [
            {'label': '상한가 종목', 'value': f"{limit_ups}개" if limit_ups else '없음', 'kind': 'up'},
            {'label': '강세 테마',   'value': f"{strong_themes}개", 'kind': 'neutral'},
            {'label': 'TOP 거래대금', 'value': f"{top_stock_by_volume['name']} {ts.fmt_won(top_stock_by_volume['trading_value'])}" if top_stock_by_volume else '-', 'kind': 'up'},
        ],
        'leader_label': f"★ {day['weekday_ko']}요일 대장 테마",
        'leader_name': f"{top_theme['tag']} ({top_theme['count']}종목)",
        'leader_rate': top_theme['avg_rate'],
    }


def build_close2(day):
    """카드 7 — 핵심 이슈 + 섹터 리뷰.

    이슈는 큰 테마 우선 (작은 테마/단독 종목 제외).
    """
    big = _big_themes(day)
    if not big:
        return None

    issue_themes = big[:config.TOP_ISSUES_CLOSE2]
    issue_tag_labels = ['최대 이슈', '모멘텀', '추가 이슈']
    issues = [
        {
            'num': f"{i + 1:02d}",
            'title': f"{t['tag']} 동반 상승",
            'tag': issue_tag_labels[i] if i < len(issue_tag_labels) else '관찰',
            'hot': i == 0,
            'desc': ts.issue_text(t),
        }
        for i, t in enumerate(issue_themes)
    ]

    sectors = []
    for s in day['sectors'][:config.TOP_SECTORS_CLOSE2]:
        intensity = 'up-strong' if s['avg_rate'] >= config.SECTOR_INTENSITY_STRONG else 'up-mild'
        top3 = s['members'][:3]
        stocks_html = ' · '.join(
            f"<strong>{m['name']}</strong> {ts.fmt_pct(m['change_rate'])}"
            for m in top3
        )
        sectors.append({
            'name': s['name'],
            'rate': s['avg_rate'],
            'intensity': intensity,
            'stocks_html': stocks_html,
        })

    return {
        'series': 'close',
        'date_kr': day['date_kr'],
        'time_text': f"{day['date_kr']} 마감",
        'label': "★ TODAY'S ISSUES",
        'title_top': f"{day['weekday_ko']}요일,",
        'title_em': '무슨 일',
        'title_bot': '이 있었나',
        'sub': '핵심 이슈 · 섹터 리뷰',
        'issues': issues,
        'sectors_label': '▣ 섹터 리뷰',
        'sectors': sectors,
    }


# ─── 진입점 ─────────────────────────────────────────

def build_all(yyyymmdd, us_indices=None, kr_indices=None):
    """카드 7장 입력 dict 한 번에 빌드.

    Args:
        yyyymmdd: 거래일 (예: '20260424')
        us_indices: {'sp500': {'close','change','pct'}, 'nasdaq': {...}, 'dow': {...}} 또는 None
        kr_indices: {'kospi': {'close','change','pct'}, 'kosdaq': {...}} 또는 None

    Returns:
        dict: {'pre','pre2','pre3','leader','leader2','close','close2','_meta'}
    """
    day = load_day(yyyymmdd)
    return {
        'pre':     build_pre(day),
        'pre2':    build_pre2(day, us_indices),
        'pre3':    build_pre3(day),
        'leader':  build_leader(day),
        'leader2': build_leader2(day),
        'close':   build_close(day, kr_indices),
        'close2':  build_close2(day),
        '_meta': {
            'date': yyyymmdd,
            'date_kr': day['date_kr'],
            'is_final': day['is_final'],
            'mode': day['mode'],
            'theme_count': len(day['themes']),
            'sector_count': len(day['sectors']),
        },
    }
