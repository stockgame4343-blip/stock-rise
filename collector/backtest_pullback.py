"""Backtest pullback/rebound parameter sweeps against cached OHLC data."""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from itertools import product

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKTEST_DATA = os.path.join(ROOT, "collector", "backtest.json")
CACHE_DIR = os.path.join(ROOT, "collector", "_ohlc_cache")
CSV_PATH = os.path.join(ROOT, "collector", "backtest_pullback_result.csv")

HEADERS = {"User-Agent": "Mozilla/5.0"}

PEAK_PCTS = [15, 20, 25, 30]
DROP_PCTS = [20, 25, 30, 35]
REBOUND_PCTS = [15, 20, 25]

LOOKBACK_DAYS = 365
MAX_DROP_DAYS = 60
MAX_REBOUND_DAYS = 120
FWD_DAYS = [30, 60]
BREAKOUT_WINDOW = 60
REQUEST_DELAY_SECONDS = 0.05

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def load_universe():
    """Extract the unique ticker universe from backtest.json."""
    with open(BACKTEST_DATA, "r", encoding="utf-8") as file:
        data = json.load(file)

    tickers = set()
    for entry in data:
        for stock in entry.get("stocks", []):
            ticker = stock.get("ticker")
            if ticker:
                tickers.add(ticker)

    return sorted(tickers)


def fetch_ohlc(ticker):
    """Load OHLC data from cache or fetch it from the Naver chart API."""
    cache_path = os.path.join(CACHE_DIR, f"{ticker}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as file:
                cached = json.load(file)
            if isinstance(cached, list) and cached:
                return cached
        except (json.JSONDecodeError, OSError):
            pass

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    url = (
        f"https://api.stock.naver.com/chart/domestic/item/{ticker}/day"
        f"?startDateTime={start_date}&endDateTime={end_date}"
    )

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json() or []
    except Exception as exc:
        logger.warning("    API fetch failed for %s: %s", ticker, exc)
        return []

    if data:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False)
        time.sleep(REQUEST_DELAY_SECONDS)

    return data


def cache_all_tickers(tickers):
    logger.info("Caching OHLC for %s tickers", len(tickers))
    for index, ticker in enumerate(tickers, start=1):
        fetch_ohlc(ticker)
        if index % 50 == 0:
            logger.info("  cache progress: %s/%s", index, len(tickers))
    logger.info("OHLC cache warmup complete")


def normalize_bars(bars):
    """Normalize API responses into sorted (date, high, low, close) tuples."""
    normalized = []
    for bar in bars:
        date_str = bar.get("localDate")
        high_price = bar.get("highPrice")
        low_price = bar.get("lowPrice")
        close_price = bar.get("closePrice")
        if not date_str or high_price is None or low_price is None or close_price is None:
            continue
        try:
            normalized.append(
                (
                    date_str,
                    int(high_price),
                    int(low_price),
                    int(close_price),
                )
            )
        except (TypeError, ValueError):
            continue

    normalized.sort(key=lambda item: item[0])
    return normalized


def simulate_ticker(bars, peak_pct, drop_pct, rebound_pct):
    """Find pullback/rebound patterns for a single ticker."""
    results = []
    bar_count = len(bars)
    if bar_count < MAX_REBOUND_DAYS + max(FWD_DAYS):
        return results

    index = 0
    while index < bar_count:
        prev_close = bars[index - 1][3] if index > 0 else 0
        if prev_close <= 0:
            index += 1
            continue

        change_pct = (bars[index][3] - prev_close) / prev_close * 100
        if change_pct < peak_pct:
            index += 1
            continue

        peak_idx = index
        peak_high = bars[peak_idx][1]
        if peak_high <= 0:
            index += 1
            continue

        trough_idx = None
        drop_limit = min(peak_idx + 1 + MAX_DROP_DAYS, bar_count)
        for candidate_idx in range(peak_idx + 1, drop_limit):
            low_price = bars[candidate_idx][2]
            if low_price <= 0:
                continue
            drop_from_peak = (peak_high - low_price) / peak_high * 100
            if drop_from_peak >= drop_pct:
                trough_idx = candidate_idx
                break

        if trough_idx is None:
            index = peak_idx + 1
            continue

        valid_lows = [
            bars[candidate_idx][2]
            for candidate_idx in range(peak_idx + 1, trough_idx + 1)
            if bars[candidate_idx][2] > 0
        ]
        if not valid_lows:
            index = peak_idx + 1
            continue

        running_low = min(valid_lows)
        rebound_low = running_low
        rebound_idx = None
        rebound_limit = min(peak_idx + 1 + MAX_REBOUND_DAYS, bar_count)

        for candidate_idx in range(trough_idx, rebound_limit):
            low_price = bars[candidate_idx][2]
            high_price = bars[candidate_idx][1]
            if low_price > 0:
                running_low = min(running_low, low_price)
            if running_low <= 0:
                continue
            rebound_from_low = (high_price - running_low) / running_low * 100
            if rebound_from_low >= rebound_pct:
                rebound_idx = candidate_idx
                rebound_low = running_low
                break

        if rebound_idx is None:
            index = peak_idx + 1
            continue

        rebound_close = bars[rebound_idx][3]
        if rebound_close <= 0:
            index = rebound_idx + 1
            continue

        fwd_returns = {}
        for days in FWD_DAYS:
            target_idx = rebound_idx + days
            if target_idx < bar_count:
                fwd_returns[days] = (
                    (bars[target_idx][3] - rebound_close) / rebound_close * 100
                )
            else:
                fwd_returns[days] = None

        breakout = False
        near_miss = False
        breakout_limit = min(rebound_idx + BREAKOUT_WINDOW, bar_count)
        for candidate_idx in range(rebound_idx, breakout_limit):
            high_price = bars[candidate_idx][1]
            if high_price > peak_high:
                breakout = True
                break
            if high_price >= peak_high * 0.95:
                near_miss = True

        double_top = (not breakout) and near_miss
        if double_top:
            low_after_miss = any(
                bars[candidate_idx][2] < rebound_low * 0.95
                for candidate_idx in range(rebound_idx, breakout_limit)
                if bars[candidate_idx][2] > 0
            )
            double_top = low_after_miss

        results.append(
            {
                "peak_idx": peak_idx,
                "rebound_idx": rebound_idx,
                "breakout": breakout,
                "double_top": double_top,
                "fwd_returns": fwd_returns,
            }
        )

        index = rebound_idx + 1

    return results


