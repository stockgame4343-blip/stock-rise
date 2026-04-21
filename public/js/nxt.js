/**
 * 넥스트장(NXT) 일별 스냅샷 조회 페이지
 * - 정적 JSON 읽기: /data/nxt/index.json → 스냅샷 파일 → 테이블 렌더
 * - 하루 1개 파일 (YYYYMMDD.json) — 같은 날 여러 번 수집되어도 overwrite
 * - 탭: 상승 TOP 20 / 하락 TOP 20 전환
 * - 네비게이션: 이전/다음 날짜 (리포트와 동일 스타일)
 */
(function () {
    var DAYS_KO = ['일', '월', '화', '수', '목', '금', '토'];

    var state = {
        snapshots: [],   // [{file, date, collected_at, last_updated, session}, ...] 최신순
        idx: 0,          // 현재 보는 스냅샷 인덱스
        side: 'gainers', // 'gainers' | 'losers'
        current: null,   // 로드된 스냅샷 객체
    };

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
    var $colChangeHeader = document.getElementById('colChangeHeader');

    // ── 유틸 ──
    function formatNumber(n) {
        if (n == null) return '-';
        return Math.round(n).toLocaleString('ko-KR');
    }
    function formatChange(r) {
        // nxtChangeRate 있으면 (postmarket + KRX 종가 매칭) NXT 세션 한정 변동 우선
        var hasNxt = r.nxtChangeRate !== undefined && r.nxtChangeRate !== null;
        var rate = hasNxt ? r.nxtChangeRate : r.changeRate;
        var change = hasNxt ? r.nxtChange : r.change;
        var cls = rate >= 0 ? 'cell-change--up' : 'cell-change--down';
        var sign = rate >= 0 ? '+' : '';
        var changeStr = sign + formatNumber(change);
        var rateStr = sign + rate.toFixed(2) + '%';
        return '<span class="' + cls + '">' + changeStr + '<br>' + rateStr + '</span>';
    }
    function formatTradingValue(v) {
        if (!v) return '-';
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

    // ── 렌더링 ──
    function renderTable() {
        if (!state.current) {
            $body.innerHTML = '';
            return;
        }
        var list = (state.current[state.side] || []);
        if (list.length === 0) {
            $body.innerHTML = '<tr><td colspan="6" class="cell-empty">데이터 없음</td></tr>';
            return;
        }

        var html = '';
        list.forEach(function (r, i) {
            var detailUrl = 'https://finance.naver.com/item/main.naver?code=' + r.ticker;
            html += '<tr>';
            html += '<td class="cell-rank">' + (i + 1) + '</td>';
            html += '<td class="cell-name"><div class="cell-name__wrap">' +
                '<a href="' + detailUrl + '" target="_blank" rel="noopener" class="cell-name__link">' + r.name + '</a>' +
                '<span class="cell-name__market">' + (r.market || 'NXT') + '</span>' +
                '</div></td>';
            html += '<td class="cell-price">' + formatNumber(r.price) + '</td>';
            html += '<td class="cell-change">' + formatChange(r) + '</td>';
            html += '<td class="cell-volume">' + formatTradingValue(r.tradingValue) + '</td>';
            html += '<td class="cell-reason">' +
                (r.reason ? '<span class="theme-tag">' + r.reason + '</span>' : '<span class="cell-reason__text">-</span>') +
                '</td>';
            html += '</tr>';
        });
        $body.innerHTML = html;
    }

    function renderSnapInfo() {
        var entry = state.snapshots[state.idx];
        var dateStr = entryDate(entry);
        $snapDisplay.textContent = dateStr ? formatDateKorean(dateStr) : '-';

        // 리포트와 동일: idx===0 이면 오늘, 아니면 과거
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

    function renderColChangeHeader() {
        if (!$colChangeHeader) return;
        var snap = state.current;
        if (snap && snap.nxtChangeEnriched) {
            $colChangeHeader.textContent = 'NXT 변동';
            $colChangeHeader.title = '본장 종가 대비 NXT 애프터마켓 변동';
        } else if (snap && snap.session === 'premarket') {
            $colChangeHeader.textContent = 'NXT 변동';
            $colChangeHeader.title = '전일 종가 대비 NXT 프리마켓 변동';
        } else {
            $colChangeHeader.textContent = '전일대비';
            $colChangeHeader.removeAttribute('title');
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
                state.current = data;
                state.idx = idx;
                $loading.style.display = 'none';
                renderSnapInfo();
                renderColChangeHeader();
                renderTable();
            });
    }

    function init() {
        $loading.style.display = 'block';

        loadIndex()
            .then(function (list) {
                state.snapshots = Array.isArray(list) ? list : [];
                if (state.snapshots.length === 0) {
                    // index 없어도 latest.json 단독 시도
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

    init();
})();
