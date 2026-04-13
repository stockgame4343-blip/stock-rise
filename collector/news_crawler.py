"""네이버 증권 뉴스/섹터/업종등락률/증권사리포트 크롤링"""
import random
import time
import logging
import re

import requests
from bs4 import BeautifulSoup

from config import (
    USER_AGENTS,
    REQUEST_DELAY_MIN, REQUEST_DELAY_MAX,
)

logger = logging.getLogger(__name__)

NAVER_NEWS_IFRAME_URL = 'https://finance.naver.com/item/news_news.naver?code={ticker}&page=&clusterId='
NAVER_ITEM_MAIN_URL = 'https://finance.naver.com/item/main.naver?code={ticker}'
NAVER_RESEARCH_URL = 'https://finance.naver.com/research/company_list.naver?keyword=&brokerCode=&writeFromDate=&writeToDate=&searchType=itemCode&itemCode={ticker}&page=1'
NAVER_SECTOR_RISE_URL = 'https://finance.naver.com/sise/sise_group.naver?type=upjong'


def _get_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Referer': 'https://finance.naver.com/',
    }


def _request_with_retry(url, max_retries=3, timeout=10):
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=_get_headers(), timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            if attempt < max_retries - 1:
                time.sleep(REQUEST_DELAY_MIN)
            else:
                logger.warning(f"  요청 실패 ({max_retries}회): {url}")
    return None


def _delay():
    time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))


# ── 뉴스 크롤링 ──

def crawl_news(ticker, max_articles=10):
    """단일 종목의 최근 뉴스 크롤링 (제목, 링크, 출처)"""
    url = NAVER_NEWS_IFRAME_URL.format(ticker=ticker)
    resp = _request_with_retry(url)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    articles = []
    seen_titles = set()

    rows = soup.select('table.type5 tr')
    for row in rows:
        if len(articles) >= max_articles:
            break

        title_tag = row.select_one('td.title a')
        source_tag = row.select_one('td.info')

        if title_tag:
            title = title_tag.get_text(strip=True)
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)

            link = title_tag.get('href', '')
            if link and not link.startswith('http'):
                link = 'https://finance.naver.com' + link
            source = source_tag.get_text(strip=True) if source_tag else ''

            articles.append({
                'title': title,
                'link': link,
                'source': source,
            })

    return articles


def crawl_news_for_tickers(tickers, date_str):
    """복수 종목의 뉴스를 일괄 크롤링"""
    news_map = {}
    total = len(tickers)

    for idx, ticker in enumerate(tickers):
        try:
            articles = crawl_news(ticker)
            news_map[ticker] = articles
            if (idx + 1) % 20 == 0:
                logger.info(f"  뉴스 수집 진행: {idx + 1}/{total}")
        except Exception as e:
            logger.warning(f"  뉴스 크롤링 실패 ({ticker}): {e}")
            news_map[ticker] = []

        _delay()

    return news_map


# ── 섹터 크롤링 ──

def crawl_sector(ticker):
    """단일 종목의 업종/섹터 정보 크롤링"""
    url = NAVER_ITEM_MAIN_URL.format(ticker=ticker)
    resp = _request_with_retry(url)
    if resp is None:
        return ''

    soup = BeautifulSoup(resp.text, 'html.parser')

    sector_links = soup.select('a[href*="/sise/sise_group"]')
    for link in sector_links:
        text = link.get_text(strip=True)
        if text and not any(kw in text for kw in ['PER', 'PBR', '차트', '업종']):
            return text

    _delay()
    return ''


# ── 업종 등락률 크롤링 (동적 테마 가중치용) ──

def crawl_sector_performance():
    """네이버 증권 업종별 등락률 크롤링

    Returns:
        dict: { '반도체': 2.5, 'AI': 1.3, ... } (등락률 %)
    """
    resp = _request_with_retry(NAVER_SECTOR_RISE_URL)
    if resp is None:
        return {}

    soup = BeautifulSoup(resp.text, 'html.parser')
    sector_perf = {}

    rows = soup.select('table.type_1 tr')
    for row in rows:
        cols = row.select('td')
        if len(cols) < 2:
            continue

        name_tag = cols[0].select_one('a')
        if not name_tag:
            continue

        name = name_tag.get_text(strip=True)
        change_text = cols[1].get_text(strip=True).replace('%', '').replace('+', '')

        try:
            change_rate = float(change_text)
            sector_perf[name] = change_rate
        except (ValueError, TypeError):
            continue

    logger.info(f"  업종 등락률: {len(sector_perf)}개 업종 수집")
    return sector_perf


# ── 증권사 리포트 크롤링 ──

def crawl_analyst_report(ticker):
    """단일 종목의 최근 증권사 리포트 크롤링

    Returns:
        list[dict]: [{'broker': str, 'title': str, 'opinion': str, 'target_price': int, 'date': str}]
    """
    url = NAVER_RESEARCH_URL.format(ticker=ticker)
    resp = _request_with_retry(url)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    reports = []

    rows = soup.select('table.type_1 tr')
    for row in rows:
        if len(reports) >= 5:
            break

        cols = row.select('td')
        if len(cols) < 5:
            continue

        title_tag = cols[1].select_one('a')
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        broker = cols[0].get_text(strip=True)
        opinion = cols[2].get_text(strip=True)
        target_text = cols[3].get_text(strip=True).replace(',', '')
        date = cols[4].get_text(strip=True)

        target_price = 0
        try:
            target_price = int(re.sub(r'[^\d]', '', target_text))
        except (ValueError, TypeError):
            pass

        if title:
            reports.append({
                'broker': broker,
                'title': title,
                'opinion': opinion,
                'target_price': target_price,
                'date': date,
            })

    return reports


def crawl_analyst_reports_for_tickers(tickers):
    """복수 종목의 증권사 리포트 일괄 크롤링"""
    report_map = {}
    total = len(tickers)

    for idx, ticker in enumerate(tickers):
        try:
            reports = crawl_analyst_report(ticker)
            report_map[ticker] = reports
            if (idx + 1) % 20 == 0:
                logger.info(f"  리포트 수집 진행: {idx + 1}/{total}")
        except Exception as e:
            logger.warning(f"  리포트 크롤링 실패 ({ticker}): {e}")
            report_map[ticker] = []

        _delay()

    return report_map
