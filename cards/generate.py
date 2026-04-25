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


# 카드 dict 의 메타 필드 (검증 제외) — 모든 카드 공통이라 중복 false positive
META_FIELDS = {'date_full', 'label', 'series', 'date_kr', 'time_text',
               'eyebrow', 'weekday_ko', 'weekday_en'}


def _walk_content(card):
    """메타 필드 제외한 콘텐츠 문자열만 yield."""
    if not isinstance(card, dict):
        yield from _walk_strings(card)
        return
    for k, v in card.items():
        if k in META_FIELDS:
            continue
        yield from _walk_strings(v)


def _validate_text(cards):
    """검열·중복 검증. 위반 발견 시 list 반환 (빈 list = 통과).

    - 카드 dict 의 META_FIELDS (date_full/label 등) 는 검증 제외
    - 12자 이상 콘텐츠 문장이 2장 이상 카드에 동일 등장 = 위반
    - 테마 태그 같은 pre/pre3 양분 중복은 통과
    """
    failures = []
    seen = {}
    MIN_LEN = 12
    for name, card in cards.items():
        if name.startswith('_') or card is None:
            continue
        for s in _walk_content(card):
            forbidden = text_synth.has_forbidden(s)
            if forbidden:
                failures.append(f"[{name}] 검열 위반 {forbidden}: {s!r}")
            if len(s.strip()) >= MIN_LEN:
                seen.setdefault(s.strip(), []).append(name)
    for text, names in seen.items():
        unique = sorted(set(names))
        if len(unique) < 2:
            continue
        if all(n in ('pre', 'pre3') for n in unique) and '#' not in text and ' ' not in text:
            continue  # 테마 태그 의도된 양분
        failures.append(f"중복 문장 {unique}: {text!r}")
    return failures


SERIES_CARDS = {
    'pre':     ('pre', 'pre2', 'pre3'),         # 평일 07:30 — 장전 키워드 + NY 마감 + 주도 종목
    'closing': ('leader', 'leader2', 'close', 'close2'),  # 평일 16:30 — 대장주 + 마감 + 이슈
    'all':     renderer.CARD_NAMES,
}


def generate(date, fetch_us=True, fetch_kr=True, dry=False, series='all'):
    """카드 생성. series='pre'|'closing'|'all'.

    PRE 시리즈는 fallback=True — 오늘 마감 데이터가 없으면 (장 시작 전 07:30)
    가장 최근 거래일 데이터로 fallback. 카드 라벨은 인자 date (오늘) 그대로.
    """
    targets = SERIES_CARDS.get(series, renderer.CARD_NAMES)
    log.info(f"=== 카드 생성 시작 — date={date}, series={series} ({len(targets)}장 대상) ===")

    us = us_indices.fetch(date) if fetch_us else None
    kr = kr_indices.fetch(date) if fetch_kr else None
    log.info(f"  지수: us={'OK' if us else 'SKIP'}, kr={'OK' if kr else 'SKIP'}")

    fallback = (series == 'pre')
    cards = data_loader.build_all(date, us_indices=us, kr_indices=kr, fallback=fallback)
    log.info(f"  meta: {cards['_meta']}")

    # 검열·중복 검증은 대상 카드만
    cards_for_validate = {k: v for k, v in cards.items() if k in targets or k.startswith('_')}
    failures = _validate_text(cards_for_validate)
    if failures:
        for f in failures:
            log.error(f"  검증 실패: {f}")
        return 1

    htmls = renderer.render_all(cards)

    html_dir = config.HTML_OUT_DIR
    html_files = {}
    for name in targets:
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
        for name in targets
    }
    log.info(f"=== PNG 변환 → {config.OUTPUT_DIR} ===")
    results = to_png.html_to_png_batch(html_files, png_files)

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

    # SNS 공유용 og:image 고정 경로 — leader 갱신 시 latest-leader.png 동기화
    leader_png = results.get('leader')
    if leader_png and os.path.exists(leader_png):
        import shutil
        latest_path = os.path.join(config.OUTPUT_DIR, 'latest-leader.png')
        try:
            shutil.copyfile(leader_png, latest_path)
            log.info(f"  og:image 동기화 — latest-leader.png ← {os.path.basename(leader_png)}")
        except OSError as exc:
            log.warning("latest-leader.png 복사 실패: %s", exc)

    # public/cards/index.json 갱신 — 리포트 페이지(report.js)가 이 인덱스로 카드 노출
    _update_cards_index(date, [n for n, p in results.items() if p is not None])

    log.info(f"=== 완료 — 생성 {success}/{len(targets)}장, 검증 실패 {len(bad)}건 ===")
    return 0 if not bad else 2


# 카드 메타 (report.js / cards.html 공용)
CARD_META = {
    'pre':     ('pre',    '장전 키워드'),
    'pre2':    ('pre',    '뉴욕 마감'),
    'pre3':    ('pre',    '주도 종목'),
    'leader':  ('leader', '오늘의 대장주'),
    'leader2': ('leader', '대장 테마 멤버'),
    'close':   ('close',  '마감 한줄'),
    'close2':  ('close',  '마감 이슈·섹터'),
}
NAME_ORDER = ('pre', 'pre2', 'pre3', 'leader', 'leader2', 'close', 'close2')


def _update_cards_index(date, generated):
    """public/cards/index.json — 시리즈별 시간차 갱신 보존.

    같은 날짜에 PRE 시리즈만 새로 생성되면 기존 LEADER/CLOSE 항목은 그대로 두고
    PRE 항목만 덮어씀. 리포트 페이지가 시간 흐름에 따라 7장이 채워지는 걸 봄.
    """
    if not generated:
        return
    index_path = os.path.join(config.OUTPUT_DIR, 'index.json')
    index = {}
    if os.path.exists(index_path):
        try:
            with open(index_path, encoding='utf-8') as f:
                index = json.load(f)
        except (json.JSONDecodeError, OSError):
            index = {}

    by_file = {c['file']: c for c in index.get(date, [])}
    for name in generated:
        meta = CARD_META.get(name)
        if not meta:
            continue
        type_, title = meta
        fname = f'{date}-{name}.png'
        by_file[fname] = {'type': type_, 'file': fname, 'title': title}

    name_idx = {n: i for i, n in enumerate(NAME_ORDER)}

    def _key(card):
        stem = card['file'].rsplit('.', 1)[0].split('-', 1)[1]
        return name_idx.get(stem, 99)

    index[date] = sorted(by_file.values(), key=_key)

    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    log.info(f"  index.json 갱신 — {date} {len(index[date])}장")


def main():
    _setup_logging()
    p = argparse.ArgumentParser(description='StockRise 카드뉴스 일일 생성')
    p.add_argument('date', nargs='?', help='YYYYMMDD (생략 시 dates.json 최신)')
    p.add_argument('--series', choices=['pre', 'closing', 'all'], default='all',
                   help='pre=장전 3장(07:30) / closing=마감 4장(16:30) / all=7장')
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
        series=args.series,
    ))


if __name__ == '__main__':
    main()
