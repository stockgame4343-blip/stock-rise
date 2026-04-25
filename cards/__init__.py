"""StockRise — 인스타그램 카드뉴스 일일 자동 생성 모듈.

상위 모듈:
    config       — 모든 임계값/상수/검열 패턴
    text_synth   — 룰 기반 텍스트 합성 + 검열 필터
    data_loader  — public/data/*.json → 카드별 입력 dict
    us_indices   — yfinance: S&P/NASDAQ/DOW (Phase 3)
    kr_indices   — pykrx: KOSPI/KOSDAQ (Phase 3)
    renderer     — 템플릿 + 데이터 → HTML (Phase 2)
    to_png       — playwright 1080x1080 캡처 (Phase 3)
    generate     — 진입점 (Phase 4)
"""
