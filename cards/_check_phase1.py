"""Phase 1 검증 스크립트.

실행 (stock-rise/ 디렉토리에서):
    python -m cards._check_phase1 [YYYYMMDD]

확인 항목:
    1. 카드 7장 dict 모두 빌드되는가 (pre2_ny는 us_indices 없으면 None 정상)
    2. 검열 단어가 카드 텍스트에 0건인가
    3. 같은 문장이 2장 이상에 중복되는가
"""

import json
import sys

from . import data_loader, text_synth


def _walk_strings(value):
    """dict/list 안의 모든 문자열을 순회."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else '20260424'

    # ─ 가짜 미국/한국 지수 (Phase 3 전 임시)
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

    # ─ 1. 카드 7장 출력
    print(f"=== 카드 빌드 결과 ({date}) ===\n")
    for name in ('pre', 'pre2', 'pre3', 'leader', 'leader2', 'close', 'close2'):
        card = cards[name]
        if card is None:
            print(f"  [{name:<8}] None (스킵)")
        else:
            print(f"  [{name:<8}] OK ({len(json.dumps(card, ensure_ascii=False))} bytes)")
    print(f"\n  meta: {json.dumps(cards['_meta'], ensure_ascii=False)}\n")

    # ─ 2. 검열 검증
    print("=== 검열 검증 (FORBIDDEN_WORDS 등장) ===\n")
    fail = 0
    for name, card in cards.items():
        if name.startswith('_') or card is None:
            continue
        for s in _walk_strings(card):
            forbidden = text_synth.has_forbidden(s)
            if forbidden:
                print(f"  [{name}] {forbidden}: {s!r}")
                fail += 1
    print(f"\n  → 위반 {fail}건\n")

    # ─ 3. 카드 간 텍스트 중복 검증
    print("=== 카드 간 동일 문장 중복 ===\n")
    seen = {}  # text → [card name]
    MIN_LEN = 12  # 짧은 라벨은 제외
    for name, card in cards.items():
        if name.startswith('_') or card is None:
            continue
        for s in _walk_strings(card):
            s_norm = s.strip()
            if len(s_norm) < MIN_LEN:
                continue
            seen.setdefault(s_norm, []).append(name)
    dup_count = 0
    for text, names in seen.items():
        unique_names = list(set(names))
        if len(unique_names) >= 2:
            print(f"  {unique_names}: {text!r}")
            dup_count += 1
    print(f"\n  → 중복 문장 {dup_count}건\n")

    # ─ 4. 샘플 카드 펼쳐 보기
    print("=== leader 카드 ===\n")
    print(json.dumps(cards['leader'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
