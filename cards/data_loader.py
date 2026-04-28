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


def _date_full(yyyymmdd):
    """20260424 → '2026.04.24 (금)' (모든 카드 우상단 통일 포맷)."""
    dt = _yyyymmdd_to_dt(yyyymmdd)
    return f"{dt.year}.{dt.strftime('%m.%d')} ({config.WEEKDAY_KO[dt.weekday()]})"


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

def _latest_date_with_data():
    """dates.json 첫 항목 (가장 최근 거래일). 없으면 None."""
    dates_path = os.path.join(config.DATA_DIR, 'dates.json')
    if not os.path.exists(dates_path):
        return None
    try:
        with open(dates_path, encoding='utf-8') as f:
            dates = json.load(f)
        return dates[0] if dates else None
    except (json.JSONDecodeError, OSError):
        return None


def load_day(yyyymmdd, fallback=False):
    """target_date 파일 없으면 가장 최근 거래일 데이터로 fallback.

    PRE 시리즈가 오늘 (장 시작 전) 만들어질 때 사용 — 오늘 마감 데이터는
    아직 없으므로 가장 최근 마감(어제) 데이터를 사용하되, 카드 라벨은 오늘.

    Returns dict 에 'data_date' (실제 사용한 데이터 거래일) 추가.
    """
    path = os.path.join(config.DATA_DIR, f'{yyyymmdd}.json')
    data_date = yyyymmdd
    if not os.path.exists(path):
        if not fallback:
            raise FileNotFoundError(f'data file not found: {path}')
        latest = _latest_date_with_data()
        if not latest:
            raise FileNotFoundError(f'no data available (target={yyyymmdd}, no fallback)')
        path = os.path.join(config.DATA_DIR, f'{latest}.json')
        data_date = latest

    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    rankings = data.get('rankings', [])
    return {
        'date': yyyymmdd,                              # 라벨용 (인자 그대로)
        'date_kr': _date_kr_full(yyyymmdd),
        'date_kr_short': _date_kr_short(yyyymmdd),
        'date_full': _date_full(yyyymmdd),
        'weekday_ko': _weekday_ko(yyyymmdd),
        'weekday_en': _weekday_en(yyyymmdd),
        'data_date': data_date,                        # 실제 데이터 거래일 (참조용)
        'data_date_kr': _date_kr_full(data_date),
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

def _theme_prefix(tag):
    """테마 태그 첫 단어 — sector dedupe 용. '철강 중소형' → '철강', '반도체 장비' → '반도체'."""
    if not tag:
        return ''
    # 공백 또는 슬래시 분리 시도
    for sep in (' ', '/'):
        if sep in tag:
            return tag.split(sep)[0].strip()
    return tag


def _big_themes(day, target_count=None):
    """키워드 카드용 — 종목수 ≥ KEYWORD_MIN_THEME_MEMBERS 테마.

    - target_count 지정 시: 후보 부족하면 KEYWORD_FALLBACK_STEPS 단계로 임계 완화.
    - 같은 sector prefix (첫 단어) 가 여러 개면 평균등락률 1위만 채택해 다양성 확보.
      예: '철강 중소형' + '철강 주요종목' → 1개만.
    """
    themes_sorted = sorted(day['themes'], key=lambda t: -t['avg_rate'])
    primary = [t for t in themes_sorted if t['count'] >= config.KEYWORD_MIN_THEME_MEMBERS]

    candidates = list(primary)
    if target_count and len(candidates) < target_count:
        seen_tags = {t['tag'] for t in candidates}
        for threshold in config.KEYWORD_FALLBACK_STEPS:
            if len(candidates) >= target_count:
                break
            if threshold >= config.KEYWORD_MIN_THEME_MEMBERS:
                continue
            extra = [t for t in themes_sorted
                     if t['count'] >= threshold and t['tag'] not in seen_tags]
            for t in extra:
                if len(candidates) >= target_count:
                    break
                candidates.append(t)
                seen_tags.add(t['tag'])

    # Sector prefix dedupe — 첫 단어 같으면 평균등락률 1위만 (이미 정렬됨)
    seen_prefix = set()
    deduped = []
    for t in candidates:
        prefix = _theme_prefix(t['tag'])
        if prefix and len(prefix) <= 4 and prefix in seen_prefix:
            continue
        if prefix and len(prefix) <= 4:
            seen_prefix.add(prefix)
        deduped.append(t)

    # dedupe 후 target 미달이면 빠진 후보 보충 (다양성보다 슬롯 채움 우선)
    if target_count and len(deduped) < target_count:
        seen_tags = {t['tag'] for t in deduped}
        for t in candidates:
            if len(deduped) >= target_count:
                break
            if t['tag'] not in seen_tags:
                deduped.append(t)
                seen_tags.add(t['tag'])
    return deduped


def build_pre0(day, dawn_data):
    """카드 0 — 새벽 브리핑. 네이버 큐레이션 헤드라인 + 매크로 한 줄.

    Args:
        day: load_day() 결과 (날짜 라벨용)
        dawn_data: dawn_brief.fetch() 결과 — {'headlines': [...], 'macro': {...}}
                   None 또는 {} 면 카드 스킵.
    """
    if not dawn_data:
        return None
    headlines = dawn_data.get('headlines') or []
    macro = dawn_data.get('macro') or {}
    if not headlines and not macro:
        return None  # 둘 다 없으면 카드 의미 없음

    # 매크로 한 줄 포맷팅 — 데이터 있는 것만
    macro_items = []
    if macro.get('nasdaq'):
        m = macro['nasdaq']
        macro_items.append({'name': 'NASDAQ', 'value': f"{m['close']:,.0f}", 'pct': m['pct']})
    if macro.get('sp500'):
        m = macro['sp500']
        macro_items.append({'name': 'S&P 500', 'value': f"{m['close']:,.0f}", 'pct': m['pct']})
    if macro.get('vix'):
        m = macro['vix']
        macro_items.append({'name': 'VIX', 'value': f"{m['close']:,.1f}", 'pct': m['pct']})
    if macro.get('usdkrw'):
        m = macro['usdkrw']
        macro_items.append({'name': 'USD/KRW', 'value': f"{m['close']:,.0f}", 'pct': m['pct']})

    return {
        'series': 'pre',
        'date_full': day['date_full'],
        'label': '★ 새벽 브리핑',
        'title_top': '새벽 브리핑',
        'title_em': '간밤에 일어난 큰 일',
        'subtitle': '국장 흔들 만큼 큼지막한 일만',
        'headlines': [
            {
                'rank': f"{i + 1:02d}",
                'title': h['title'],
                'impact': h.get('impact') or '',
            }
            for i, h in enumerate(headlines[:config.TOP_DAWN_HEADLINES])
        ],
        'macro': macro_items,
        'source_note': '출처: 네이버 금융 마켓뉴스',
    }


def build_pre(day):
    """카드 1 — 키워드 4개. 한 카드 = 4 핵심 테마, 메타 최소.

    제목에 요일 prefix 제거 (우상단 날짜로 충분).
    """
    top = _big_themes(day, target_count=config.TOP_THEMES_PRE)[:config.TOP_THEMES_PRE]
    if not top:
        return None
    return {
        'series': 'pre',
        'date_full': day['date_full'],
        'label': '★ 주도 키워드',
        'title_top': '오늘 달궜던',
        'title_em': '키워드',
        'keywords': [
            {
                'rank': f"{i + 1:02d}",
                'tag': t['tag'],
                'pct_text': f"평균 +{t['avg_rate']:.1f}%",
                'hot': i < config.TOP_HOT_THEMES,
            }
            for i, t in enumerate(top)
        ],
    }


def build_pre2(day, us_indices, dawn_data=None):
    """카드 2 — 미국 마감. 3 지수 + 무드 + 마켓 무빙 헤드라인 N개."""
    if not us_indices:
        return None
    headlines = []
    if dawn_data:
        for h in (dawn_data.get('headlines') or [])[:config.PRE2_HEADLINES_TOP]:
            headlines.append({
                'rank': f"{len(headlines) + 1:02d}",
                'title': h['title'],
                'impact': h.get('impact') or '',
            })
    return {
        'series': 'pre',
        'date_full': day['date_full'],
        'label': '★ 뉴욕 마감',
        'title_top': '뉴욕',
        'title_em': '마감',
        'indices': [
            {'name': name, 'value': v['close'], 'change': v['change'], 'pct': v['pct'], 'up': v['pct'] > 0}
            for name, v in [
                ('S&P 500', us_indices.get('sp500', {})),
                ('NASDAQ',  us_indices.get('nasdaq', {})),
                ('DOW',     us_indices.get('dow', {})),
            ]
            if v
        ],
        'mood_text': ts.market_mood(us_indices),
        'headlines': headlines,
    }


def build_pre3(day):
    """카드 3 — 4테마 × 대장 1명만 (한 줄에 테마+종목+%).

    leader 카드와 일관성을 위해 leader 종목의 테마를 1번으로 강제 정렬 —
    pre3 1번 ≠ leader 카드 종목인 인지부조화 방지.
    """
    top = _big_themes(day, target_count=config.TOP_THEMES_PRE3)[:config.TOP_THEMES_PRE3]
    if not top:
        return None

    # leader 종목의 테마를 맨 앞으로 (일관성)
    leader_stock = _select_leader_stock(day['rankings'])
    if leader_stock:
        leader_tag = leader_stock.get('theme_tag')
        for i, t in enumerate(top):
            if t['tag'] == leader_tag and i > 0:
                top = [top[i]] + top[:i] + top[i + 1:]
                break

    return {
        'series': 'pre',
        'date_full': day['date_full'],
        'label': '★ 테마별 대장',
        'title_top': '오늘의',
        'title_em': '대장 종목',
        'themes': [
            {
                'rank': f"{i + 1:02d}",
                'tag': t['tag'],
                'hot': i < config.TOP_HOT_THEMES,
                'stocks': [
                    {'name': s['name'], 'ticker': s['ticker'], 'rate': s['change_rate']}
                    for s in t['members'][:config.TOP_STOCKS_PER_THEME]
                ],
            }
            for i, t in enumerate(top)
        ],
    }


def build_leader(day):
    """카드 4 — 대장주 1개. 종목명 + 등락률 초대형."""
    leader = _select_leader_stock(day['rankings'])
    if not leader:
        return None
    top_theme = _theme_group_for(leader, day['themes'])
    return {
        'series': 'leader',
        'date_full': day['date_full'],
        'label': '★ 대장주',
        'title_em': '대장주',
        'badge_theme': top_theme['tag'],
        'name': leader['name'],
        'code': leader['ticker'],
        'market': leader['market'],
        'rate': leader['change_rate'],
        'is_limit_up': ts.is_limit_up(leader['change_rate']),
        'why_text': ts.leader_why(leader, top_theme),
    }


def build_leader2(day):
    """카드 5 — 대장 테마 + 멤버 5명.

    대장주 테마 멤버 수가 LEADER2_RICH_THEME_MIN 미만이면 day 의 가장 풍부한
    테마(종목수 ≥ MIN, avg_rate 1위)로 대체 — 카드가 휑하게 나오는 것 방지.
    """
    leader = _select_leader_stock(day['rankings'])
    if not leader:
        return None
    top_theme = _theme_group_for(leader, day['themes'])
    if top_theme['count'] < config.LEADER2_RICH_THEME_MIN:
        rich = [t for t in day['themes'] if t['count'] >= config.LEADER2_RICH_THEME_MIN]
        if rich:
            # 종목수 우선, 동일하면 평균등락률 우선
            top_theme = max(rich, key=lambda t: (t['count'], t['avg_rate']))
    if top_theme['count'] < config.MIN_THEME_MEMBERS:
        return None
    members = top_theme['members'][:config.LEADER_MEMBERS_TOP]
    return {
        'series': 'leader',
        'date_full': day['date_full'],
        'label': '★ 대장 테마',
        'title_top': '오늘의',
        'title_em': '대장 테마',
        'theme_name': f"#{top_theme['tag']}",
        'theme_stat_html': f"<strong>+{top_theme['avg_rate']:.1f}%</strong> · {top_theme['count']}종목",
        'members': [
            {
                'rank': i + 1,
                'name': m['name'],
                'rate': m['change_rate'],
                'is_leader': i == 0,
            }
            for i, m in enumerate(members)
        ],
    }


def build_close(day, kr_indices, summary):
    """카드 6 — 마감 시황. 지수 + 통계 + 대장 테마.

    kr_indices 가 None 일 때 휑함 방지 — summary.json 기반 fallback 통계 사용.
    """
    big = _big_themes(day)
    if not big:
        return None
    top_theme = big[0]
    # 강세(LEADER_MIN_RATE) 종목 중 거래대금 1위 — leader 카드와 일치시켜 인지부조화 방지
    top_stock_by_volume = _select_leader_stock(day['rankings'])

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

    # summary.json 기반 시장 통계 (kr_indices 실패해도 카드가 풍성)
    market_stats = []
    if summary:
        if summary.get('limitUp'):
            market_stats.append({'label': '상한가', 'value': f"{summary['limitUp']}종목"})
        if summary.get('avgRate'):
            market_stats.append({'label': 'TOP 100 평균', 'value': f"+{summary['avgRate']:.1f}%"})
    if top_stock_by_volume:
        market_stats.append({
            'label': '오늘의 대장주',
            'value': f"{top_stock_by_volume['name']} {ts.fmt_won(top_stock_by_volume['trading_value'])}",
        })

    return {
        'series': 'close',
        'date_full': day['date_full'],
        'label': '★ 마감 시황',
        'title_top': '장 마감',
        'title_em': '한 줄 요약',
        'indices': indices,
        'market_stats': market_stats,
        'leader_label': '대장 테마',
        'leader_name': f"#{top_theme['tag']}",
        'leader_rate': top_theme['avg_rate'],
    }


def build_close2(day):
    """카드 7 — 핵심 이슈 3장만 (큰 글씨)."""
    big = _big_themes(day, target_count=config.TOP_ISSUES_CLOSE2)
    if not big:
        return None
    issue_themes = big[:config.TOP_ISSUES_CLOSE2]
    issues = [
        {
            'num': f"{i + 1:02d}",
            'title': f"#{t['tag']} +{t['avg_rate']:.1f}%",
            'hot': i == 0,
            'desc': ts.issue_text(t),
        }
        for i, t in enumerate(issue_themes)
    ]
    return {
        'series': 'close',
        'date_full': day['date_full'],
        'label': '★ 핵심 이슈',
        'title_top': '오늘의',
        'title_em': '핵심 이슈',
        'issues': issues,
    }


# ─── 진입점 ─────────────────────────────────────────

def build_all(yyyymmdd, us_indices=None, kr_indices=None, dawn_data=None, fallback=False):
    """카드 8장 입력 dict 한 번에 빌드.

    Args:
        yyyymmdd: 거래일 (예: '20260424')
        us_indices: {'sp500': {...}, 'nasdaq': {...}, 'dow': {...}} 또는 None
        kr_indices: {'kospi': {...}, 'kosdaq': {...}} 또는 None
        dawn_data: {'headlines': [...], 'macro': {...}} 또는 None — pre0(새벽 브리핑)
        fallback: True 면 오늘 데이터 없을 때 가장 최근 거래일 데이터 사용
                  (PRE 시리즈가 장전 08:05 에 만들어질 때)
    """
    day = load_day(yyyymmdd, fallback=fallback)
    summary = load_summary(day['data_date']) or load_summary(yyyymmdd)
    return {
        'pre0':    build_pre0(day, dawn_data),
        'pre':     build_pre(day),
        'pre2':    build_pre2(day, us_indices, dawn_data),
        'pre3':    build_pre3(day),
        'leader':  build_leader(day),
        'leader2': build_leader2(day),
        'close':   build_close(day, kr_indices, summary),
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
