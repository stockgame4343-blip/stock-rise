"""Phase 2 검증: 04.24 데이터로 카드 7장 HTML 렌더 → cards/_render/ 저장.

실행 (stock-rise/ 디렉토리에서):
    python -m cards._check_phase2 [YYYYMMDD]

저장된 HTML 은 PNG 변환 입력 + 디버그 미리보기 용. public 외부라 vercel 배포 안 됨.
"""

import os
import sys

from . import config, data_loader, renderer


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else '20260424'

    fake_us = {
        'sp500':  {'close': 7165.08,  'change':  56.68, 'pct': 0.80},
        'nasdaq': {'close': 24836.60, 'change': 398.09, 'pct': 1.63},
        'dow':    {'close': 49230.71, 'change': -79.61, 'pct': -0.16},
    }
    fake_kr = {
        'kospi':  {'close': 6475.63, 'change': -0.18, 'pct': 0.00},
        'kosdaq': {'close': 1203.84, 'change': 29.53, 'pct': 2.51},
    }

    cards = data_loader.build_all(date, us_indices=fake_us, kr_indices=fake_kr)
    htmls = renderer.render_all(cards)

    out_dir = config.HTML_OUT_DIR
    print(f"\n=== HTML 저장: {out_dir} ===\n")
    for name in renderer.CARD_NAMES:
        html = htmls.get(name)
        if html is None:
            print(f"  [{name:<8}] None (스킵)")
            continue
        path = renderer.write_html(html, name, out_dir, date)
        print(f"  [{name:<8}] {len(html):>6} bytes → {os.path.relpath(path, config.PROJECT_ROOT)}")

    print(f"\n  HTML 위치: cards/_render/{date}-leader.html (PNG 변환 입력)\n")


if __name__ == '__main__':
    main()
