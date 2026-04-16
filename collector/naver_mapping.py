"""네이버 증권 테마/업종 API 매핑 빌드

네이버 공식 테마(263개)·업종(79개) API에서 종목 소속 정보를 가져와
ticker → [themes], ticker → industry 역매핑을 구축한다.
매일 수집 전 1회 빌드하고 naver_mapping.json에 캐시.
"""
import json
import os
import time
import logging
from datetime import datetime

import requests

from config import COLLECTOR_DIR

logger = logging.getLogger(__name__)

MAPPING_PATH = os.path.join(COLLECTOR_DIR, 'naver_mapping.json')
BASE_URL = 'https://m.stock.naver.com/api/stocks'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
PAGE_SIZE = 100
REQUEST_DELAY = 0.08  # 80ms between API calls


def _get_json(url, params=None):
    """GET 요청 → JSON 파싱. 실패 시 None."""
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"API 실패: {url} — {e}")
        return None


def _fetch_all_groups(group_type):
    """테마 or 업종 전체 목록을 페이지네이션으로 가져온다.
    group_type: 'theme' | 'industry'
    Returns: [{no, name, totalCount, changeRate, ...}, ...]
    """
    all_groups = []
    page = 1
    while True:
        data = _get_json(f'{BASE_URL}/{group_type}', {'page': page, 'pageSize': PAGE_SIZE})
        if not data or 'groups' not in data:
            break
        all_groups.extend(data['groups'])
        if len(all_groups) >= data.get('totalCount', 0):
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    return all_groups


def _fetch_group_stocks(group_type, group_no):
    """특정 테마/업종의 소속 종목 ticker 리스트를 가져온다.
    Returns: [ticker, ...]
    """
    tickers = []
    page = 1
    while True:
        data = _get_json(
            f'{BASE_URL}/{group_type}/{group_no}',
            {'page': page, 'pageSize': PAGE_SIZE},
        )
        if not data or 'stocks' not in data:
            break
        for s in data['stocks']:
            tickers.append(s['itemCode'])
        if len(tickers) >= data.get('totalCount', 0):
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    return tickers


