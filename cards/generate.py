"""카드 일일 생성 진입점.

사용:
    cd stock-rise
    python -m cards.generate                 # dates.json 최신 거래일 사용
    python -m cards.generate 20260424        # 특정 날짜
    python -m cards.generate 20260424 --dry  # PNG 미생성 (HTML만)
    python -m cards.generate --skip-us       # 미국 지수 카드 스킵
    python -m cards.generate --skip-kr       # 한국 지수 카드 영역 스킵

운영 흐름:
    1. dates.json 에서 가장 최근 거래일 자동 선택 (또는 인자)
    2. yfinance + pykrx 로 지수 fetch (실패해도 다른 카드는 진행)
    3. 카드 7장 dict 빌드 → HTML 렌더 → PNG 변환
    4. public/cards/{date}-{name}.png 저장
    5. 검열·중복·1080×1080·모서리 검증
    6. 결과 요약 출력 + 종료코드
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

from . import (
    config, data_loader, renderer, text_synth, to_png,
    us_indices, kr_indices,
)


log = logging.getLogger('cards.generate')


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
    )


def _latest_trading_day():
    """public/data/dates.json 의 첫 항목 = 가장 최근 거래일."""
    path = os.path.join(config.DATA_DIR, 'dates.json')
    if not os.path.exists(path):
        raise FileNotFoundError(f'{path} 없음 — collector 가 먼저 실행돼야 함')
    with open(path, encoding='utf-8') as f:
        dates = json.load(f)
    if not dates:
        raise ValueError('dates.json 비어 있음')
    return dates[0]


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def _validate_text(cards):
    """검열·중복 검증. 위반 발견 시 list 반환 (빈 list = 통과).

    중복 룰:
      - 12자 이상 동일 문장이 카드 2~5장에만 등장하면 위반 (의미 중복)
      - 모든 카드(>=6장)에 등장하는 짧은 메타(시간·라벨)는 통과
      - 테마 태그 같은 pre/pre3 양분 중복은 통과
    """
    failures = []
    seen = {}
    MIN_LEN = 12
    META_THRESHOLD = 6  # 이 카드 수 이상 등장 = 메타 (브랜딩·시간) 로 간주
    for name, card in cards.items():
        if name.startswith('_') or card is None:
            continue
        for s in _walk_strings(card):
            forbidden = text_synth.has_forbidden(s)
            if forbidden:
                failures.append(f"[{name}] 검열 위반 {forbidden}: {s!r}")
            if len(s.strip()) >= MIN_LEN:
                seen.setdefault(s.strip(), []).append(name)
    for text, names in seen.items():
        unique = sorted(set(names))
        if len(unique) < 2:
            continue
        if len(unique) >= META_THRESHOLD:
            continue  # 모든/대부분 카드 공통 메타
        if all(n in ('pre', 'pre3') for n in unique) and '#' not in text and ' ' not in text:
            continue  # 테마 태그 의도된 양분
        failures.append(f"중복 문장 {unique}: {text!r}")
    return failures


def generate(date, fetch_us=True, fetch_kr=True, dry=False):
    """카드 7장 생성. dry=True 면 PNG 미생성."""
    log.info(f"=== 카드 생성 시작 — date={date} ===")

    us = us_indices.fetch(date) if fetch_us else None
    kr = kr_indices.fetch(date) if fetch_kr else None
    log.info(f"  지수: us={'OK' if us else 'SKIP'}, kr={'OK' if kr else 'SKIP'}")

    cards = data_loader.build_all(date, us_indices=us, kr_indices=kr)
    log.info(f"  meta: {cards['_meta']}")

    failures = _validate_text(cards)
    if failures:
        for f in failures:
            log.error(f"  검증 실패: {f}")
        return 1

    htmls = renderer.render_all(cards)

    html_dir = config.HTML_OUT_DIR
    html_files = {}
    for name in renderer.CARD_NAMES:
        html = htmls.get(name)
        if html is None:
            html_files[name] = None
            continue
        html_files[name] = renderer.write_html(html, name, html_dir, date)

    if dry:
        log.info("=== dry run — PNG 미생성 ===")
        return 0

    png_files = {
        name: os.path.join(config.OUTPUT_DIR, f'{date}-{name}.png')
        for name in renderer.CARD_NAMES
    }
    log.info(f"=== PNG 변환 → {config.OUTPUT_DIR} ===")
    results = to_png.html_to_png_batch(html_files, png_files)

    # ─ PNG 검증 (1080×1080 + 4모서리 흰 짤림 0)
    bad = []
    for name, png_path in results.items():
        if png_path is None:
            continue
        ok, msg = to_png.verify_png(png_path)
        if not ok:
            log.error(f"  ✗ [{name}] {msg}")
            bad.append(name)
        else:
            log.info(f"  ✓ [{name}] {msg}")

    success = sum(1 for v in results.values() if v is not None)
    log.info(f"=== 완료 — 생성 {success}/7장, 검증 실패 {len(bad)}건 ===")
    return 0 if not bad else 2


def main():
    _setup_logging()
    p = argparse.ArgumentParser(description='StockRise 카드뉴스 일일 생성')
    p.add_argument('date', nargs='?', help='YYYYMMDD (생략 시 dates.json 최신)')
    p.add_argument('--dry', action='store_true', help='PNG 미생성 (HTML만)')
    p.add_argument('--skip-us', action='store_true', help='미국 지수 fetch 스킵')
    p.add_argument('--skip-kr', action='store_true', help='한국 지수 fetch 스킵')
    args = p.parse_args()

    date = args.date or _latest_trading_day()
    if not (len(date) == 8 and date.isdigit()):
        print(f"잘못된 날짜 형식: {date}", file=sys.stderr)
        sys.exit(1)

    sys.exit(generate(
        date,
        fetch_us=not args.skip_us,
        fetch_kr=not args.skip_kr,
        dry=args.dry,
    ))


if __name__ == '__main__':
    main()