def run_sweep(all_bars):
    """Evaluate every parameter combination across the full universe."""
    combos = list(product(PEAK_PCTS, DROP_PCTS, REBOUND_PCTS))
    logger.info("Running parameter sweep for %s combinations", len(combos))

    rows = []
    for peak_pct, drop_pct, rebound_pct in combos:
        samples = []
        for bars in all_bars.values():
            samples.extend(simulate_ticker(bars, peak_pct, drop_pct, rebound_pct))

        sample_count = len(samples)
        if sample_count == 0:
            rows.append(
                {
                    "peak_pct": peak_pct,
                    "drop_pct": drop_pct,
                    "rebound_pct": rebound_pct,
                    "n_samples": 0,
                    "breakout_pct": 0,
                    "double_top_pct": 0,
                    "avg_fwd30": 0,
                    "avg_fwd60": 0,
                    "score": 0,
                }
            )
            continue

        breakout_count = sum(1 for sample in samples if sample["breakout"])
        double_top_count = sum(1 for sample in samples if sample["double_top"])

        def avg_fwd(days):
            values = [
                sample["fwd_returns"].get(days)
                for sample in samples
                if sample["fwd_returns"].get(days) is not None
            ]
            return sum(values) / len(values) if values else 0

        rows.append(
            {
                "peak_pct": peak_pct,
                "drop_pct": drop_pct,
                "rebound_pct": rebound_pct,
                "n_samples": sample_count,
                "breakout_pct": breakout_count / sample_count * 100,
                "double_top_pct": double_top_count / sample_count * 100,
                "avg_fwd30": avg_fwd(30),
                "avg_fwd60": avg_fwd(60),
                "score": (breakout_count - double_top_count) / sample_count * 100,
            }
        )

    return rows


def print_table(rows):
    rows = sorted(rows, key=lambda row: row["score"], reverse=True)
    header = (
        f'{"peak":>5} {"drop":>5} {"bounce":>7} {"n":>6} '
        f'{"breakout%":>10} {"doubleT%":>9} {"fwd30%":>8} {"fwd60%":>8} {"score":>7}'
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f'{row["peak_pct"]:>5} {row["drop_pct"]:>5} {row["rebound_pct"]:>7} '
            f'{row["n_samples"]:>6} {row["breakout_pct"]:>10.1f} '
            f'{row["double_top_pct"]:>9.1f} {row["avg_fwd30"]:>+8.1f} '
            f'{row["avg_fwd60"]:>+8.1f} {row["score"]:>+7.1f}'
        )


def write_csv(rows):
    with open(CSV_PATH, "w", encoding="utf-8") as file:
        file.write(
            "peak_pct,drop_pct,rebound_pct,n_samples,breakout_pct,double_top_pct,"
            "avg_fwd30,avg_fwd60,score\n"
        )
        for row in sorted(rows, key=lambda item: item["score"], reverse=True):
            file.write(
                f'{row["peak_pct"]},{row["drop_pct"]},{row["rebound_pct"]},'
                f'{row["n_samples"]},{row["breakout_pct"]:.2f},'
                f'{row["double_top_pct"]:.2f},{row["avg_fwd30"]:.2f},'
                f'{row["avg_fwd60"]:.2f},{row["score"]:.2f}\n'
            )


def main():
    tickers = load_universe()
    logger.info("Universe size: %s tickers", len(tickers))

    cache_all_tickers(tickers)

    logger.info("Loading and normalizing OHLC data")
    all_bars = {}
    for ticker in tickers:
        bars = normalize_bars(fetch_ohlc(ticker))
        if len(bars) >= 30:
            all_bars[ticker] = bars
    logger.info("Usable tickers: %s", len(all_bars))

    rows = run_sweep(all_bars)

    print()
    print("===== Pullback parameter sweep results (sorted by score) =====")
    print_table(rows)

    write_csv(rows)
    logger.info("CSV written to %s", CSV_PATH)


if __name__ == "__main__":
    main()
