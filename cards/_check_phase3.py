"""Phase 3 검증: 지수 fetch + 7장 HTML → PNG + 4모서리 검증.

실행 (stock-rise/ 디렉토리에서):
    python -m cards._check_phase3 [YYYYMMDD]
    python -m cards._check_phase3 20260424 --skip-fetch    # 가짜 지수 사용
"""

import os
import sys

from . import (
    config, data_loader, renderer, to_png,
    us_indices, kr_indices,
)


def main():
    args = sys.argv[1:]
    date = '20260424'
    skip_fetch = False
    for a in args:
        if a == '--skip-fetch':
            skip_fetch = True
        elif a.isdigit() and len(a) == 8:
            date = a

    # ─ 지수 가져오기 (실패 시 가짜로 fallback)
    if skip_fetch:
        print("=== 지수 fetch 스킵 (가짜 데이터) ===")
        us = {
            'sp500':  {'close': 7165.08,  'change':  56.68, 'pct': 0.80},
            'nasdaq': {'close': 24836.60, 'change': 398.09, 'pct': 1.63},
            'dow':    {'close': 49230.71, 'change': -79.61, 'pct': -0.16},
        }
        kr = {
            'kospi':  {'close': 6475.63, 'change': -0.18, 'pct': 0.00},
            'kosdaq': {'close': 1203.84, 'change': 29.53, 'pct': 2.51},
        }
    else:
        print("=== 지수 fetch ===")
        print("  yfinance...", end=' ', flush=True)
        us = us_indices.fetch(date)
        print(f"{'OK' if us else 'FAIL'}")
        if us:
            for k, v in us.items():
                print(f"    {k:>7}: {v['close']:>10,.2f}  {v['pct']:+.2f}%  ({v['date']})")
        print("  pykrx...", end=' ', flush=True)
        kr = kr_indices.fetch(date)
        print(f"{'OK' if kr else 'FAIL'}")
        if kr:
            for k, v in kr.items():
                print(f"    {k:>7}: {v['close']:>10,.2f}  {v['pct']:+.2f}%")

    # ─ 카드 dict + HTML 렌더
    print(f"\n=== HTML 렌더 ({date}) ===")
    cards = data_loader.build_all(date, us_indices=us, kr_indices=kr)
    htmls = renderer.render_all(cards)

    html_dir = config.HTML_OUT_DIR
    html_files = {}
    for name in renderer.CARD_NAMES:
        html = htmls.get(name)
        if html is None:
            html_files[name] = None
            continue
        path = renderer.write_html(html, name, html_dir, date)
        html_files[name] = path

    # ─ PNG 변환
    print(f"\n=== PNG 변환 → public/cards/ ===")
    png_files = {
        name: os.path.join(config.OUTPUT_DIR, f'{date}-{name}.png')
        for name in renderer.CARD_NAMES
    }
    results = to_png.html_to_png_batch(html_files, png_files)

    # ─ 검증 (1080×1080 + 4모서리 흰색 0)
    print(f"\n=== PNG 검증 ===")
    fail = 0
    for name, png_path in results.items():
        if png_path is None:
            print(f"  [{name:<8}] SKIP")
            continue
        ok, msg = to_png.verify_png(png_path)
        mark = '✓' if ok else '✗'
        print(f"  {mark} [{name:<8}] {msg}")
        if not ok:
            fail += 1

    print(f"\n  → 검증 실패 {fail}건")


if __name__ == '__main__':
    main()
