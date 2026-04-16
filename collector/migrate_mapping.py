"""기존 일별 데이터에 네이버 매핑 적용 (테마/업종 업데이트 + 점수 재계산)

사용법: python migrate_mapping.py
"""
import json
import sys
import logging

sys.stdout.reconfigure(encoding='utf-8')

from config import LEADER_HISTORY_DAYS
from json_store import load_daily_data, save_daily_data, update_summary_index
from naver_mapping import load_mapping, resolve_themes, resolve_industry, build_mapping
from scorer import calculate_daejang_score

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def migrate_day(date_str, mapping, theme_rates, history_data=None):
    """하루치 데이터를 네이버 매핑으로 업데이트."""
    data = load_daily_data(date_str)
    if not data:
        logger.warning(f"  {date_str}: 데이터 없음, 스킵")
        return False

    rankings = data.get('rankings', [])
    if not rankings:
        return False

    updated = 0
    no_tag_before = 0
    no_tag_after = 0

    # Pass 1: 테마/업종 매핑 적용
    for r in rankings:
        t = r['ticker']
        old_tag = r.get('theme_tag', '')
        old_sector = r.get('sector', '')

        if not old_tag:
            no_tag_before += 1

        # 네이버 테마 매핑
        resolved = resolve_themes(t, mapping, theme_rates)
        if resolved:
            theme_tags = [th['name'] for th in resolved[:2]]
            r['theme_tag'] = theme_tags[0]
            r['theme_tags'] = theme_tags
            r['theme_no'] = resolved[0].get('no')
            updated += 1
        else:
            # 매핑에 없으면 기존 태그 유지
            r['theme_tags'] = [old_tag] if old_tag else []
            r['theme_no'] = None

        if not r.get('theme_tag'):
            no_tag_after += 1

        # 네이버 업종 매핑
        ind = resolve_industry(t, mapping)
        if ind:
            r['sector'] = ind

    # Pass 2: 테마 그룹 재빌드 + 점수 재계산
    theme_groups = {}
    for r in rankings:
        tag = r.get('theme_tag', '')
        if tag:
            theme_groups.setdefault(tag, []).append(r)

    for r in rankings:
        tag = r.get('theme_tag', '')
        group = theme_groups.get(tag, [])
        td = {
            'today_value': r.get('trading_value', 0),
            'avg_5day': r.get('avg_5day', 0),
            'inst_net': r.get('inst_net', 0),
            'foreign_net': r.get('foreign_net', 0),
            'is_limit_up': r.get('change_rate', 0) >= 29.5,
        }
        score_result = calculate_daejang_score(
            stock=r, theme_group=group, td=td, history_data=history_data,
        )
        r['score'] = score_result['total']
        r['score_detail'] = score_result['detail']

    data['version'] = 4
    save_daily_data(date_str, data)

    logger.info(
        f"  {date_str}: 매핑 {updated}개 적용, "
        f"태그없음 {no_tag_before}→{no_tag_after}, "
        f"테마그룹 {len(theme_groups)}개"
    )
    return True


def main():
    logger.info("=== 기존 데이터 마이그레이션 시작 ===")

    # 매핑 빌드 (없으면 새로 생성)
    mapping = build_mapping()

    # 테마 등락률 (매핑 내 theme_list에서 추출)
    theme_rates = {}
    for tl in mapping.get('theme_list', []):
        try:
            theme_rates[tl['no']] = float(tl.get('changeRate', '0'))
        except (ValueError, TypeError):
            theme_rates[tl['no']] = 0.0

    # 날짜 목록 로드
    dates_path = 'public/data/dates.json'
    try:
        import os
        from config import DATA_DIR
        dp = os.path.join(DATA_DIR, 'dates.json')
        with open(dp, 'r') as f:
            dates = json.load(f)
    except Exception:
        dates = []

    if not dates:
        logger.warning("dates.json이 비어있음")
        return

    logger.info(f"마이그레이션 대상: {dates}")

    # 각 날짜별 마이그레이션 (최신→과거 순)
    all_data = {}
    for d in dates:
        loaded = load_daily_data(d)
        if loaded:
            all_data[d] = loaded

    for d in dates:
        # 히스토리 데이터 (이 날짜 이전 데이터)
        history = []
        for od in dates:
            if od < d and od in all_data:
                history.append(all_data[od])
        migrate_day(d, mapping, theme_rates, history_data=history)

    # summary.json 갱신
    update_summary_index()
    logger.info("=== 마이그레이션 완료 ===")


if __name__ == '__main__':
    main()