def build_mapping():
    """테마/업종 전체 매핑을 빌드하고 저장한다.

    Returns:
        dict: {
            'built_date': 'YYYYMMDD',
            'themes': {ticker: [{no, name}, ...]},        # 종목→테마 역매핑
            'industries': {ticker: {no, name}},            # 종목→업종
            'theme_list': [{no, name, totalCount, changeRate}, ...],  # 테마 목록 (당일 등락률 포함)
            'industry_list': [{no, name, totalCount, changeRate}, ...],
        }
    """
    logger.info("=== 네이버 매핑 빌드 시작 ===")

    # ── 1. 테마 목록 ──
    theme_groups = _fetch_all_groups('theme')
    logger.info(f"  테마 {len(theme_groups)}개 로드")

    # ── 2. 테마별 종목 → 역매핑 ──
    theme_map = {}  # ticker → [{no, name}, ...]
    for i, tg in enumerate(theme_groups):
        tickers = _fetch_group_stocks('theme', tg['no'])
        for t in tickers:
            if t not in theme_map:
                theme_map[t] = []
            theme_map[t].append({'no': tg['no'], 'name': tg['name']})
        if (i + 1) % 50 == 0:
            logger.info(f"  테마 진행: {i + 1}/{len(theme_groups)}")
        time.sleep(REQUEST_DELAY)
    logger.info(f"  테마 매핑 완료: {len(theme_map)}개 종목")

    # ── 3. 업종 목록 ──
    industry_groups = _fetch_all_groups('industry')
    logger.info(f"  업종 {len(industry_groups)}개 로드")

    # ── 4. 업종별 종목 → 역매핑 ──
    industry_map = {}  # ticker → {no, name}
    for i, ig in enumerate(industry_groups):
        tickers = _fetch_group_stocks('industry', ig['no'])
        for t in tickers:
            industry_map[t] = {'no': ig['no'], 'name': ig['name']}
        if (i + 1) % 20 == 0:
            logger.info(f"  업종 진행: {i + 1}/{len(industry_groups)}")
        time.sleep(REQUEST_DELAY)
    logger.info(f"  업종 매핑 완료: {len(industry_map)}개 종목")

    # ── 5. 저장 ──
    mapping = {
        'built_date': datetime.now().strftime('%Y%m%d'),
        'themes': theme_map,
        'industries': industry_map,
        'theme_list': [
            {'no': g['no'], 'name': g['name'], 'totalCount': g['totalCount'],
             'changeRate': g.get('changeRate', '0')}
            for g in theme_groups
        ],
        'industry_list': [
            {'no': g['no'], 'name': g['name'], 'totalCount': g['totalCount'],
             'changeRate': g.get('changeRate', '0')}
            for g in industry_groups
        ],
    }

    with open(MAPPING_PATH, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    logger.info(f"=== 매핑 저장 완료: {MAPPING_PATH} ===")
    return mapping


def load_mapping(date_str=None):
    """캐시된 매핑을 로드한다. 당일 빌드가 없으면 새로 빌드.

    Args:
        date_str: 'YYYYMMDD' — 이 날짜와 built_date가 같으면 캐시 사용

    Returns:
        dict: 매핑 데이터
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')

    if os.path.exists(MAPPING_PATH):
        try:
            with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            if mapping.get('built_date') == date_str:
                logger.info(f"매핑 캐시 사용 (built: {date_str})")
                return mapping
            logger.info(f"매핑 캐시 만료 (built: {mapping.get('built_date')}, need: {date_str})")
        except Exception as e:
            logger.warning(f"매핑 캐시 로드 실패: {e}")

    return build_mapping()


def get_theme_rates():
    """당일 테마별 등락률을 API에서 가져온다 (실시간).
    Returns: {theme_no: float(changeRate)}
    """
    theme_groups = _fetch_all_groups('theme')
    rates = {}
    for tg in theme_groups:
        try:
            rates[tg['no']] = float(tg.get('changeRate', '0'))
        except (ValueError, TypeError):
            rates[tg['no']] = 0.0
    return rates


def resolve_themes(ticker, mapping, theme_rates=None):
    """종목의 테마를 매핑에서 조회하고 당일 등락률 순으로 정렬.

    Args:
        ticker: 종목코드
        mapping: load_mapping() 결과
        theme_rates: {theme_no: changeRate} — 없으면 mapping 내 theme_list 사용

    Returns:
        list: [{'no': int, 'name': str, 'changeRate': float}, ...] 등락률 내림차순 (최대 전체)
    """
    themes = mapping.get('themes', {}).get(ticker, [])
    if not themes:
        return []

    # 등락률 매핑
    if theme_rates is None:
        theme_rates = {}
        for tl in mapping.get('theme_list', []):
            try:
                theme_rates[tl['no']] = float(tl.get('changeRate', '0'))
            except (ValueError, TypeError):
                theme_rates[tl['no']] = 0.0

    result = []
    for th in themes:
        rate = theme_rates.get(th['no'], 0.0)
        result.append({'no': th['no'], 'name': th['name'], 'changeRate': rate})

    # 당일 등락률 높은 순 정렬
    result.sort(key=lambda x: x['changeRate'], reverse=True)
    return result


def resolve_industry(ticker, mapping):
    """종목의 업종을 매핑에서 조회.
    Returns: str (업종명) or ''
    """
    ind = mapping.get('industries', {}).get(ticker, {})
    return ind.get('name', '')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    mapping = build_mapping()
    print(f"\n테마 매핑: {len(mapping['themes'])}개 종목")
    print(f"업종 매핑: {len(mapping['industries'])}개 종목")
    print(f"테마 목록: {len(mapping['theme_list'])}개")
    print(f"업종 목록: {len(mapping['industry_list'])}개")
