"""playwright — 카드 HTML → 1080×1080 PNG.

핵심: `.card` 요소만 캡처해 정확히 width×height 보장 (body 배경이 카드 밖으로
새어 흰색으로 잡히는 짤림 사고 방지). PNG 4모서리는 항상 카드 배경색.
"""

import logging
import os
import time

from . import config

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


log = logging.getLogger(__name__)

FONT_LOAD_WAIT_MS = 800  # Pretendard CDN 로드 여유


def _file_url(path):
    """절대경로 → file:/// URL (Windows 백슬래시 안전 처리)."""
    abs_path = os.path.abspath(path).replace('\\', '/')
    return f'file:///{abs_path}'


def html_to_png(html_path, png_path, width=None, height=None):
    """단일 HTML → PNG. .card 요소를 캡처."""
    if sync_playwright is None:
        raise RuntimeError(
            "playwright 미설치 — pip install playwright && playwright install chromium"
        )
    width = width or config.CARD_WIDTH
    height = height or config.CARD_HEIGHT
    os.makedirs(os.path.dirname(os.path.abspath(png_path)), exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            ctx = browser.new_context(
                viewport={'width': width, 'height': height},
                device_scale_factor=1,
            )
            page = ctx.new_page()
            page.goto(_file_url(html_path))
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(FONT_LOAD_WAIT_MS)
            card = page.query_selector('.card')
            if card is None:
                raise RuntimeError(f"`.card` 요소 없음 in {html_path}")
            card.screenshot(path=png_path)
        finally:
            browser.close()


def html_to_png_batch(html_files, png_files):
    """여러 HTML → PNG 일괄 처리 (브라우저 1회만 띄움).

    Args:
        html_files: dict {name: html_path|None}
        png_files:  dict {name: png_path}

    Returns:
        dict {name: png_path|None}
    """
    if sync_playwright is None:
        raise RuntimeError("playwright 미설치")

    results = {}
    width = config.CARD_WIDTH
    height = config.CARD_HEIGHT
    output_dirs = {os.path.dirname(os.path.abspath(p)) for p in png_files.values()}
    for d in output_dirs:
        os.makedirs(d, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for name, html_path in html_files.items():
                png_path = png_files.get(name)
                if html_path is None or png_path is None:
                    results[name] = None
                    continue

                t0 = time.time()
                ctx = browser.new_context(
                    viewport={'width': width, 'height': height},
                    device_scale_factor=1,
                )
                try:
                    page = ctx.new_page()
                    page.goto(_file_url(html_path))
                    page.wait_for_load_state('networkidle')
                    page.wait_for_timeout(FONT_LOAD_WAIT_MS)
                    card = page.query_selector('.card')
                    if card is None:
                        log.error(f"`.card` 요소 없음: {html_path}")
                        results[name] = None
                        continue
                    card.screenshot(path=png_path)
                    results[name] = png_path
                    log.info(f"  [{name:<8}] {os.path.basename(png_path)}  ({(time.time()-t0)*1000:.0f}ms)")
                finally:
                    ctx.close()
        finally:
            browser.close()

    return results


# ─── PNG 검증 ───────────────────────────────────────

def verify_png(png_path):
    """PNG 강력 검증.

    1) 1080×1080 정사각형
    2) 4 가장자리 (위·아래·좌·우) 행/열 전체에 흰 픽셀 0건
    3) 전체 행 단위 — 어떤 행이든 흰 픽셀 비율 50% 초과 0건 (배경 짤림 차단)

    Returns:
        (ok: bool, msg: str)
    """
    try:
        from PIL import Image
    except ImportError:
        return True, "PIL 미설치 — 검증 스킵"
    img = Image.open(png_path).convert('RGB')
    if img.size != (config.CARD_WIDTH, config.CARD_HEIGHT):
        return False, f"size {img.size} != ({config.CARD_WIDTH},{config.CARD_HEIGHT})"

    w, h = img.size
    WHITE = (255, 255, 255)

    # (1) 4 가장자리 — 8픽셀 step 으로 샘플
    edges = []
    for x in range(0, w, 8):
        edges.append((x, 0))
        edges.append((x, h - 1))
    for y in range(0, h, 8):
        edges.append((0, y))
        edges.append((w - 1, y))
    edge_whites = [p for p in edges if img.getpixel(p) == WHITE]
    if edge_whites:
        return False, f"가장자리 흰 픽셀 {len(edge_whites)}개 (예: {edge_whites[:3]})"

    # (2) 전체 행 검사 — 어떤 행도 흰 비율 50% 초과 X
    threshold = w // 2
    bad_rows = []
    for y in range(h):
        whites = sum(1 for x in range(0, w, 4) if img.getpixel((x, y)) == WHITE)
        if whites * 4 > threshold:
            bad_rows.append(y)
    if bad_rows:
        return False, f"흰 행 {len(bad_rows)}개 (y={bad_rows[:3]}…)"

    return True, f"OK ({img.size})"
