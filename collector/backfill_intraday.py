"""Backfill high_price and low_price for recent daily ranking JSON files."""

import json
import logging
import os
import time
from datetime import datetime, timedelta

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "public", "data")

HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_AGE_DAYS = 120
REQUEST_DELAY_SECONDS = 0.05

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def fetch_ohlc_entry(ticker, date_str):
    """Fetch a single-day OHLC entry for the given ticker."""
    url = (
        f"https://api.stock.naver.com/chart/domestic/item/{ticker}/day"
        f"?startDateTime={date_str}&endDateTime={date_str}"
    )
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json() or []
    except Exception as exc:
        logger.warning("    API fetch failed for %s: %s", ticker, exc)
        return None

    if not isinstance(data, list) or not data:
        return None

    return next((item for item in data if item.get("localDate") == date_str), data[0])


def has_valid_intraday_prices(ranking):
    """Return True when both high_price and low_price are present and positive."""
    try:
        high_price = int(ranking.get("high_price", 0) or 0)
        low_price = int(ranking.get("low_price", 0) or 0)
    except (TypeError, ValueError):
        return False

    return high_price > 0 and low_price > 0


def backfill_file(path):
    """Backfill one YYYYMMDD.json file.

    Returns:
        tuple[int, int, int]: updated_count, already_complete_count, failed_count
    """
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    date_str = data.get("date") or os.path.basename(path).replace(".json", "")
    rankings = data.get("rankings", [])
    if not rankings:
        return 0, 0, 0

    pending = [ranking for ranking in rankings if not has_valid_intraday_prices(ranking)]
    already_complete = len(rankings) - len(pending)

    if not pending:
        logger.info("  %s: already complete", date_str)
        return 0, already_complete, 0

    logger.info(
        "  %s: backfilling %s of %s rankings",
        date_str,
        len(pending),
        len(rankings),
    )

    updated = 0
    failed = 0
    for index, ranking in enumerate(pending, start=1):
        ticker = ranking.get("ticker")
        if not ticker:
            failed += 1
            continue

        entry = fetch_ohlc_entry(ticker, date_str)
        if entry is None:
            failed += 1
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        try:
            high_price = int(entry.get("highPrice") or 0)
            low_price = int(entry.get("lowPrice") or 0)
        except (TypeError, ValueError):
            high_price = 0
            low_price = 0

        if high_price <= 0 or low_price <= 0:
            failed += 1
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        ranking["high_price"] = high_price
        ranking["low_price"] = low_price
        updated += 1

        if index % 20 == 0:
            logger.info("    progress: %s/%s", index, len(pending))

        time.sleep(REQUEST_DELAY_SECONDS)

    if updated > 0:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    logger.info(
        "  %s: updated=%s already_complete=%s failed=%s",
        date_str,
        updated,
        already_complete,
        failed,
    )
    return updated, already_complete, failed


def main():
    cutoff = (datetime.now() - timedelta(days=MAX_AGE_DAYS)).strftime("%Y%m%d")
    files = []
    for file_name in sorted(os.listdir(DATA_DIR)):
        if not file_name.endswith(".json") or len(file_name) != 13:
            continue
        date_part = file_name.replace(".json", "")
        if not date_part.isdigit():
            continue
        if date_part < cutoff:
            continue
        files.append(os.path.join(DATA_DIR, file_name))

    logger.info("Backfill target files: %s (cutoff=%s)", len(files), cutoff)

    total_updated = 0
    total_already_complete = 0
    total_failed = 0

    for path in files:
        try:
            updated, already_complete, failed = backfill_file(path)
            total_updated += updated
            total_already_complete += already_complete
            total_failed += failed
        except Exception as exc:
            logger.error("  failed to backfill %s: %s", path, exc)

    logger.info(
        "Backfill done: updated=%s already_complete=%s failed=%s",
        total_updated,
        total_already_complete,
        total_failed,
    )


if __name__ == "__main__":
    main()
