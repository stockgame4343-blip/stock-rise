"""JSON 파일 기반 데이터 저장/조회 (SQLite 대체)"""
import json
import os
import logging
from datetime import datetime, timedelta

from config import DATA_DIR, DATA_RETENTION_DAYS, SECTOR_CACHE_PATH

logger = logging.getLogger(__name__)


def _ensure_data_dir():
    """data/ 디렉토리 존재 확인"""
    os.makedirs(DATA_DIR, exist_ok=True)


def save_daily_data(date_str, data):
    """날짜별 JSON 파일 저장

    Args:
        date_str: 'YYYYMMDD' 형식
        data: dict (date, collected_at, count, rankings)
    """
    _ensure_data_dir()
    path = os.path.join(DATA_DIR, f'{date_str}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"  저장 완료: {path}")


def update_dates_index():
    """data/dates.json 갱신 — data/ 내 YYYYMMDD.json 목록을 최신순 정렬"""
    _ensure_data_dir()
    dates = []
    for fname in os.listdir(DATA_DIR):
        if fname.endswith('.json') and fname != 'dates.json' and len(fname) == 13:
            dates.append(fname.replace('.json', ''))

    dates.sort(reverse=True)

    path = os.path.join(DATA_DIR, 'dates.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(dates, f, ensure_ascii=False)
    logger.info(f"  dates.json 갱신: {len(dates)}개 날짜")


def cleanup_old_data():
    """보관 기간(90일) 초과 JSON 삭제"""
    cutoff = (datetime.now() - timedelta(days=DATA_RETENTION_DAYS)).strftime('%Y%m%d')
    removed = 0

    for fname in os.listdir(DATA_DIR):
        if fname.endswith('.json') and fname != 'dates.json' and len(fname) == 13:
            date_part = fname.replace('.json', '')
            if date_part < cutoff:
                os.remove(os.path.join(DATA_DIR, fname))
                removed += 1

    if removed:
        logger.info(f"  오래된 데이터 {removed}개 삭제")
        update_dates_index()


def load_sector_cache():
    """섹터 캐시 로드 (ticker → sector 매핑)"""
    if not os.path.exists(SECTOR_CACHE_PATH):
        return {}
    try:
        with open(SECTOR_CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_sector_cache(sector_map):
    """섹터 캐시 저장 (전체 덮어쓰기)"""
    with open(SECTOR_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(sector_map, f, ensure_ascii=False, indent=2)
