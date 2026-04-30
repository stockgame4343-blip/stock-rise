"""다변량 회귀 — 어떤 시그널이 익일 수익률을 진짜 예측하나.

numpy 만으로 OLS 풀어서 각 feature 의 계수 + 단변량 R² 비교.

Features (각 종목, 각 거래일):
  tp, tl, ti                    — 원본 score 컴포넌트
  theme_persist                 — 같은 theme_tag 가 최근 5일 등장 횟수
  near_52w_ratio                — close / high_52w (0~1.05+)
  pullback_bounce_pct           — pullbacks 의 bouncePct (해당 시), 없으면 0
  consec_limit_up               — 최근 연속 상한가 카운트
  log_trading_value             — log10(trading_value)  (스케일 정규화)

Target: forward 1일 수익률 (%)

selection bias: 표본은 "다음 거래일에도 rankings 등장한 종목" 한정.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from forward_score import (  # noqa: E402
    LIMIT_UP_THRESHOLD,
    _consec_limit_up_score,
    _theme_persistence_score,
)

DATA_DIR = Path(__file__).parent.parent / 'public' / 'data'


def load_days():
    days = []
    for f in sorted(DATA_DIR.glob('2026*.json')):
        try:
            d = json.load(open(f, encoding='utf-8'))
            if not d.get('is_final'):
                continue
            days.append({
                'date': d['date'],
                'rankings': d.get('rankings', []),
                'pullbacks': d.get('pullbacks', []),
            })
        except (OSError, json.JSONDecodeError):
            continue
    return days


def build_features(days):
    """샘플 = (X 행렬, y 벡터, feature 이름)."""
    sorted_dates = [d['date'] for d in days]
    by_ticker_date = defaultdict(dict)
    for day in days:
        for s in day['rankings']:
            by_ticker_date[s['ticker']][day['date']] = s

    feature_names = [
        'tp', 'tl', 'ti',
        'theme_persist', 'near_52w_ratio', 'pullback_bounce_pct',
        'consec_limit_up', 'log_trading_value',
    ]
    X_rows = []
    y_rows = []

    for i, day in enumerate(days):
        history = days[max(0, i - 5):i][::-1]
        pullbacks_map = {p.get('ticker'): p for p in day.get('pullbacks', [])}

        for stock in day['rankings']:
            ticker = stock['ticker']
            close = stock.get('close_price') or 0
            if close <= 0:
                continue

            # forward 1일 수익률
            if i + 1 >= len(days):
                continue
            next_close = by_ticker_date[ticker].get(sorted_dates[i + 1], {}).get('close_price')
            if not next_close:
                continue
            ret = (next_close - close) / close * 100

            detail = stock.get('score_detail') or {}
            tp = detail.get('tp', 0) or 0
            tl = detail.get('tl', 0) or 0
            ti = detail.get('ti', 0) or 0

            theme_persist = _theme_persistence_score(stock, history) / 2  # 0~10 → 0~5 (raw count)
            high_52w = stock.get('high_52w') or 0
            near_52w_ratio = (close / high_52w) if high_52w > 0 else 0.0
            pull = pullbacks_map.get(ticker)
            pull_bounce = (pull.get('bouncePct') or 0) if pull else 0
            consec_lu = _consec_limit_up_score(stock, history)

            tv = stock.get('trading_value') or 0
            log_tv = math.log10(tv) if tv > 0 else 0

            X_rows.append([tp, tl, ti, theme_persist, near_52w_ratio, pull_bounce,
                           consec_lu, log_tv])
            y_rows.append(ret)

    X = np.array(X_rows, dtype=float)
    y = np.array(y_rows, dtype=float)
    return X, y, feature_names


def standardize(X):
    """각 열을 (x - μ) / σ — 계수 비교 가능하게."""
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std = np.where(std == 0, 1, std)
    return (X - mean) / std, mean, std


def ols(X, y):
    """OLS β = (X'X)^-1 X'y. intercept 포함 X."""
    X_aug = np.hstack([np.ones((X.shape[0], 1)), X])
    beta, *_ = np.linalg.lstsq(X_aug, y, rcond=None)
    y_pred = X_aug @ beta
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    return beta, r2


def univariate_r2(X, y, feature_names):
    """각 feature 단독 회귀 → R² (3-tuple: name, R², corr)."""
    out = []
    for j, name in enumerate(feature_names):
        x = X[:, j]
        if x.std() == 0:
            out.append((name, 0.0, 0.0))
            continue
        corr = np.corrcoef(x, y)[0, 1]
        if np.isnan(corr):
            out.append((name, 0.0, 0.0))
        else:
            out.append((name, corr ** 2, corr))
    return out


def main():
    days = load_days()
    X, y, names = build_features(days)
    print(f"샘플: {len(y)}, features: {len(names)}")
    print(f"target(forward 1일 수익률): mean={y.mean():.2f}%, std={y.std():.2f}%")
    print()

    print("━━━━━━━━ 단변량 R² (어느 feature 가 단독으로 가장 강한가) ━━━━━━━━")
    uni = univariate_r2(X, y, names)
    uni.sort(key=lambda t: -t[1])
    for name, r2, corr in uni:
        sign = '+' if corr >= 0 else '-'
        print(f"  {name:<22}  R²={r2:.4f}  corr={sign}{abs(corr):.4f}")

    print()
    print("━━━━━━━━ 다변량 OLS — 표준화 계수 (절대값 = 영향력) ━━━━━━━━")
    Xs, mean, std = standardize(X)
    beta, r2 = ols(Xs, y)
    print(f"  전체 R² (표준화 모델): {r2:.4f}")
    print(f"  intercept: {beta[0]:+.3f}")
    pairs = sorted(zip(names, beta[1:]), key=lambda p: -abs(p[1]))
    for name, coef in pairs:
        bar_len = int(min(abs(coef) * 6, 30))
        bar = ('+' if coef > 0 else '-') * bar_len
        print(f"  {name:<22}  coef={coef:+.4f}  {bar}")

    print()
    print("해석:")
    print("  - 단변량 R²: feature 단독으로 forward 수익률 변동의 몇 % 설명")
    print("  - 다변량 표준화 계수: 다른 변수 통제 후 영향력 (절대값 클수록 ↑)")
    print("  - 두 결과 모두에서 일관되게 강한 feature 가 진짜 예측력 있음")


if __name__ == '__main__':
    main()
