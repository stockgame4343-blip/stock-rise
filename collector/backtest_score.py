"""대장점수(score) ↔ 미래 수익률 상관 백테스트.

원본 score 와 forward_score 의 예측력 비교.
forward_score = score + theme_persist + near_52w + pullback_bounce + consec_limit_up.

가설:
  H1. 그날 score 가 높을수록 익일에도 강세 지속 → forward 1일 수익률 (+)
  H2. score 가 높을수록 N일 후에도 상승 → forward 3·5일 수익률 (+)
  H3. forward_score 가 score 보다 예측력 우월?

방법:
  - public/data/YYYYMMDD.json 14일치 로드
  - 각 (ticker, date) → forward_score 계산 (history 최근 5일·pullbacks 사용)
  - 다음 거래일에 같은 ticker 등장 시 close_price 비교
  - score 버킷 vs forward_score 버킷별 평균 수익률·적중률·상관계수 비교
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from forward_score import calculate_forward_score  # noqa: E402

DATA_DIR = Path(__file__).parent.parent / 'public' / 'data'

BUCKETS_SCORE = [
    ('score_80+', lambda s: s >= 80),
    ('score_70-79', lambda s: 70 <= s < 80),
    ('score_60-69', lambda s: 60 <= s < 70),
    ('score_50-59', lambda s: 50 <= s < 60),
    ('score_<50', lambda s: s < 50),
]
BUCKETS_FORWARD = [
    ('fwd_80+', lambda s: s >= 80),
    ('fwd_70-79', lambda s: 70 <= s < 80),
    ('fwd_60-69', lambda s: 60 <= s < 70),
    ('fwd_50-59', lambda s: 50 <= s < 60),
    ('fwd_<50', lambda s: s < 50),
]


def load_days() -> list[dict]:
    days = []
    for f in sorted(DATA_DIR.glob('2026*.json')):
        try:
            with open(f, encoding='utf-8') as fh:
                d = json.load(fh)
            if not d.get('is_final'):
                continue  # closing 데이터만 (intraday 제외)
            days.append({
                'date': d['date'],
                'rankings': d.get('rankings', []),
                'pullbacks': d.get('pullbacks', []),
            })
        except (OSError, json.JSONDecodeError):
            continue
    return days


def annotate_forward_scores(days):
    """각 종목에 forward_score 부여. history_data 는 직전 5일 사용."""
    for i, day in enumerate(days):
        history = days[max(0, i - 5):i][::-1]  # 최근 → 과거 순
        pullbacks = day.get('pullbacks') or []
        for stock in day['rankings']:
            result = calculate_forward_score(
                stock,
                history_data=history,
                pullbacks=pullbacks,
            )
            stock['_fwd_score'] = result['forward_total']
            stock['_fwd_bonus'] = result['forward_bonus']


def build_index(days):
    """ticker → {date: stock_dict} 인덱스."""
    by_ticker = defaultdict(dict)
    for day in days:
        for s in day['rankings']:
            by_ticker[s['ticker']][day['date']] = s
    return by_ticker


def forward_return(by_ticker, ticker, base_date, days_forward, sorted_dates):
    """base_date 의 다음 N번째 거래일 수익률 (none if not in rankings)."""
    base = by_ticker[ticker].get(base_date)
    if not base or not base.get('close_price'):
        return None
    try:
        idx = sorted_dates.index(base_date)
    except ValueError:
        return None
    target_idx = idx + days_forward
    if target_idx >= len(sorted_dates):
        return None
    target_date = sorted_dates[target_idx]
    target = by_ticker[ticker].get(target_date)
    if not target or not target.get('close_price'):
        return None
    return (target['close_price'] - base['close_price']) / base['close_price'] * 100


def bucket_analysis(samples, buckets):
    """[(score, return), ...] → 버킷별 통계."""
    results = []
    for label, predicate in buckets:
        rs = [r for s, r in samples if predicate(s)]
        if not rs:
            results.append((label, 0, None, None, None))
            continue
        avg = statistics.mean(rs)
        hit = sum(1 for r in rs if r > 0) / len(rs) * 100
        med = statistics.median(rs)
        results.append((label, len(rs), avg, hit, med))
    return results


def correlation(samples):
    """Pearson 상관계수 (score, return)."""
    if len(samples) < 5:
        return None
    xs = [s for s, _ in samples]
    ys = [r for _, r in samples]
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = sum((x - mx) ** 2 for x in xs) ** 0.5
    den_y = sum((y - my) ** 2 for y in ys) ** 0.5
    if den_x * den_y == 0:
        return None
    return num / (den_x * den_y)


def run_test(by_ticker, sorted_dates, days_forward, score_field='score'):
    """샘플 수집 → 버킷 분석 + 상관계수.

    score_field:
      'score' — 원본 대장점수 (0~100)
      '_fwd_score' — forward_score (0~130)
      'tp'/'tl'/'ti' — score_detail 컴포넌트
    """
    samples = []
    for ticker, by_date in by_ticker.items():
        for base_date in by_date:
            base = by_date[base_date]
            if score_field in ('score', '_fwd_score'):
                score = base.get(score_field)
            else:
                detail = base.get('score_detail') or {}
                score = detail.get(score_field)
            if score is None:
                continue
            r = forward_return(by_ticker, ticker, base_date, days_forward, sorted_dates)
            if r is None:
                continue
            samples.append((score, r))
    return samples


def fmt_row(label, n, avg, hit, med):
    if avg is None:
        return f"  {label:<14} n={n:>4}  (표본 부족)"
    return (f"  {label:<14} n={n:>4}  avg={avg:>+6.2f}%  "
            f"hit={hit:>5.1f}%  median={med:>+6.2f}%")


def main():
    days = load_days()
    annotate_forward_scores(days)
    by_ticker = build_index(days)
    sorted_dates = sorted({d['date'] for d in days})
    print(f"데이터: {len(days)}일 ({sorted_dates[0]} ~ {sorted_dates[-1]})")
    print(f"고유 종목: {len(by_ticker)}")
    print()

    # ─── 1) 원본 score vs forward 수익률 ───
    for n_days in [1, 3, 5]:
        print(f"━━━━━━━━ Forward {n_days}일 — 원본 SCORE 예측력 ━━━━━━━━")
        samples = run_test(by_ticker, sorted_dates, n_days, 'score')
        if samples:
            corr = correlation(samples)
            print(f"  샘플 {len(samples)}개  Pearson corr: {corr:+.4f}")
            for row in bucket_analysis(samples, BUCKETS_SCORE):
                print(fmt_row(*row))
        print()

    # ─── 2) forward_score (개선판) 예측력 ───
    for n_days in [1, 3, 5]:
        print(f"━━━━━━━━ Forward {n_days}일 — FORWARD_SCORE 예측력 ━━━━━━━━")
        samples = run_test(by_ticker, sorted_dates, n_days, '_fwd_score')
        if samples:
            corr = correlation(samples)
            print(f"  샘플 {len(samples)}개  Pearson corr: {corr:+.4f}")
            for row in bucket_analysis(samples, BUCKETS_FORWARD):
                print(fmt_row(*row))
        print()

    # ─── 3) 컴포넌트별 상관 (1일) ───
    print("━━━━━━━━ Forward 1일 — 컴포넌트별 상관 비교 ━━━━━━━━")
    print("  [원본 score 컴포넌트]")
    for field, max_v in [('tp', 35), ('tl', 45), ('ti', 20)]:
        samples = run_test(by_ticker, sorted_dates, 1, field)
        if samples:
            corr = correlation(samples)
            print(f"    {field:<3} (max {max_v}): corr={corr:+.4f}  n={len(samples)}")
    print("  [forward_score]")
    samples = run_test(by_ticker, sorted_dates, 1, '_fwd_score')
    if samples:
        corr = correlation(samples)
        print(f"    fwd (max 130): corr={corr:+.4f}  n={len(samples)}")


if __name__ == '__main__':
    main()
