"""네이버 증권 뉴스/섹터 크롤링"""
import random
import time
import logging

import requests
from bs4 import BeautifulSoup

from config import (
    USER_AGENTS,
    REQUEST_DELAY_MIN, REQUEST_DELAY_MAX,
)

logger = logging.getLogger(__name__)

# 뉴스는 iframe 내부 URL을 직접 조회해야 한다
NAVER_NEWS_IFRAME_URL = 'https://finance.naver.com/item/news_news.naver?code={ticker}&page=&clusterId='
NAVER_ITEM_MAIN_URL = 'https://finance.naver.com/item/main.naver?code={ticker}'


def _get_headers():
    """랜덤 User-Agent 헤더 반환"""
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Referer': 'https://finance.naver.com/',
    }


def _request_with_retry(url, max_retries=3, timeout=10):
    """재시도 로직이 포함된 HTTP GET"""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=_get_headers(), timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(REQUEST_DELAY_MIN)
            else:
                logger.warning(f"  요청 실패 ({max_retries}회): {url}")
    return None


def _delay():
    """요청 간 랜덤 딜레이"""
    time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))


def crawl_news(ticker, max_articles=10):
    """단일 종목의 최근 뉴스 크롤링 (제목, 링크, 출처)
    네이버 증권 뉴스는 iframe 안에 있으므로 iframe URL을 직접 조회한다.
    """
    url = NAVER_NEWS_IFRAME_URL.format(ticker=ticker)
    resp = _request_with_retry(url)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    articles = []
    seen_titles = set()

    # table.type5 안의 뉴스 행 파싱
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


def crawl_sector(ticker):
    """단일 종목의 업종/섹터 정보 크롤링
    네이버 종목 메인 페이지에서 업종 링크(sise_group)를 찾는다.
    """
    url = NAVER_ITEM_MAIN_URL.format(ticker=ticker)
    resp = _request_with_retry(url)
    if resp is None:
        return ''

    soup = BeautifulSoup(resp.text, 'html.parser')

    # 업종 링크: <a href="/sise/sise_group_detail.naver?...">반도체와반도체장비</a>
    sector_links = soup.select('a[href*="/sise/sise_group"]')
    for link in sector_links:
        text = link.get_text(strip=True)
        # 업종명만 추출 (숫자나 'PER' 등이 포함된 것은 제외)
        if text and not any(kw in text for kw in ['PER', 'PBR', '차트', '업종']):
            return text

    _delay()
    return ''
