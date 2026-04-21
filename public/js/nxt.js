/**
 * 넥스트장(NXT) 일별 스냅샷 조회 페이지
 * - 정적 JSON 읽기: /data/nxt/index.json → 스냅샷 파일 → 테이블 렌더
 * - 하루 1개 파일 (YYYYMMDD.json) — 같은 날 여러 번 수집되어도 overwrite
 * - 탭: 상승 TOP 20 / 하락 TOP 20 전환
 * - 네비게이션: 이전/다음 날짜 (리포트와 동일 스타일)
 * - 정렬: 컬럼 헤더 클릭 → 해당 컬럼 기준 desc/asc 토글
 */
(function () {
    var DAYS_KO = ['일', '월', '화', '수', '목', '금', '토'];
    var RATINGS_KEY = 'stock-ratings';   // 대시보드와 동일 키 — 평가/제외/메모 공유
    var _syncTimer = null;
    var _memoTicker = null;

    var state = {
        snapshots: [],   // [{file, date, collected_at, last_updated, session}, ...] 최신순
        idx: 0,          // 현재 보는 스냅샷 인덱스
        side: 'gainers', // 'gainers' | 'losers'
        current: null,   // 로드된 스냅샷 객체
        sort: {          // 정렬 상태 (null 이면 기본: 변동률)
            key: null,   // 'price' | 'nxtChangeRate' | 'changeRate' | 'tradingValue' | 'krxTradingValue' | 'marketCap' | 'sector'
            dir: 'desc', // 'desc' | 'asc'
        },
    };

    // 문자열 정렬 컬럼
    var STRING_COLS = { sector: true, themes: true };

    // 컬럼별 실제 비교 값 (r[key] 대신 파생값이 필요한 경우)
    function sortValue(r, key) {
        if (key === 'themes') {
            return (r.themes && r.themes[0]) || '';
        }
        return r[key];
    }

    // DOM
    var $body = document.getElementById('nxtBody');
    var $loading = document.getElementById('loading');
    var $message = document.getElementById('message');
    var $snapDisplay = document.getElementById('snapDisplay');
    var $snapBadge = document.getElementById('snapBadge');
    var $snapPrev = document.getElementById('snapPrev');
    var $snapNext = document.getElementById('snapNext');
    var $themeToggle = document.getElementById('themeToggle');
    var $lastUpdated = document.getElementById('lastUpdated');
    var $tabs = document.querySelectorAll('.tab[data-side]');
    var $sortHeaders = document.querySelectorAll('.sortable[data-sort]');
    var $memoModal = document.getElementById('memoModal');
    var $memoModalClose = document.getElementById('memoModalClose');
    var $memoModalTitle = document.getElementById('memoModalTitle');
    var $memoTextarea = document.getElementById('memoTextarea');
    var $memoSave = document.getElementById('memoSave');
    var $memoDelete = document.getElementById('memoDelete');

    // ── 유틸 ──
    function formatNumber(n) {
        if (n == null) return '-';
        return Math.round(n).toLocaleString('ko-KR');
    }
    function formatChangeCell(rate, change) {
        // 대시보드 전일대비와 동일 포맷: ▲+1,560 / (+30.00%)
        if (rate == null) return '<span class="cell-empty">-</span>';
        var cls = rate >= 0 ? 'cell-change--up' : 'cell-change--down';
        var sign = rate >= 0 ? '+' : '';
        var arrow = rate > 0 ? '\u25B2' : (rate < 0 ? '\u25BC' : '');
        var line1 = change != null
            ? (arrow + sign + formatNumber(change))
            : (arrow + sign + rate.toFixed(2) + '%');
        var rateStr = '(' + sign + rate.toFixed(2) + '%)';
        return '<span class="' + cls + '">' + line1 +
            (change != null ? ('<br><span class="change-rate">' + rateStr + '</span>') : '') +
            '</span>';
    }
    function formatKrw(v) {
        if (v == null || !v) return '-';
        if (v >= 1e12) return (v / 1e12).toFixed(1) + '조';
        if (v >= 1e8) return (v / 1e8).toFixed(0) + '억';
        if (v >= 1e4) return (v / 1e4).toFixed(0) + '만';
        return formatNumber(v);
    }
    function formatDateKorean(ds) {
        // "20260421" → "4월 21일 (화)"
        if (!ds || ds.length < 8) return '-';
        var y = ds.substring(0, 4);
        var m = parseInt(ds.substring(4, 6), 10);
        var d = parseInt(ds.substring(6, 8), 10);
        var dt = new Date(+y, m - 1, +d);
        return m + '월 ' + d + '일 (' + DAYS_KO[dt.getDay()] + ')';
    }
    function entryDate(entry) {
        if (!entry) return '';
        if (entry.date) return entry.date;
        var f = entry.file || '';
        var stem = f.replace('.json', '');
        return stem.indexOf('_') >= 0 ? stem.split('_')[0] : stem;
    }
    function htmlEscape(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
    // 대시보드(table.js) 와 동일: 괄호 속 부연 제거 + 12자 커트
    function shortenTheme(name, maxLen) {
        if (!name) return name;
        maxLen = maxLen || 12;
        var short = name.replace(/\(.*?\)/g, '').trim();
        if (!short) return name;
        if (short.length > maxLen) short = short.substring(0, maxLen) + '…';
        return short;
    }

    // ── 별점/제외/메모 (대시보드 app.js + table.js 와 동일 동작) ──
    function getRatings() {
        try { return JSON.parse(localStorage.getItem(RATINGS_KEY) || '{}'); }
        catch (e) { return {}; }
    }
    function saveRatings(ratings) {
        localStorage.setItem(RATINGS_KEY, JSON.stringify(ratings));
        if (_syncTimer) clearTimeout(_syncTimer);
        _syncTimer = setTimeout(syncToServer, 3000);
    }
    function syncToServer() {
        fetch('/api/sync-ratings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(getRatings()),
        }).catch(function () {});
    }
    function loadFromServer() {
        if (Object.keys(getRatings()).length > 0) return Promise.resolve();
        return fetch('/api/sync-ratings')
            .then(function (r) { return r.json(); })
            .then(function (s) {
                if (s && Object.keys(s).length > 0) {
                    localStorage.setItem(RATINGS_KEY, JSON.stringify(s));
                }
            })
            .catch(function () {});
    }
    function miniIndicatorsHtml(ticker, ratings) {
        var rating = ratings[ticker] || {};
        var stars = rating.stars || 0;
        var excluded = rating.excluded || false;
        var hasMemo = rating.memo ? true : false;
        if (!(stars > 0 || excluded || hasMemo)) return '';
        var html = '<span class="mini-indicators">';
        if (stars > 0) html += '<span class="mini-star">★' + stars + '</span>';
        if (excluded) html += '<span class="mini-exclude">✕</span>';
        if (hasMemo) html += '<span class="mini-memo">✎</span>';
        html += '</span>';
        return html;
    }
    function starRatingHtml(ticker, ratings) {
        var rating = ratings[ticker] || {};
        var stars = rating.stars || 0;
        var excluded = rating.excluded || false;
        var hasMemo = rating.memo ? true : false;
        var html = '<span class="ctrl-wrap">';
        html += '<button class="ctrl-toggle" type="button" data-ticker="' + ticker + '" aria-label="평가">⋯</button>';
        html += '<div class="float-controls" data-ticker="' + ticker + '">';
        html += '<span class="star-rating" data-ticker="' + ticker + '">';
        for (var i = 1; i <= 5; i++) {
            html += '<span class="star' + (i <= stars ? ' star--active' : '') +
                '" data-star="' + i + '">★</span>';
        }
        html += '</span>';
        html += '<button class="exclude-btn' + (excluded ? ' exclude-btn--active' : '') +
            '" data-ticker="' + ticker + '" title="제외">✕</button>';
        html += '<button class="memo-btn' + (hasMemo ? ' memo-btn--has' : '') +
            '" data-ticker="' + ticker + '" title="메모">✎</button>';
        html += '</div>';
        html += '</span>';
        return html;
    }

    // ── 테마 토글 ──
    function currentTheme() {
        return document.documentElement.getAttribute('data-theme') || 'dark';
    }
    function applyTheme(theme) {
        if (theme === 'light') document.documentElement.setAttribute('data-theme', 'light');
        else document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme', theme);
        renderThemeIcon();
    }
    function renderThemeIcon() {
        var isDark = currentTheme() === 'dark';
        $themeToggle.innerHTML = isDark
            ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
            : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
    }
    if ($themeToggle) {
        renderThemeIcon();
        $themeToggle.addEventListener('click', function () {
            applyTheme(currentTheme() === 'dark' ? 'light' : 'dark');
        });
    }

    // ── 정렬 ──
    function getSortedList() {
        if (!state.current) return [];
        var list = (state.current[state.side] || []).slice();
        var key = state.sort.key;
        if (!key) return list; // 기본: 서버 정렬 유지 (변동률 desc)

        var dir = state.sort.dir === 'asc' ? 1 : -1;
        var isString = !!STRING_COLS[key];
        list.sort(function (a, b) {
            var va = sortValue(a, key);
            var vb = sortValue(b, key);
            if (isString) {
                va = va || '';
                vb = vb || '';
                if (va === vb) return 0;
                return (va < vb ? -1 : 1) * dir;
            }
            // 숫자: null/undefined 를 최하위로 (desc 기준)
            var aMissing = va == null;
            var bMissing = vb == null;
            if (aMissing && bMissing) return 0;
            if (aMissing) return 1;
            if (bMissing) return -1;
            return (va - vb) * dir;
        });
        return list;
    }

    function renderSortArrows() {
        $sortHeaders.forEach(function (th) {
            var key = th.getAttribute('data-sort');
            var icon = th.querySelector('.sort-icon');
            if (!icon) return;
            if (state.sort.key === key) {
                icon.innerHTML = state.sort.dir === 'asc' ? '&#9650;' : '&#9660;';
                icon.classList.add('sort-icon--active');
            } else {
                icon.innerHTML = '&#9660;';
                icon.classList.remove('sort-icon--active');
            }
        });
    }

    // ── 렌더링 ──
    function renderTable() {
        if (!state.current) {
            $body.innerHTML = '';
            return;
        }
        var list = getSortedList();
        if (list.length === 0) {
            $body.innerHTML = '<tr><td colspan="11" class="cell-empty">데이터 없음</td></tr>';
            return;
        }

        var ratings = getRatings();
        var html = '';
        list.forEach(function (r, i) {
            var detailUrl = 'https://finance.naver.com/item/main.naver?code=' + r.ticker;
            // 대시보드와 동일 규칙: primary 1개 + 보조 1개(있고 primary와 다를 때만)
            var themesHtml = '<span class="cell-empty">-</span>';
            if (r.themes && r.themes.length) {
                var primary = shortenTheme(r.themes[0]);
                var sub = r.themes.length > 1 ? shortenTheme(r.themes[1]) : '';
                if (sub && sub === primary) sub = '';
                var parts = ['<span class="theme-tag">' + htmlEscape(primary) + '</span>'];
                if (sub) parts.push('<span class="theme-tag theme-tag--sub">' + htmlEscape(sub) + '</span>');
                themesHtml = parts.join('');
            }
            // NXT 변동 (nxtChangeRate/nxtChange) — 없으면 '-'
            var nxtChangeHtml = formatChangeCell(
                r.nxtChangeRate != null ? r.nxtChangeRate : null,
                r.nxtChange != null ? r.nxtChange : null
            );
            // 전일대비 (changeRate/change) — NXT API 기본
            var prevChangeHtml = formatChangeCell(r.changeRate, r.change);

            // 모바일 전용 meta-compact 라인 (PC 에선 숨김)
            // 데스크톱 컬럼 순서와 동일: 시장 · 섹터 · 시총 · NXT거래 · 거래(총합) · 전일%
            var metaParts = [];
            if (r.market) metaParts.push(htmlEscape(r.market));
            if (r.sector) metaParts.push(htmlEscape(r.sector));
            if (r.marketCap) metaParts.push('시총 ' + formatKrw(r.marketCap));
            if (r.tradingValue) metaParts.push('NXT ' + formatKrw(r.tradingValue));
            if (r.totalTradingValue) metaParts.push('거래 ' + formatKrw(r.totalTradingValue));
            if (r.changeRate != null) {
                var prevSign = r.changeRate >= 0 ? '+' : '';
                metaParts.push('전일 ' + prevSign + r.changeRate.toFixed(2) + '%');
            }
            var metaCompact = metaParts.join(' &middot; ');

            html += '<tr>';
            html += '<td class="cell-rank">' + (i + 1) + '</td>';
            html += '<td class="cell-name"><div class="cell-name__wrap">' +
                '<a href="' + detailUrl + '" target="_blank" rel="noopener" class="cell-name__link">' + htmlEscape(r.name) + '</a>' +
                miniIndicatorsHtml(r.ticker, ratings) +
                '<span class="cell-name__market">' + htmlEscape(r.market || 'NXT') + '</span>' +
                starRatingHtml(r.ticker, ratings) +
                '</div></td>';
            html += '<td class="cell-price">' + formatNumber(r.price) + '</td>';
            html += '<td class="cell-change">' + nxtChangeHtml + '</td>';
            html += '<td class="cell-change cell-change-prev">' + prevChangeHtml + '</td>';
            // "NXT 거래대금" = NXT 세션만, "거래대금" = NXT + 본장 총합
            html += '<td class="cell-volume">' + formatKrw(r.tradingValue) + '</td>';
            html += '<td class="cell-volume">' + formatKrw(r.totalTradingValue) + '</td>';
            html += '<td class="cell-volume">' + formatKrw(r.marketCap) + '</td>';
            html += '<td class="cell-sector">' + (r.sector ? htmlEscape(r.sector) : '<span class="cell-empty">-</span>') + '</td>';
            // 모바일 카드 순서: meta 라인 먼저, 테마 태그 나중 (대시보드와 동일)
            html += '<td class="cell-meta-compact">' + metaCompact + '</td>';
            html += '<td class="cell-themes">' + themesHtml + '</td>';
            html += '</tr>';
        });
        $body.innerHTML = html;
    }

    function renderSnapInfo() {
        var entry = state.snapshots[state.idx];
        var dateStr = entryDate(entry);
        $snapDisplay.textContent = dateStr ? formatDateKorean(dateStr) : '-';

        if (state.idx === 0) {
            $snapBadge.textContent = '오늘';
            $snapBadge.className = 'date-badge';
        } else {
            $snapBadge.textContent = '과거';
            $snapBadge.className = 'date-badge date-badge--past';
        }
        $snapBadge.style.display = '';
        $snapPrev.disabled = state.idx >= state.snapshots.length - 1;
        $snapNext.disabled = state.idx <= 0;

        // 상단 바: 마지막 업데이트 시각
        if ($lastUpdated) {
            var lu = (state.current && state.current.last_updated)
                || (entry && entry.last_updated) || '';
            if (!lu && state.current && state.current.collected_at) {
                var d = new Date(state.current.collected_at);
                var hh = String(d.getHours()).padStart(2, '0');
                var mm = String(d.getMinutes()).padStart(2, '0');
                lu = hh + ':' + mm;
            }
            $lastUpdated.textContent = lu ? (lu + ' 수집') : '';
        }
    }

    function showMessage(msg) {
        $loading.style.display = 'none';
        $message.style.display = 'block';
        $message.textContent = msg;
    }

    // ── 데이터 로드 ──
    function loadIndex() {
        return fetch('/data/nxt/index.json', { cache: 'no-cache' })
            .then(function (r) {
                if (!r.ok) throw new Error('index.json 없음');
                return r.json();
            });
    }

    function loadSnapshot(idx) {
        $loading.style.display = 'block';
        $message.style.display = 'none';
        var entry = state.snapshots[idx];
        var url = entry ? ('/data/nxt/' + entry.file) : '/data/nxt/latest.json';
        return fetch(url, { cache: 'no-cache' })
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                // 총 거래대금 = NXT + 본장(KRX). "거래대금" 컬럼 표시 및 정렬 기준
                ['gainers', 'losers'].forEach(function (side) {
                    (data[side] || []).forEach(function (r) {
                        var nxt = r.tradingValue || 0;
                        var krx = r.krxTradingValue || 0;
                        if (nxt || krx) r.totalTradingValue = nxt + krx;
                    });
                });
                state.current = data;
                state.idx = idx;
                $loading.style.display = 'none';
                renderSnapInfo();
                renderSortArrows();
                renderTable();
            });
    }

    // ── 이벤트 위임: tbody 클릭 (별점/제외/메모/ctrl-toggle) ──
    function onBodyClick(e) {
        var toggleBtn = e.target.closest('.ctrl-toggle');
        if (toggleBtn) {
            var wrap = toggleBtn.closest('.ctrl-wrap');
            if (!wrap) return;
            var wasOpen = wrap.classList.contains('is-open');
            document.querySelectorAll('.ctrl-wrap.is-open').forEach(function (w) {
                if (w !== wrap) w.classList.remove('is-open');
            });
            if (!wasOpen) wrap.classList.add('is-open');
            else wrap.classList.remove('is-open');
            return;
        }
        var starEl = e.target.closest('.star');
        if (starEl) {
            var starRating = starEl.closest('.star-rating');
            if (!starRating) return;
            var ticker = starRating.getAttribute('data-ticker');
            var starNum = parseInt(starEl.getAttribute('data-star'), 10);
            if (!ticker || isNaN(starNum)) return;
            var ratings = getRatings();
            if (!ratings[ticker]) ratings[ticker] = {};
            ratings[ticker].stars = (ratings[ticker].stars === starNum) ? 0 : starNum;
            saveRatings(ratings);
            renderTable();
            return;
        }
        var excludeBtn = e.target.closest('.exclude-btn');
        if (excludeBtn) {
            var t = excludeBtn.getAttribute('data-ticker');
            if (!t) return;
            var rs = getRatings();
            if (!rs[t]) rs[t] = {};
            rs[t].excluded = !rs[t].excluded;
            saveRatings(rs);
            renderTable();
            return;
        }
        var memoBtn = e.target.closest('.memo-btn');
        if (memoBtn) {
            var mt = memoBtn.getAttribute('data-ticker');
            if (mt) openMemo(mt);
            return;
        }
    }

    // ── 메모 모달 ──
    function findStockName(ticker) {
        if (!state.current) return '';
        var all = (state.current.gainers || []).concat(state.current.losers || []);
        for (var i = 0; i < all.length; i++) {
            if (all[i].ticker === ticker) return all[i].name || '';
        }
        return '';
    }
    function openMemo(ticker) {
        _memoTicker = ticker;
        var rd = getRatings()[ticker] || {};
        $memoModalTitle.textContent = (findStockName(ticker) || ticker) + ' 메모';
        $memoTextarea.value = rd.memo || '';
        $memoModal.style.display = 'flex';
        $memoTextarea.focus();
    }
    function closeMemo() {
        $memoModal.style.display = 'none';
        _memoTicker = null;
    }
    function saveMemo() {
        if (!_memoTicker) return;
        var rs = getRatings();
        if (!rs[_memoTicker]) rs[_memoTicker] = {};
        var text = $memoTextarea.value.trim();
        if (text) rs[_memoTicker].memo = text;
        else delete rs[_memoTicker].memo;
        saveRatings(rs);
        closeMemo();
        renderTable();
    }
    function deleteMemo() {
        if (!_memoTicker) return;
        var rs = getRatings();
        if (rs[_memoTicker]) {
            delete rs[_memoTicker].memo;
            saveRatings(rs);
        }
        closeMemo();
        renderTable();
    }

    function init() {
        $loading.style.display = 'block';
        // 서버 저장본이 있으면 localStorage 미리 채우기 (병렬, 완료 시 재렌더)
        loadFromServer().then(function () {
            if (state.current) renderTable();
        });

        loadIndex()
            .then(function (list) {
                state.snapshots = Array.isArray(list) ? list : [];
                if (state.snapshots.length === 0) {
                    return loadSnapshot(0).catch(function () {
                        showMessage('아직 수집된 NXT 스냅샷이 없습니다.');
                    });
                }
                return loadSnapshot(0);
            })
            .catch(function (err) {
                showMessage('데이터 로드 실패: ' + (err && err.message ? err.message : ''));
            });
    }

    // ── 이벤트 바인딩 ──
    $tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
            $tabs.forEach(function (t) { t.classList.remove('active'); });
            tab.classList.add('active');
            state.side = tab.getAttribute('data-side');
            renderTable();
        });
    });

    $sortHeaders.forEach(function (th) {
        th.addEventListener('click', function () {
            var key = th.getAttribute('data-sort');
            if (!key) return;
            if (state.sort.key === key) {
                // 같은 컬럼 재클릭 → 방향 토글, 두 번 더 클릭하면 정렬 해제
                if (state.sort.dir === 'desc') {
                    state.sort.dir = 'asc';
                } else {
                    state.sort = { key: null, dir: 'desc' };
                }
            } else {
                state.sort = { key: key, dir: 'desc' };
            }
            renderSortArrows();
            renderTable();
        });
    });

    $snapPrev.addEventListener('click', function () {
        if (state.idx < state.snapshots.length - 1) {
            loadSnapshot(state.idx + 1).catch(function () {});
        }
    });
    $snapNext.addEventListener('click', function () {
        if (state.idx > 0) {
            loadSnapshot(state.idx - 1).catch(function () {});
        }
    });

    // tbody 이벤트 위임 (별점/제외/메모/ctrl-toggle)
    $body.addEventListener('click', onBodyClick);

    // 메모 모달
    if ($memoModalClose) $memoModalClose.addEventListener('click', closeMemo);
    if ($memoModal) $memoModal.addEventListener('click', function (e) {
        if (e.target === $memoModal) closeMemo();
    });
    if ($memoSave) $memoSave.addEventListener('click', saveMemo);
    if ($memoDelete) $memoDelete.addEventListener('click', deleteMemo);

    // 바깥 탭 → 열려 있는 ctrl-wrap 패널 닫기 (모바일)
    document.addEventListener('click', function (e) {
        if (!e.target.closest('.ctrl-wrap')) {
            document.querySelectorAll('.ctrl-wrap.is-open').forEach(function (w) {
                w.classList.remove('is-open');
            });
        }
    });

    init();
})();
