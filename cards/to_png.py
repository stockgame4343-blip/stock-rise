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

def add_png_metadata(png_path, title, description, keywords=''):
    """PNG tEXt/iTXt 청크에 메타데이터 삽입.

    구글 이미지 검색·SNS 공유 시 활용. PNG 표준 키:
      Title, Description, Author, Source, Software, Keywords, Copyright
    """
    try:
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo
    except ImportError:
        log.warning("PIL 미설치 — PNG 메타 스킵")
        return False

    try:
        img = Image.open(png_path)
        info = PngInfo()
        info.add_text("Title", title)
        info.add_text("Description", description)
        info.add_text("Author", "라이즈와이 RiseWhy")
        info.add_text("Source", "https://stock-rise.vercel.app/cards.html")
        info.add_text("Software", "StockRise cards generator")
        info.add_text("Copyright", "© 라이즈와이 RiseWhy")
        if keywords:
            info.add_text("Keywords", keywords)
        img.save(png_path, "PNG", pnginfo=info, optimize=True)
        return True
    except Exception as exc:
        log.warning("PNG 메타 추가 실패 (%s): %s", png_path, exc)
        return False


def verify_png(png_path):
    """PNG 강력 검증.

    1) 1080×1080 정사각형
    2) 4 가장자리 (위·아래·좌·우) 행/열 전체에 흰 픽셀 0건
    3) 어떤 행이든 **연속** 흰 픽셀 런이 가로 폭의 절반 이상 0건 (배경 짤림 차단)
       — 흰 글자(180px 굵은 종목명 등)는 글리프 사이 공백으로 짧은 런만 생기지만,
         배경이 잘려 흰 띠가 생기면 수백 px 연속 → 둘을 명확히 구분

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
    pixels = img.load()  # 픽셀 직접 접근 — getpixel 보다 빠름

    # (1) 4 가장자리 — 8픽셀 step 으로 샘플
    edges = []
    for x in range(0, w, 8):
        edges.append((x, 0))
        edges.append((x, h - 1))
    for y in range(0, h, 8):
        edges.append((0, y))
        edges.append((w - 1, y))
    edge_whites = [p for p in edges if pixels[p[0], p[1]] == WHITE]
    if edge_whites:
        return False, f"가장자리 흰 픽셀 {len(edge_whites)}개 (예: {edge_whites[:3]})"

    # (2) 행 단위 연속 흰 런 검사 — 절반 폭(540px) 이상 연속이면 배경 짤림
    max_run_threshold = w // 2  # 540px
    bad_rows = []
    for y in range(h):
        run = 0
        max_run = 0
        for x in range(w):
            if pixels[x, y] == WHITE:
                run += 1
                if run > max_run:
                    max_run = run
            else:
                run = 0
        if max_run > max_run_threshold:
            bad_rows.append((y, max_run))
            if len(bad_rows) >= 3:
                break  # 조기 종료 — 3개만 보여줘도 충분
    if bad_rows:
        sample = ', '.join(f'y={y} run={r}px' for y, r in bad_rows)
        return False, f"흰 띠(연속 흰 런 {max_run_threshold}px 초과) — {sample}"

    return True, f"OK ({img.size})"
