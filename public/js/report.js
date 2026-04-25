/**
 * 데일리 리포트 페이지 로직
 */
(function () {
    var DAYS_KO = ['일', '월', '화', '수', '목', '금', '토'];
    var THEME_KEY = 'theme';
    var RATINGS_KEY = 'stock-ratings';
    var _syncTimer = null;

    // 급등 → 조정 → 재반등 임계값 (backtest_pullback.py 결과 기반)
    //   peak=20  n=504 조합 중 breakout 68.7% / double_top 5.4% / fwd60 +14.6%
    var PEAK_PCT = 20;     // 급등 기준 (%)
    var DROP_PCT = 20;     // 조정 기준 (%)
    var REBOUND_PCT = 25;  // 재반등 기준 (%)

    var state = {
        dates: [],
        dateIndex: 0,
        allRankings: [],
        analysis: null,
        summaryHistory: [],
        cardsIndex: null,    // public/cards/index.json 캐시
        cardsList: [],       // 현재 날짜의 카드 배열
        cardsPage: 0,
        cardsModalIdx: 0,
    };

    var CARDS_PAGE_SIZE = 5;
    var CARDS_TYPE_LABEL = { pre: '장전', leader: '주도주', close: '장마감' };

    // 네이버 테마명 표시용 줄임 — 괄호 제거 + 길면 말줄임
    function shortenTheme(name, maxLen) {
        if (!name) return name;
        maxLen = maxLen || 12;
        // 괄호 내용 제거: "우주항공산업(누리호/인공위성 등)" → "우주항공산업"
        var short = name.replace(/\(.*?\)/g, '').trim();
        // 빈 문자열 방지
        if (!short) return name;
        // 길면 말줄임
        if (short.length > maxLen) short = short.substring(0, maxLen) + '…';
        return short;
    }

    // DOM
    var $reportTitle = document.getElementById('reportTitle');
    var $loading = document.getElementById('loading');
    var $message = document.getElementById('message');
    var $content = document.getElementById('reportContent');
    var $datePrev = document.getElementById('datePrev');
    var $dateNext = document.getElementById('dateNext');
    var $dateBadge = document.getElementById('dateBadge');
    var $lastUpdated = document.getElementById('lastUpdated');

    // ── 유틸 ──
    function formatDateKorean(ds) {
        var y = ds.substring(0, 4);
        var m = parseInt(ds.substring(4, 6), 10);
        var d = parseInt(ds.substring(6, 8), 10);
        var dt = new Date(+y, m - 1, +d);
        return m + '월 ' + d + '일 (' + DAYS_KO[dt.getDay()] + ')';
    }

    function formatNumber(n) {
        if (n == null) return '-';
        return n.toLocaleString('ko-KR');
    }

    function formatAmount(n) {
        // 대시보드/NXT 와 동일: 조/억/만 단위 + 콤마 없음
        if (n == null || n === 0) return '-';
        if (n >= 1e12) return (n / 1e12).toFixed(1) + '조';
        if (n >= 1e8) return Math.round(n / 1e8) + '억';
        if (n >= 1e4) return Math.round(n / 1e4) + '만';
        return formatNumber(n);
    }

    function daysSince(dateStr, currentDate) {
        if (!dateStr || dateStr.length < 8) return -1;
        var y1 = +currentDate.substring(0,4), m1 = +currentDate.substring(4,6)-1, d1 = +currentDate.substring(6,8);
        var y2 = +dateStr.substring(0,4), m2 = +dateStr.substring(4,6)-1, d2 = +dateStr.substring(6,8);
        return Math.round((new Date(y1,m1,d1) - new Date(y2,m2,d2)) / 86400000);
    }

    function showLoading(v) {
        $loading.style.display = v ? 'block' : 'none';
        $content.style.display = v ? 'none' : 'block';
    }
    function showMessage(msg) {
        $message.style.display = msg ? 'block' : 'none';
        $message.textContent = msg;
    }

    function filterGoodNews(newsList) {
        return newsList.filter(function (n) {
            return n.title.indexOf('서울데이터랩') === -1;
        });
    }

    // ── localStorage 레이팅 ──
    function getRatings() {
        try { return JSON.parse(localStorage.getItem(RATINGS_KEY) || '{}'); }
        catch (e) { return {}; }
    }
    function saveRatings(r) {
        localStorage.setItem(RATINGS_KEY, JSON.stringify(r));
        // 3초 디바운스 후 서버 동기화 (대시보드/NXT와 동일 패턴)
        if (_syncTimer) clearTimeout(_syncTimer);
        _syncTimer = setTimeout(syncToServer, 3000);
    }
    function syncToServer() {
        var ratings = getRatings();
        fetch('/api/sync-ratings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(ratings),
        }).catch(function () {});
    }
    function loadFromServer() {
        // 페이지 로드 시 서버 상태를 localStorage 로 덮어쓰기 (기기 간 동기화)
        return fetch('/api/sync-ratings')
            .then(function (r) { return r.json(); })
            .then(function (server) {
                if (server && typeof server === 'object') {
                    localStorage.setItem(RATINGS_KEY, JSON.stringify(server));
                }
            })
            .catch(function () {});
    }
    function controlsHtml(ticker, ratings) {
        var rd = ratings[ticker] || {};
        var stars = rd.stars || 0;
        var excluded = rd.excluded || false;
        var hasMemo = rd.memo ? true : false;
        var hasAny = stars > 0 || excluded || hasMemo;

        var html = '<span class="ctrl-wrap">';
        if (hasAny) {
            html += '<span class="mini-indicators">';
            if (stars > 0) html += '<span class="mini-star">\u2605' + stars + '</span>';
            if (excluded) html += '<span class="mini-exclude">\u2715</span>';
            if (hasMemo) html += '<span class="mini-memo">\u270E</span>';
            html += '</span>';
        }
        // 모바일 토글 버튼 (PC 에선 hover 로 열기 때문에 CSS 에서 숨김)
        html += '<button class="ctrl-toggle" type="button" data-ticker="' + ticker + '" aria-label="\uD3C9\uAC00">\u22EF</button>';
        html += '<div class="float-controls" data-ticker="' + ticker + '">';
        html += '<span class="star-rating" data-ticker="' + ticker + '">';
        for (var i = 1; i <= 5; i++) {
            html += '<span class="star' + (i <= stars ? ' star--active' : '') + '" data-star="' + i + '">\u2605</span>';
        }
        html += '</span>';
        html += '<button class="exclude-btn' + (excluded ? ' exclude-btn--active' : '') + '" data-ticker="' + ticker + '" title="\uC81C\uC678">\u2715</button>';
        html += '<button class="memo-btn' + (hasMemo ? ' memo-btn--has' : '') + '" data-ticker="' + ticker + '" title="\uBA54\uBAA8">\u270E</button>';
        html += '</div></span>';
        return html;
    }

    function refreshControlsUI(ticker) {
        var ratings = getRatings();
        var rd = ratings[ticker] || {};
        var stars = rd.stars || 0;
        var excluded = !!rd.excluded;
        var hasMemo = !!rd.memo;
        var hasAny = stars > 0 || excluded || hasMemo;

        document.querySelectorAll('.float-controls[data-ticker="' + ticker + '"]').forEach(function (fc) {
            fc.querySelectorAll('.star').forEach(function (s, i) {
                s.classList.toggle('star--active', i < stars);
            });
            var ex = fc.querySelector('.exclude-btn');
            if (ex) ex.classList.toggle('exclude-btn--active', excluded);
            var memo = fc.querySelector('.memo-btn');
            if (memo) memo.classList.toggle('memo-btn--has', hasMemo);

            var wrap = fc.closest('.ctrl-wrap');
            if (!wrap) return;
            var oldMini = wrap.querySelector('.mini-indicators');
            if (oldMini) oldMini.remove();
            if (hasAny) {
                var m = '<span class="mini-indicators">';
                if (stars > 0) m += '<span class="mini-star">\u2605' + stars + '</span>';
                if (excluded) m += '<span class="mini-exclude">\u2715</span>';
                if (hasMemo) m += '<span class="mini-memo">\u270E</span>';
                m += '</span>';
                fc.insertAdjacentHTML('beforebegin', m);
            }
        });
    }

    // 점수 레벨 텍스트
    function buzzLevel(v) {
        if (v >= 18) return '매우 많음';
        if (v >= 13) return '많음';
        if (v >= 8) return '보통';
        if (v >= 4) return '적음';
        return '거의 없음';
    }
    function qualityLevel(v) {
        if (v >= 20) return '매우 높음';
        if (v >= 15) return '높음';
        if (v >= 10) return '보통';
        if (v >= 5) return '낮음';
        return '매우 낮음';
    }
    function typeLevel(v) {
        if (v >= 25) return '핵심 이슈';
        if (v >= 15) return '보통 이슈';
        if (v >= 5) return '약한 이슈';
        return '미분류';
    }
    function turnoverLevel(v) {
        if (v >= 23) return '폭발적';
        if (v >= 18) return '매우 활발';
        if (v >= 12) return '활발';
        if (v >= 6) return '보통';
        return '평이';
    }
    // 대장점수 v3 레벨
    function tpLevel(v) {
        if (v >= 28) return '최강 테마';
        if (v >= 20) return '강한 테마';
        if (v >= 12) return '보통 테마';
        if (v >= 5) return '약한 테마';
        return '테마 미확인';
    }
    function tlLevel(v) {
        if (v >= 35) return '확실한 대장';
        if (v >= 25) return '유력 대장';
        if (v >= 15) return '중위권';
        if (v >= 8) return '추종주';
        return '미확인';
    }
    function tiLevel(v) {
        if (v >= 16) return '폭발적';
        if (v >= 12) return '매우 활발';
        if (v >= 8) return '활발';
        if (v >= 4) return '보통';
        return '평이';
    }

    // ── 테마 토글 (공통) ──
    var $themeToggle = document.getElementById('themeToggle');
    function applyThemeIcon() {
        var isDark = !document.documentElement.hasAttribute('data-theme');
        $themeToggle.innerHTML = isDark
            ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
            : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
    }
    function toggleTheme() {
        var isDark = !document.documentElement.hasAttribute('data-theme');
        if (isDark) {
            document.documentElement.setAttribute('data-theme', 'light');
            localStorage.setItem(THEME_KEY, 'light');
        } else {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem(THEME_KEY, 'dark');
        }
        applyThemeIcon();
    }
    $themeToggle.addEventListener('click', toggleTheme);
    applyThemeIcon();

    // ── 상세 모달 ──
    var $detailModal = document.getElementById('detailModal');
    var $detailModalTitle = document.getElementById('detailModalTitle');
    var $detailModalBody = document.getElementById('detailModalBody');
    var $detailModalClose = document.getElementById('detailModalClose');

    function openDetailModal(title, bodyHtml) {
        $detailModalTitle.textContent = title;
        $detailModalBody.innerHTML = bodyHtml;
        $detailModal.style.display = 'flex';
    }
    function closeDetailModal() {
        $detailModal.style.display = 'none';
    }

    // ── 날짜 뱃지 ──
    function updateDateBadge() {
        if (!$dateBadge) return;
        var isToday = state.dateIndex === 0;
        if (isToday) {
            $dateBadge.textContent = '오늘';
            $dateBadge.className = 'date-badge';
        } else {
            $dateBadge.textContent = '과거';
            $dateBadge.className = 'date-badge date-badge--past';
        }
    }

    // ── SVG 차트 빌더 ──
    function buildLineChart(values, labels, type) {
        if (!values || values.length < 2) return '';
        var w = 540, h = 160, padL = 52, padR = 40, padT = 20, padB = 32;
        var min = Math.min.apply(null, values);
        var max = Math.max.apply(null, values);
        var range = max - min || 1;

        var points = values.map(function (v, i) {
            var x = padL + (i / (values.length - 1)) * (w - padL - padR);
            var y = padT + (1 - (v - min) / range) * (h - padT - padB);
            return { x: x, y: y, v: v };
        });
        var polyline = points.map(function (p) { return p.x.toFixed(1) + ',' + p.y.toFixed(1); }).join(' ');

        var svg = '<svg class="detail-chart" viewBox="0 0 ' + w + ' ' + h + '">';
        for (var g = 0; g <= 4; g++) {
            var gy = padT + (h - padT - padB) * (g / 4);
            var gv = max - range * (g / 4);
            var label;
            if (type === 'totalVolume') label = formatAmount(gv);
            else if (type === 'avgRate') label = gv.toFixed(1) + '%';
            else if (type === 'rank') label = String(Math.round(-gv)) + '위';
            else label = String(Math.round(gv));
            svg += '<line x1="' + padL + '" y1="' + gy.toFixed(1) + '" x2="' + (w - padR) + '" y2="' + gy.toFixed(1) + '" stroke="var(--border)" stroke-dasharray="3,3"/>';
            svg += '<text x="' + (padL - 4) + '" y="' + (gy + 4).toFixed(1) + '" text-anchor="end" fill="var(--text-muted)" font-size="10">' + label + '</text>';
        }
        svg += '<polyline fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="' + polyline + '"/>';
        points.forEach(function (p) {
            svg += '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="3" fill="var(--accent)"/>';
        });
        var step = Math.max(1, Math.floor(labels.length / 6));
        for (var i = 0; i < labels.length; i += step) {
            var lbl = labels[i].substring(4, 6) + '/' + labels[i].substring(6, 8);
            svg += '<text x="' + points[i].x.toFixed(1) + '" y="' + (h - 2) + '" text-anchor="middle" fill="var(--text-muted)" font-size="10">' + lbl + '</text>';
        }
        svg += '</svg>';
        return svg;
    }

    // ── 서머리 차트 팝업 ──
    function openSummaryChart(type) {
        var history = state.summaryHistory;
        if (!history || history.length < 2) {
            openDetailModal('히스토리', '<p class="report__empty">히스토리 데이터가 부족합니다</p>');
            return;
        }
        var titles = { avgRate: '평균 상승률 추이', limitUp: '상한가 종목 수 추이', totalVolume: '총 거래대금 추이' };
        var recent = history.slice(0, 30).reverse();
        var values = recent.map(function (h) {
            return type === 'avgRate' ? h.avgRate : (type === 'limitUp' ? h.limitUp : h.totalVolume);
        });
        var labels = recent.map(function (h) { return h.date; });

        var html = buildLineChart(values, labels, type);
        html += '<div class="detail-history">';
        history.slice(0, 15).forEach(function (h) {
            var val = type === 'avgRate' ? '+' + (h.avgRate || 0).toFixed(2) + '%' :
                type === 'limitUp' ? (h.limitUp || 0) + '종목' :
                    formatAmount(h.totalVolume || 0);
            html += '<div class="detail-history__row">';
            html += '<span class="detail-history__date">' + formatDateKorean(h.date) + '</span>';
            html += '<span class="detail-history__val">' + val + '</span>';
            html += '</div>';
        });
        html += '</div>';
        openDetailModal(titles[type] || '추이', html);
    }

    // ── 섹터/테마 상세 팝업 ──
    function getSectorRankHistory(name, type) {
        var history = state.summaryHistory;
        if (!history || history.length === 0) return { rank: '-', delta: '', history: [] };
        var field = type === 'theme' ? 'topThemes' : 'topSectors';
        var currentDate = state.dates[state.dateIndex];
        var rank = '-', delta = '', rankHist = [];
        for (var i = 0; i < history.length; i++) {
            var list = history[i].topSectors ? history[i][field] : [];
            var idx = list ? list.indexOf(name) : -1;
            rankHist.push({ date: history[i].date, rank: idx >= 0 ? idx + 1 : null });
            if (history[i].date === currentDate && idx >= 0) rank = idx + 1;
        }
        // 전일 대비 변동
        if (rankHist.length >= 2 && rankHist[0].rank != null && rankHist[1].rank != null) {
            var diff = rankHist[1].rank - rankHist[0].rank;
            if (diff > 0) delta = '<span class="rank-delta rank-delta--up">\u25B2' + diff + '</span>';
            else if (diff < 0) delta = '<span class="rank-delta rank-delta--down">\u25BC' + Math.abs(diff) + '</span>';
        } else if (rankHist.length >= 2 && rankHist[0].rank != null && rankHist[1].rank == null) {
            delta = '<span class="rank-delta rank-delta--new">NEW</span>';
        }
        return { rank: rank, delta: delta, history: rankHist };
    }

    // 섹터/테마 히스토리 데이터 수집 (각 날짜별 avgRate, volume, rank)
    function getSectorHistoryData(name, type) {
        var history = state.summaryHistory;
        if (!history || history.length === 0) return [];
        var result = [];
        var field = type === 'theme' ? 'topThemes' : 'topSectors';
        // 각 날짜의 실제 데이터를 가져오려면 해당 날짜의 rankings를 로드해야 하지만
        // 현재 분석 데이터에서만 가능. 순위 이력만 summary에서 추출.
        history.forEach(function (h) {
            var list = h[field] || [];
            var idx = list.indexOf(name);
            result.push({ date: h.date, rank: idx >= 0 ? idx + 1 : null });
        });
        return result;
    }

    // ── 대장점수 상세 팝업 ──
    function openScoreDetail(ticker) {
        var stock = null;
        for (var i = 0; i < state.allRankings.length; i++) {
            if (state.allRankings[i].ticker === ticker) { stock = state.allRankings[i]; break; }
        }
        if (!stock) return;
        var detail = stock.score_detail || {};
        var isV3 = detail.ti != null;
        var tp = detail.tp || 0, tl = detail.tl || 0, ti = detail.ti || 0;
        var cls = stock.score >= 70 ? 'high' : (stock.score >= 40 ? 'mid' : 'low');

        var capStr = formatAmount(stock.market_cap);

        var html = '<div class="score-popup">';
        html += '<div class="score-popup__header">';
        html += '<span class="score-badge score-badge--' + cls + '" style="width:52px;height:34px;font-size:16px">' + stock.score + '</span>';
        html += '<div class="score-popup__stock">';
        html += '<span class="score-popup__name">' + stock.name + '</span>';
        html += '<span class="score-popup__meta">' + stock.market + ' &middot; ' + (stock.sector || '-') + ' &middot; 시총 ' + capStr + ' &middot; +' + stock.change_rate.toFixed(2) + '%</span>';
        html += '</div>';
        html += '<a class="score-popup__naver" href="https://finance.naver.com/item/main.naver?code=' + stock.ticker + '" target="_blank" rel="noopener" title="네이버 증권에서 보기"><span class="score-popup__naver-icon">N</span></a>';
        html += '</div>';

        if (isV3) {
            html += scorePopupItem('테마강도 (TP)', tp, 35, tpLevelText(tp), '테마의 시장 파괴력 — 모멘텀 + 지속일 + 규모');
            html += scorePopupItem('대장성 (TL)', tl, 45, tlLevelText(tl), '테마 내 리더십 — 등락률 + 거래집중 + 연속출현');
            html += scorePopupItem('거래강도 (TI)', ti, 20, tiLevelText(ti), '개별 거래 활력 — 5일대비 + 회전율 + 수급');
        } else {
            var bz = detail.buzz || 0, qu = detail.quality || 0;
            var ty = detail.type || 0, tv = detail.turnover || 0;
            html += scorePopupItem('뉴스 양', bz, 20, '', '관련 뉴스 건수');
            html += scorePopupItem('뉴스 질', qu, 25, '', '주요 언론사, 수치 포함');
            html += scorePopupItem('이슈 강도', ty, 30, '', '테마 연동, 이슈 유형');
            html += scorePopupItem('거래량 강도', tv, 25, '', '시총 대비 거래대금');
        }

        if (stock.theme_tag) {
            html += '<div class="score-popup__theme"><span class="theme-tag">' + stock.theme_tag + '</span>';
            if (stock.rise_reason) html += '<span style="font-size:12px;color:var(--text-secondary)">' + stock.rise_reason + '</span>';
            html += '</div>';
        }

        if (stock.news && stock.news.length > 0) {
            html += '<div class="score-popup__news">';
            stock.news.slice(0, 5).forEach(function (n) {
                html += '<a class="score-popup__news-item" href="' + n.link + '" target="_blank" rel="noopener">';
                html += '<span class="score-popup__news-title">' + n.title + '</span>';
                if (n.date) html += '<span class="score-popup__news-date">' + n.date + '</span>';
                html += '</a>';
            });
            html += '</div>';
        }
        html += '</div>';

        openDetailModal(stock.name + ' 대장점수 분석', html);
    }

    function scorePopupItem(label, val, max, level, desc) {
        var pct = Math.round(val / max * 100);
        var h = '<div class="score-popup__row">';
        h += '<div class="score-popup__row-header">';
        h += '<span class="score-popup__row-label">' + label + '</span>';
        h += '<span class="score-popup__row-score">' + val + '<span style="color:var(--text-muted);font-weight:400">/' + max + '</span></span>';
        h += '</div>';
        h += '<div class="score-analysis__bar"><div class="score-analysis__fill" style="width:' + pct + '%"></div></div>';
        if (level || desc) {
            h += '<div class="score-popup__row-desc">';
            if (level) h += '<strong>' + level + '</strong> — ';
            h += desc;
            h += '</div>';
        }
        h += '</div>';
        return h;
    }

    function tpLevelText(v) {
        if (v >= 28) return '최강 테마';
        if (v >= 20) return '강한 테마';
        if (v >= 12) return '보통 테마';
        if (v >= 5) return '약한 테마';
        return '테마 미확인';
    }
    function tlLevelText(v) {
        if (v >= 35) return '확실한 대장';
        if (v >= 25) return '유력 대장';
        if (v >= 15) return '중위권';
        if (v >= 8) return '추종주';
        return '미확인';
    }
    function tiLevelText(v) {
        if (v >= 16) return '폭발적';
        if (v >= 12) return '매우 활발';
        if (v >= 8) return '활발';
        if (v >= 4) return '보통';
        return '평이';
    }

    function openSectorDetail(name, type) {
        var list = type === 'theme'
            ? (state.analysis ? state.analysis.allThemes : [])
            : (state.analysis ? state.analysis.allSectors : []);
        var item = null;
        for (var i = 0; i < list.length; i++) {
            if (list[i].name === name) { item = list[i]; break; }
        }
        if (!item) return;
        var ratings = getRatings();
        var rankInfo = getSectorRankHistory(name, type);

        // 클릭 가능한 stat 카드
        var rankText = rankInfo.rank !== '-' ? rankInfo.rank + '위' : '-';
        var deltaHtml = rankInfo.delta ? ' ' + rankInfo.delta : '';
        var html = '<div class="detail-stats detail-stats--clickable">';
        // 종목 수
        html += '<div class="detail-stat">';
        html += '<span class="detail-stat__label">종목 수</span>';
        html += '<span class="detail-stat__value">' + item.stocks.length + '개</span>';
        html += '</div>';
        // 현재 순위 + 변동 옆에
        html += '<div class="detail-stat detail-stat--click" data-chart="rank" data-name="' + name + '" data-type="' + type + '">';
        html += '<span class="detail-stat__label">현재 순위</span>';
        html += '<span class="detail-stat__value">' + rankText + deltaHtml + '</span>';
        html += '</div>';
        // 평균 상승률
        html += '<div class="detail-stat detail-stat--click" data-chart="avgRate" data-name="' + name + '" data-type="' + type + '">';
        html += '<span class="detail-stat__label">평균 상승률</span>';
        html += '<span class="detail-stat__value detail-stat__value--rise">+' + item.avgRate.toFixed(2) + '%</span>';
        html += '</div>';
        // 총 거래대금
        html += '<div class="detail-stat detail-stat--click" data-chart="volume" data-name="' + name + '" data-type="' + type + '">';
        html += '<span class="detail-stat__label">총 거래대금</span>';
        html += '<span class="detail-stat__value">' + formatAmount(item.totalVolume) + '</span>';
        html += '</div>';
        html += '</div>';

        // 차트 영역 (기본: 순위 차트 표시)
        html += '<div class="detail-chart-area" id="detailChartArea">';
        html += buildRankChartHtml(name, type);
        html += '</div>';

        // 네이버 링크 (테마 또는 섹터)
        var naverNo = type === 'theme' ? item.themeNo : item.industryNo;
        var naverType = type === 'theme' ? 'theme' : 'upjong';
        if (naverNo) {
            html += '<div class="detail-naver-link">';
            html += '<a href="https://finance.naver.com/sise/sise_group_detail.naver?type=' + naverType + '&no=' + naverNo + '" target="_blank" rel="noopener" class="detail-naver-btn">';
            html += '<span class="detail-naver-btn__icon">N</span>';
            html += '네이버에서 전체 종목 보기';
            html += '</a>';
            html += '<span class="detail-naver-note">상승 TOP 100 중 ' + item.stocks.length + '종목 포함</span>';
            html += '</div>';
        }

        // 종목 리스트 (호버 컨트롤 + 네이버 링크)
        html += '<div class="detail-stocks">';
        item.stocks.forEach(function (s, idx) {
            var url = 'https://finance.naver.com/item/main.naver?code=' + s.ticker;
            var scoreCls = s.score >= 70 ? 'high' : (s.score >= 40 ? 'mid' : 'low');
            html += '<div class="detail-stock" data-url="' + url + '">';
            html += '<span class="detail-stock__rank">' + (idx + 1) + '</span>';
            html += '<span class="detail-stock__name"><span class="score-click detail-stock__link" data-ticker="' + s.ticker + '">' + s.name + '</span><span class="compact-row__market">' + s.market + '</span>' + controlsHtml(s.ticker, ratings) + '</span>';
            html += '<span class="detail-stock__rate">+' + s.change_rate.toFixed(2) + '%</span>';
            html += '<span class="score-badge score-badge--' + scoreCls + '" style="font-size:11px;width:32px;height:22px">' + s.score + '</span>';
            html += '</div>';
        });
        html += '</div>';
        openDetailModal(name + (type === 'theme' ? ' 테마' : ' 섹터') + ' 상세', html);
    }

    function buildRankChartHtml(name, type) {
        var histData = getSectorHistoryData(name, type);
        var valid = histData.filter(function (h) { return h.rank != null; }).reverse();
        if (valid.length < 2) return '<p class="report__empty" style="padding:8px 12px">순위 히스토리 데이터 부족</p>';
        var ranks = valid.map(function (h) { return h.rank; });
        var labels = valid.map(function (h) { return h.date; });
        var inverted = ranks.map(function (r) { return -r; });
        return buildLineChart(inverted, labels, 'rank');
    }

    // 섹터/테마 상세 팝업 내 stat 클릭 → 차트 전환
    function onDetailStatClick(chartType, name, type) {
        var area = document.getElementById('detailChartArea');
        if (!area) return;
        // 활성 탭 표시
        document.querySelectorAll('.detail-stat--click').forEach(function (el) {
            el.classList.toggle('detail-stat--active', el.getAttribute('data-chart') === chartType);
        });
        if (chartType === 'rank') {
            area.innerHTML = buildRankChartHtml(name, type);
        } else {
            // avgRate, volume — 현재 데이터에선 일별 이 섹터/테마의 값을 직접 알 수 없음
            // summary.json에서 전체 시장의 avgRate/volume만 있음
            // 대신 전체 시장의 해당 지표 추이를 보여줌
            var history = state.summaryHistory;
            if (!history || history.length < 2) {
                area.innerHTML = '<p class="report__empty" style="padding:8px 12px">히스토리 데이터 부족</p>';
                return;
            }
            var recent = history.slice(0, 30).reverse();
            var values, mapType;
            if (chartType === 'avgRate') {
                values = recent.map(function (h) { return h.avgRate || 0; });
                mapType = 'avgRate';
            } else {
                values = recent.map(function (h) { return h.totalVolume || 0; });
                mapType = 'totalVolume';
            }
            var labels = recent.map(function (h) { return h.date; });
            area.innerHTML = buildLineChart(values, labels, mapType);
        }
    }

    // ── 전체보기 팝업 ──
    function openAllList(type) {
        var list = type === 'theme'
            ? (state.analysis ? state.analysis.allThemes : [])
            : (state.analysis ? state.analysis.allSectors : []);
        if (!list || list.length === 0) {
            openDetailModal(type === 'theme' ? '전체 테마' : '전체 섹터', '<p class="report__empty">데이터 없음</p>');
            return;
        }
        var html = '<div class="detail-all-list">';
        list.forEach(function (item, idx) {
            html += '<div class="detail-all-item" data-name="' + item.name + '" data-type="' + type + '">';
            html += '<span class="detail-all-item__rank">' + (idx + 1) + '</span>';
            html += '<span class="detail-all-item__name">' + item.name + '</span>';
            html += '<span class="detail-all-item__count">' + item.stocks.length + '종목</span>';
            html += '<span class="detail-all-item__rate">+' + item.avgRate.toFixed(2) + '%</span>';
            html += '<span class="detail-all-item__volume">' + formatAmount(item.totalVolume) + '</span>';
            html += '</div>';
        });
        html += '</div>';
        openDetailModal(type === 'theme' ? '전체 테마 목록' : '전체 섹터 목록', html);
    }

    // ── 데이터 분석 ──
    function analyzeData(rankings) {
        var result = {};

        // 1) 요약
        var totalCount = rankings.length;
        var avgRate = rankings.reduce(function (s, r) { return s + r.change_rate; }, 0) / totalCount;
        var limitUp = rankings.filter(function (r) { return r.change_rate >= 29.9; }).length;
        var totalVolume = rankings.reduce(function (s, r) { return s + (r.trading_value || 0); }, 0);
        result.summary = { count: totalCount, avgRate: avgRate, limitUp: limitUp, totalVolume: totalVolume };

        // 2) 섹터 분석
        var sectorMap = {};
        rankings.forEach(function (r) {
            var sec = r.sector || '기타';
            if (!sectorMap[sec]) sectorMap[sec] = { name: sec, stocks: [], totalRate: 0, totalVolume: 0, industryNo: null };
            sectorMap[sec].stocks.push(r);
            sectorMap[sec].totalRate += r.change_rate;
            sectorMap[sec].totalVolume += (r.trading_value || 0);
            if (!sectorMap[sec].industryNo && r.industry_no) sectorMap[sec].industryNo = r.industry_no;
        });
        result.allSectors = Object.values(sectorMap)
            .filter(function (s) { return s.stocks.length >= 2; })
            .map(function (s) {
                s.avgRate = s.totalRate / s.stocks.length;
                s.stocks.sort(function (a, b) { return b.change_rate - a.change_rate; });
                return s;
            })
            .sort(function (a, b) { return b.stocks.length - a.stocks.length; });
        result.sectors = result.allSectors.slice(0, 5);

        // 3) 테마 분석 (theme_tag 원본으로 그룹핑, 표시만 줄임)
        var themeMap = {};
        rankings.forEach(function (r) {
            if (!r.theme_tag) return;
            var tag = r.theme_tag;
            if (!themeMap[tag]) themeMap[tag] = { name: tag, count: 0, totalRate: 0, totalVolume: 0, stocks: [], themeNo: null };
            themeMap[tag].count++;
            themeMap[tag].totalRate += r.change_rate;
            themeMap[tag].totalVolume += (r.trading_value || 0);
            themeMap[tag].stocks.push(r);
            if (!themeMap[tag].themeNo && r.theme_no) themeMap[tag].themeNo = r.theme_no;
        });
        result.allThemes = Object.values(themeMap)
            .filter(function (t) { return t.count >= 2; })
            .map(function (t) {
                t.avgRate = t.totalRate / t.count;
                t.stocks.sort(function (a, b) { return b.change_rate - a.change_rate; });
                return t;
            })
            .sort(function (a, b) { return b.count - a.count; });
        result.themes = result.allThemes.slice(0, 5);

        // 4) 52주 신고가 / 근접 — 장중 고점(high_price) 우선, 없으면 종가 폴백 (pullback 섹션과 통일)
        var highList = [];
        var nearHighList = [];
        rankings.forEach(function (r) {
            var h = r.high_52w || 0;
            if (h <= 0) return;
            var peakVal = r.high_price || r.close_price;
            var ratio = peakVal / h;
            if (ratio >= 1.0) {
                highList.push({ stock: r, ratio: ratio });
            } else if (ratio >= 0.9) {
                nearHighList.push({ stock: r, ratio: ratio, gap: ((1 - ratio) * 100).toFixed(1) });
            }
        });
        highList.sort(function (a, b) { return b.stock.change_rate - a.stock.change_rate; });
        nearHighList.sort(function (a, b) { return a.gap - b.gap; });
        result.highList = highList;
        result.nearHighList = nearHighList;

        return result;
    }

    // ── 급등 후 조정 분석 (과거 데이터 비교) ──
    function analyzePullbacks(currentDate, allDates) {
        // 과거 날짜: 장마감 저장본에서 종목/고점/저점 frozen, 현재가만 실시간 재조회 후 % 재계산
        // 저장본 없으면 runtime 재계산
        var isToday = (state.dateIndex === 0);
        if (!isToday) {
            return StockAPI.getRankings(currentDate, 'ALL').then(function (data) {
                if (data && Array.isArray(data.pullbacks)) return refreshPullbackPrices(data.pullbacks);
                return analyzePullbacksRuntime(currentDate, allDates);
            }).catch(function () { return analyzePullbacksRuntime(currentDate, allDates); });
        }
        return analyzePullbacksRuntime(currentDate, allDates);
    }

    // ── 과거 스냅샷 pullbacks 의 현재가만 실시간 갱신 + dropPct/bouncePct 재계산 ──
    // 종목 리스트·peakPrice·peakDate·postPeakLow 는 저장 당시 값 유지 (frozen).
    // 실시간 조회 실패 종목은 frozen 값 그대로 유지.
    function refreshPullbackPrices(frozen) {
        if (!frozen || frozen.length === 0) return Promise.resolve(frozen || []);
        var pricePromises = frozen.map(function (p) {
            return StockAPI.getCurrentPrice(p.ticker)
                .then(function (data) { return { ticker: p.ticker, price: data.price }; })
                .catch(function () { return { ticker: p.ticker, price: null }; });
        });
        return batchProcess(pricePromises, 5).then(function (prices) {
            var priceMap = {};
            prices.forEach(function (x) { priceMap[x.ticker] = x.price; });
            var updated = frozen.map(function (p) {
                var livePrice = priceMap[p.ticker];
                if (!livePrice || livePrice <= 0) return p;
                var dropPct = ((p.peakPrice - livePrice) / p.peakPrice) * 100;
                var low = (p.postPeakLow && p.postPeakLow > 0) ? p.postPeakLow : livePrice;
                var bouncePct = low > 0 ? ((livePrice - low) / low * 100) : 0;
                var next = {};
                for (var k in p) { if (Object.prototype.hasOwnProperty.call(p, k)) next[k] = p[k]; }
                next.currentPrice = livePrice;
                next.dropPct = dropPct;
                next.bouncePct = bouncePct;
                next.bounceBack = bouncePct >= REBOUND_PCT;
                return next;
            });
            updated.sort(function (a, b) { return b.dropPct - a.dropPct; });
            return updated;
        });
    }

    // ── runtime 재계산 로직 (기존 analyzePullbacks 본체) ──
    function analyzePullbacksRuntime(currentDate, allDates) {
        // 과거 90일 데이터에서 PEAK_PCT+ 급등 또는 신고가 돌파 종목 찾기
        var pastDates = allDates.filter(function (d) { return d < currentDate; }).slice(0, 90);
        if (pastDates.length === 0) return Promise.resolve([]);

        var peakStocks = {}; // ticker → { name, peakPrice (장중 고점), peakDate, reason }

        var promises = pastDates.map(function (date) {
            return StockAPI.getRankings(date, 'ALL')
                .then(function (data) {
                    (data.rankings || []).forEach(function (r) {
                        // 장중 고점 우선, 없으면 종가 폴백
                        var peakVal = r.high_price || r.close_price;
                        var dominated = r.change_rate >= PEAK_PCT;
                        var hitHigh = r.high_52w > 0 && peakVal >= r.high_52w;
                        if (!dominated && !hitHigh) return;

                        var existing = peakStocks[r.ticker];
                        if (!existing || peakVal > existing.peakPrice) {
                            peakStocks[r.ticker] = {
                                name: r.name,
                                market: r.market,
                                sector: r.sector,
                                peakPrice: peakVal,
                                peakDate: date,
                                reason: dominated ? '+' + r.change_rate.toFixed(1) + '% 급등' : '52주 신고가',
                            };
                        }
                    });
                })
                .catch(function () {});
        });

        return Promise.all(promises).then(function () {
            // 현재가 조회 (배치)
            var tickers = Object.keys(peakStocks);
            if (tickers.length === 0) return [];

            var pricePromises = tickers.map(function (ticker) {
                return StockAPI.getCurrentPrice(ticker)
                    .then(function (data) {
                        return { ticker: ticker, price: data.price };
                    })
                    .catch(function () {
                        return { ticker: ticker, price: null };
                    });
            });

            return batchProcess(pricePromises, 5).then(function (prices) {
                var pullbacks = [];
                prices.forEach(function (p) {
                    if (!p.price) return;
                    var peak = peakStocks[p.ticker];
                    var dropPct = ((peak.peakPrice - p.price) / peak.peakPrice * 100);
                    if (dropPct >= DROP_PCT) {
                        pullbacks.push({
                            ticker: p.ticker,
                            name: peak.name,
                            market: peak.market,
                            sector: peak.sector,
                            peakPrice: peak.peakPrice,
                            peakDate: peak.peakDate,
                            currentPrice: p.price,
                            dropPct: dropPct,
                            reason: peak.reason,
                        });
                    }
                });
                pullbacks.sort(function (a, b) { return b.dropPct - a.dropPct; });
                return enrichBounce(pullbacks, currentDate);
            });
        });
    }

    // ── pullback 후보의 peak 이후 저점 추출 + 반등률 계산 ──
    function enrichBounce(pullbacks, currentDate) {
        if (pullbacks.length === 0) return Promise.resolve(pullbacks);

        var bouncePromises = pullbacks.map(function (p) {
            // /api/chart-ohlc 프록시 (Vercel serverless) — 브라우저 CORS 우회
            var url = '/api/chart-ohlc?ticker=' + p.ticker +
                '&from=' + p.peakDate + '&to=' + currentDate;
            return fetch(url)
                .then(function (r) { return r.ok ? r.json() : []; })
                .then(function (arr) {
                    if (!arr || !arr.length) return { ticker: p.ticker, low: p.currentPrice };
                    var after = arr.filter(function (x) { return x.localDate > p.peakDate; });
                    if (!after.length) return { ticker: p.ticker, low: p.currentPrice };
                    var lows = after.map(function (x) { return x.lowPrice || x.closePrice; })
                        .filter(function (v) { return v && v > 0; });
                    if (!lows.length) return { ticker: p.ticker, low: p.currentPrice };
                    return { ticker: p.ticker, low: Math.min.apply(null, lows) };
                })
                .catch(function () { return { ticker: p.ticker, low: p.currentPrice }; });
        });

        return batchProcess(bouncePromises, 5).then(function (lows) {
            var lowMap = {};
            lows.forEach(function (x) { lowMap[x.ticker] = x.low; });
            pullbacks.forEach(function (p) {
                var low = lowMap[p.ticker] || p.currentPrice;
                p.postPeakLow = low;
                p.bouncePct = low > 0 ? (p.currentPrice - low) / low * 100 : 0;
                p.bounceBack = p.bouncePct >= REBOUND_PCT;
            });
            return pullbacks;
        });
    }

    function batchProcess(promises, batchSize) {
        var results = [];
        var batches = [];
        for (var i = 0; i < promises.length; i += batchSize) {
            batches.push(promises.slice(i, i + batchSize));
        }
        var chain = Promise.resolve();
        batches.forEach(function (batch) {
            chain = chain.then(function () {
                return Promise.all(batch).then(function (batchResults) {
                    results = results.concat(batchResults);
                });
            });
        });
        return chain.then(function () { return results; });
    }

    // ── 렌더링 ──
    function renderSummary(summary, history, currentDate) {
        document.getElementById('sumCount').textContent = summary.count + '개';
        document.getElementById('sumAvgRate').textContent = '+' + summary.avgRate.toFixed(2) + '%';
        document.getElementById('sumLimit').textContent = summary.limitUp + '종목';
        document.getElementById('sumVolume').textContent = formatAmount(summary.totalVolume);

        // Find previous day's data from history
        var prev = null;
        if (history && history.length > 0) {
            for (var i = 0; i < history.length; i++) {
                if (history[i].date === currentDate) {
                    if (i + 1 < history.length) prev = history[i + 1];
                    break;
                }
            }
        }

        // Delta badges
        renderDelta('sumAvgRate', summary.avgRate, prev ? prev.avgRate : null, '%p', true);
        renderDelta('sumLimit', summary.limitUp, prev ? prev.limitUp : null, '개');
        renderDelta('sumVolume', summary.totalVolume, prev ? prev.totalVolume : null, null, false, true);

        // Sparklines
        if (history && history.length >= 2) {
            var recent = history.slice(0, 30).reverse();
            renderSparkline('sparkAvgRate', recent.map(function(h) { return h.avgRate; }));
            renderSparkline('sparkLimit', recent.map(function(h) { return h.limitUp; }));
            renderSparkline('sparkVolume', recent.map(function(h) { return h.totalVolume; }));
        }
    }

    function renderDelta(parentId, current, prev, unit, isPercent, isAmount) {
        var container = document.getElementById(parentId);
        if (!container) return;
        var old = container.parentElement.querySelector('.stat-delta');
        if (old) old.remove();

        if (prev == null) return;
        var diff = current - prev;
        var diffText;
        if (isAmount) {
            diffText = formatAmount(Math.abs(diff));
            if (diff > 0) diffText = '+' + diffText;
            else if (diff < 0) diffText = '-' + diffText;
            else diffText = '-';
        } else if (isPercent) {
            diffText = (diff >= 0 ? '+' : '') + diff.toFixed(2) + (unit || '');
        } else {
            diffText = (diff >= 0 ? '+' : '') + diff + (unit || '');
        }

        var cls = diff > 0 ? 'stat-delta--up' : (diff < 0 ? 'stat-delta--down' : 'stat-delta--neutral');
        var el = document.createElement('span');
        el.className = 'stat-delta ' + cls;
        el.textContent = diffText;
        container.parentElement.appendChild(el);
    }

    function renderSparkline(containerId, values) {
        var container = document.getElementById(containerId);
        if (!container || values.length < 2) {
            if (container) container.innerHTML = '';
            return;
        }

        var w = 64, h = 28;
        var min = Math.min.apply(null, values);
        var max = Math.max.apply(null, values);
        var range = max - min || 1;

        var points = values.map(function(v, i) {
            var x = (i / (values.length - 1)) * w;
            var y = h - 2 - ((v - min) / range) * (h - 4);
            return x.toFixed(1) + ',' + y.toFixed(1);
        }).join(' ');

        var lastX = w;
        var lastY = h - 2 - ((values[values.length - 1] - min) / range) * (h - 4);
        var trend = values[values.length - 1] >= values[0] ? 'up' : 'down';

        container.innerHTML = '<svg class="sparkline" viewBox="0 0 ' + w + ' ' + h + '">' +
            '<polyline class="sparkline__line sparkline__line--' + trend + '" points="' + points + '"/>' +
            '<circle class="sparkline__dot sparkline__dot--' + trend + '" cx="' + lastX.toFixed(1) + '" cy="' + lastY.toFixed(1) + '" r="2"/>' +
            '</svg>';
    }

    function getRankDelta(name, currentRank, history, currentDate, field) {
        if (!history || history.length < 2) return '';
        var prevEntry = null;
        for (var i = 0; i < history.length; i++) {
            if (history[i].date === currentDate) {
                if (i + 1 < history.length) prevEntry = history[i + 1];
                break;
            }
        }
        if (!prevEntry) return '';

        var prevList = prevEntry[field] || [];
        var prevIdx = -1;
        for (var j = 0; j < prevList.length; j++) {
            if (prevList[j] === name) { prevIdx = j; break; }
        }
        if (prevIdx === -1) return ' <span class="rank-delta rank-delta--new">NEW</span>';
        var diff = prevIdx - currentRank;
        if (diff > 0) return ' <span class="rank-delta rank-delta--up">\u25B2' + diff + '</span>';
        if (diff < 0) return ' <span class="rank-delta rank-delta--down">\u25BC' + Math.abs(diff) + '</span>';
        return '';
    }

    var PAGE_SIZE = 5;
    var sectorPage = 0;
    var themePage = 0;

    function renderSectorCard(items, container, ratings, history, currentDate, historyField, startIdx) {
        ratings = ratings || getRatings();
        var rankField = historyField || 'topSectors';
        var cardType = rankField === 'topThemes' ? 'theme' : 'sector';
        startIdx = startIdx || 0;
        var html = '';
        items.forEach(function (sec, i) {
            var globalIdx = startIdx + i;
            var topStocks = sec.stocks.slice(0, 3);
            var delta = getRankDelta(sec.name, globalIdx, history, currentDate, rankField);
            html += '<div class="sector-card sector-card--clickable" data-card-name="' + sec.name + '" data-card-type="' + cardType + '">';
            html += '<div class="sector-card__header">';
            html += '<span class="sector-card__rank">' + (globalIdx + 1) + '</span>';
            var displayName = cardType === 'theme' ? shortenTheme(sec.name, 14) : sec.name;
            html += '<span class="sector-card__name-wrap">';
            html += '<span class="sector-card__name" title="' + sec.name + '">' + displayName + '</span>';
            if (delta) html += delta;
            html += '</span>';
            html += '<span class="sector-card__count">' + sec.stocks.length + '종목</span>';
            html += '</div>';
            html += '<div class="sector-card__stats">';
            html += '<span class="sector-card__rate">평균 +' + sec.avgRate.toFixed(2) + '%</span>';
            html += '<span class="sector-card__volume">거래대금 ' + formatAmount(sec.totalVolume) + '</span>';
            html += '</div>';
            html += '<div class="sector-card__stocks">';
            topStocks.forEach(function (s) {
                html += '<div class="sector-card__stock">';
                html += '<span class="sector-card__stock-name"><span class="sector-card__stock-name-text score-click" data-ticker="' + s.ticker + '" title="' + s.name + '">' + s.name + '</span>' + controlsHtml(s.ticker, ratings) + '</span>';
                html += '<span class="sector-card__stock-rate">+' + s.change_rate.toFixed(2) + '%</span>';
                html += '</div>';
            });
            if (sec.stocks.length > 3) {
                html += '<span class="sector-card__more">외 ' + (sec.stocks.length - 3) + '종목</span>';
            }
            html += '</div>';
            html += '</div>';
        });
        container.innerHTML = html;
    }

    function renderPager(pagerId, allItems, currentPage, onPageChange) {
        var pager = document.getElementById(pagerId);
        if (!pager) return;
        var totalPages = Math.ceil(allItems.length / PAGE_SIZE);
        if (totalPages <= 1) { pager.innerHTML = ''; return; }
        pager.innerHTML =
            '<button class="section-pager__btn" data-dir="prev" ' + (currentPage <= 0 ? 'disabled' : '') + '>‹</button>' +
            '<span class="section-pager__text">' + (currentPage + 1) + '/' + totalPages + '</span>' +
            '<button class="section-pager__btn" data-dir="next" ' + (currentPage >= totalPages - 1 ? 'disabled' : '') + '>›</button>';
        pager.onclick = function (e) {
            var btn = e.target.closest('.section-pager__btn');
            if (!btn || btn.disabled) return;
            var dir = btn.getAttribute('data-dir');
            var newPage = dir === 'prev' ? currentPage - 1 : currentPage + 1;
            if (newPage >= 0 && newPage < totalPages) onPageChange(newPage);
        };
    }

    function renderSectorPage(page) {
        sectorPage = page;
        var all = state.analysis ? state.analysis.allSectors : [];
        var slice = all.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
        var ratings = getRatings();
        renderSectorCard(slice, document.getElementById('sectorCards'), ratings, state.summaryHistory, state.dates[state.dateIndex], 'topSectors', page * PAGE_SIZE);
        renderPager('sectorPager', all, page, renderSectorPage);
    }

    function renderThemePage(page) {
        themePage = page;
        var all = state.analysis ? state.analysis.allThemes : [];
        var slice = all.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
        var ratings = getRatings();
        renderSectorCard(slice, document.getElementById('themeCards'), ratings, state.summaryHistory, state.dates[state.dateIndex], 'topThemes', page * PAGE_SIZE);
        renderPager('themePager', all, page, renderThemePage);
    }

    // renderThemes는 renderThemePage로 대체됨

    // ── 카드뉴스 ──
    function loadCardsIndex() {
        if (state.cardsIndex) return Promise.resolve(state.cardsIndex);
        return fetch('/cards/index.json', { cache: 'no-cache' })
            .then(function (r) { return r.ok ? r.json() : {}; })
            .then(function (idx) { state.cardsIndex = idx || {}; return state.cardsIndex; })
            .catch(function () { state.cardsIndex = {}; return state.cardsIndex; });
    }

    function renderCardsSection() {
        var section = document.getElementById('cardsSection');
        var grid = document.getElementById('cardsGrid');
        if (!section || !grid) return;
        var date = state.dates[state.dateIndex];
        var list = (state.cardsIndex && state.cardsIndex[date]) || [];
        state.cardsList = list;
        if (!list.length) {
            section.style.display = 'none';
            return;
        }
        section.style.display = '';
        state.cardsPage = 0;
        renderCardsPage(0);
    }

    function renderCardsPage(page) {
        state.cardsPage = page;
        var grid = document.getElementById('cardsGrid');
        if (!grid) return;
        var list = state.cardsList;
        var slice = list.slice(page * CARDS_PAGE_SIZE, (page + 1) * CARDS_PAGE_SIZE);
        var html = '';
        slice.forEach(function (card, i) {
            var globalIdx = page * CARDS_PAGE_SIZE + i;
            var label = CARDS_TYPE_LABEL[card.type] || card.type;
            html += '<button type="button" class="cards-grid__item" data-idx="' + globalIdx + '">' +
                '<span class="cards-grid__tag cards-grid__tag--' + card.type + '">' + label + '</span>' +
                '<img class="cards-grid__img" src="/cards/' + card.file + '" alt="' + (card.title || label) + '" loading="lazy">' +
                '</button>';
        });
        grid.innerHTML = html;
        renderPager('cardsPager', list, page, renderCardsPage);
    }

    function openCardsModal(idx) {
        var modal = document.getElementById('cardsModal');
        if (!modal || !state.cardsList.length) return;
        state.cardsModalIdx = idx;
        updateCardsModal();
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }

    function closeCardsModal() {
        var modal = document.getElementById('cardsModal');
        if (!modal) return;
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }

    function updateCardsModal() {
        var list = state.cardsList;
        var idx = state.cardsModalIdx;
        if (idx < 0) idx = 0;
        if (idx >= list.length) idx = list.length - 1;
        state.cardsModalIdx = idx;
        var card = list[idx];
        if (!card) return;
        var label = CARDS_TYPE_LABEL[card.type] || card.type;
        document.getElementById('cardsModalImg').src = '/cards/' + card.file;
        document.getElementById('cardsModalImg').alt = card.title || label;
        var tagEl = document.getElementById('cardsModalTag');
        tagEl.textContent = label;
        tagEl.className = 'cards-modal__tag cards-modal__tag--' + card.type;
        document.getElementById('cardsModalTitle').textContent = card.title || '';
        document.getElementById('cardsModalCount').textContent = (idx + 1) + ' / ' + list.length;
        document.getElementById('cardsModalPrev').disabled = idx <= 0;
        document.getElementById('cardsModalNext').disabled = idx >= list.length - 1;
    }

    function moveCardsModal(delta) {
        var next = state.cardsModalIdx + delta;
        if (next < 0 || next >= state.cardsList.length) return;
        state.cardsModalIdx = next;
        updateCardsModal();
    }

    function scoreItem(label, val, max, level, desc) {
        var pct = Math.round(val / max * 100);
        return '<div class="score-analysis__item">' +
            '<div class="score-analysis__item-header">' +
            '<span class="score-analysis__item-label">' + label + '</span>' +
            '<span class="score-analysis__item-score">' + val + '<span class="score-analysis__item-max">/' + max + '</span></span>' +
            '</div>' +
            '<div class="score-analysis__bar"><div class="score-analysis__fill" style="width:' + pct + '%"></div></div>' +
            '<span class="score-analysis__desc">' + level + ' — ' + desc + '</span>' +
            '</div>';
    }

    // ── 52주 신고가 렌더링 (돌파 + 근접 통합, 2칼럼) ──
    function renderHighSection(highList, nearHighList, currentDate, ratings) {
        ratings = ratings || getRatings();
        var container = document.getElementById('highList');
        if (highList.length === 0 && nearHighList.length === 0) {
            container.innerHTML = '<div class="compact-list"><p class="report__empty">52주 신고가 데이터가 아직 수집되지 않았습니다.</p></div>';
            return;
        }

        // 근접: 최근 고점 순 (days asc)
        nearHighList.sort(function (a, b) {
            var daysA = a.stock.high_52w_date ? daysSince(a.stock.high_52w_date, currentDate) : 9999;
            var daysB = b.stock.high_52w_date ? daysSince(b.stock.high_52w_date, currentDate) : 9999;
            if (daysA !== daysB) return daysA - daysB;
            return parseFloat(a.gap) - parseFloat(b.gap);
        });

        var html = '<div class="compact-list compact-list--grid">';

        // 돌파 먼저
        highList.forEach(function (item) {
            var s = item.stock;
            html += '<div class="compact-row score-click" data-ticker="' + s.ticker + '">';
            html += '<span class="compact-row__name">' + s.name + '<span class="compact-row__market">' + s.market + '</span>' + controlsHtml(s.ticker, ratings) + '</span>';
            html += '<span class="compact-row__tag--break">52주 최고가 돌파</span>';
            html += '<span class="compact-row__rate compact-row__rate--up">+' + s.change_rate.toFixed(2) + '%</span>';
            html += '</div>';
        });

        // 근접: 최근 → 과거 순
        nearHighList.forEach(function (item) {
            var s = item.stock;
            var daysText = '';
            if (s.high_52w_date) {
                var days = daysSince(s.high_52w_date, currentDate);
                if (days >= 0) daysText = days + '일 전 ';
            }
            html += '<div class="compact-row score-click" data-ticker="' + s.ticker + '">';
            html += '<span class="compact-row__name">' + s.name + '<span class="compact-row__market">' + s.market + '</span>' + controlsHtml(s.ticker, ratings) + '</span>';
            html += '<span class="compact-row__tag">' + daysText + '고점 대비 -' + item.gap + '%</span>';
            html += '<span class="compact-row__rate compact-row__rate--up">+' + s.change_rate.toFixed(2) + '%</span>';
            html += '</div>';
        });

        html += '</div>';
        container.innerHTML = html;
    }

    function renderPullbacks(pullbacks, ratings) {
        ratings = ratings || getRatings();
        var container = document.getElementById('pullbackList');
        if (pullbacks.length === 0) {
            container.innerHTML = '<div class="compact-list"><p class="report__empty">조건에 해당하는 종목이 없습니다</p></div>';
            return;
        }
        var html = '<div class="compact-list">';
        pullbacks.forEach(function (p) {
            var url = 'https://finance.naver.com/item/main.naver?code=' + p.ticker;
            html += '<a class="compact-row" href="' + url + '" target="_blank" rel="noopener">';
            html += '<span class="compact-row__name">' + p.name + '<span class="compact-row__market">' + p.market + '</span>' + controlsHtml(p.ticker, ratings) + '</span>';
            html += '<span class="compact-row__detail">';
            html += '<span class="compact-row__peak">고점 ' + formatNumber(p.peakPrice) + '</span>';
            html += '<span class="compact-row__arrow">&rarr;</span>';
            if (p.bounceBack && p.postPeakLow > 0 && p.postPeakLow < p.peakPrice) {
                html += '<span class="compact-row__low">저점 ' + formatNumber(p.postPeakLow) + '</span>';
                html += '<span class="compact-row__arrow">&rarr;</span>';
            }
            html += '<span class="compact-row__current">현재 ' + formatNumber(p.currentPrice) + '</span>';
            html += '</span>';
            html += '<span class="compact-row__rate compact-row__rate--down">-' + p.dropPct.toFixed(1) + '%</span>';
            if (p.bounceBack) {
                html += '<span class="compact-row__tag--bounce">저점 대비 +' + p.bouncePct.toFixed(1) + '%</span>';
            }
            html += '<span class="compact-row__tag">' + p.reason + ' (' + formatDateKorean(p.peakDate) + ')</span>';
            html += '</a>';
        });
        html += '</div>';
        container.innerHTML = html;
    }

    // ── 데이터 로드 ──
    function loadReport() {
        var date = state.dates[state.dateIndex];
        if (!date) return;

        showLoading(true);
        showMessage('');
        $reportTitle.textContent = formatDateKorean(date) + ' 데일리 리포트';
        $dateNext.disabled = state.dateIndex <= 0;
        $datePrev.disabled = state.dateIndex >= state.dates.length - 1;

        // Fetch summary history (non-blocking)
        var summaryPromise = fetch('/data/summary.json')
            .then(function (res) { return res.ok ? res.json() : []; })
            .catch(function () { return []; });

        Promise.all([StockAPI.getRankings(date, 'ALL'), summaryPromise])
            .then(function (results) {
                var data = results[0];
                var history = results[1];
                state.summaryHistory = history || [];

                showLoading(false);
                if (!data.rankings || data.rankings.length === 0) {
                    showMessage('해당 날짜의 데이터가 없습니다.');
                    $content.style.display = 'none';
                    return;
                }

                if (data.collected_at && $lastUpdated) {
                    var d = new Date(data.collected_at);
                    var hh = String(d.getHours()).padStart(2, '0');
                    var mm = String(d.getMinutes()).padStart(2, '0');
                    var label = data.is_final ? '장마감' : '장중';
                    $lastUpdated.textContent = label + ' ' + hh + ':' + mm + ' 수집';
                }

                var analysis = analyzeData(data.rankings);
                state.allRankings = data.rankings;
                state.analysis = analysis;
                var ratings = getRatings();

                updateDateBadge();
                renderSummary(analysis.summary, state.summaryHistory, date);
                sectorPage = 0;
                themePage = 0;
                renderSectorPage(0);
                renderThemePage(0);
                loadCardsIndex().then(renderCardsSection);
                renderHighSection(analysis.highList, analysis.nearHighList, date, ratings);

                // 급등 후 조정 (비동기)
                document.getElementById('pullbackList').innerHTML = '<p class="report__empty" style="padding:16px">조정 종목 분석 중...</p>';
                analyzePullbacks(date, state.dates).then(function (pullbacks) {
                    renderPullbacks(pullbacks, getRatings());
                });
            })
            .catch(function () {
                showLoading(false);
                showMessage('데이터를 불러올 수 없습니다.');
                $content.style.display = 'none';
            });
    }

    // ── 메모 모달 (리포트) ──
    var $memoModal = document.getElementById('memoModal');
    var $memoModalClose = document.getElementById('memoModalClose');
    var $memoModalTitle = document.getElementById('memoModalTitle');
    var $memoTextarea = document.getElementById('memoTextarea');
    var $memoSave = document.getElementById('memoSave');
    var $memoDelete = document.getElementById('memoDelete');
    var _memoTicker = null;

    function openMemo(ticker) {
        _memoTicker = ticker;
        var ratings = getRatings();
        var rd = ratings[ticker] || {};
        var name = '';
        for (var i = 0; i < state.allRankings.length; i++) {
            if (state.allRankings[i].ticker === ticker) { name = state.allRankings[i].name; break; }
        }
        $memoModalTitle.textContent = (name || ticker) + ' 메모';
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
        var ratings = getRatings();
        if (!ratings[_memoTicker]) ratings[_memoTicker] = {};
        ratings[_memoTicker].memo = $memoTextarea.value.trim();
        saveRatings(ratings);
        closeMemo();
        refreshControlsUI(_memoTicker);
    }
    function deleteMemo() {
        if (!_memoTicker) return;
        var ratings = getRatings();
        if (ratings[_memoTicker]) ratings[_memoTicker].memo = '';
        saveRatings(ratings);
        closeMemo();
        refreshControlsUI(_memoTicker);
    }

    // ── 이벤트 위임 (별점, X, 메모) — 리포트 전체 영역 ──
    document.getElementById('reportContent').addEventListener('click', function (e) {
        // 모바일 토글 버튼: 패널 열기/닫기
        var toggleBtn = e.target.closest('.ctrl-toggle');
        if (toggleBtn) {
            e.preventDefault();
            e.stopPropagation();
            var tWrap = toggleBtn.closest('.ctrl-wrap');
            if (!tWrap) return;
            var wasOpen = tWrap.classList.contains('is-open');
            document.querySelectorAll('.ctrl-wrap.is-open').forEach(function (w) {
                if (w !== tWrap) w.classList.remove('is-open');
            });
            if (!wasOpen) tWrap.classList.add('is-open');
            else tWrap.classList.remove('is-open');
            return;
        }
        var starEl = e.target.closest('.star');
        if (starEl) {
            e.preventDefault();
            e.stopPropagation();
            var sr = starEl.closest('.star-rating');
            if (!sr) return;
            var ticker = sr.getAttribute('data-ticker');
            var starNum = parseInt(starEl.getAttribute('data-star'));
            if (!ticker || isNaN(starNum)) return;
            var ratings = getRatings();
            if (!ratings[ticker]) ratings[ticker] = {};
            ratings[ticker].stars = ratings[ticker].stars === starNum ? 0 : starNum;
            saveRatings(ratings);
            refreshControlsUI(ticker);
            return;
        }
        var exBtn = e.target.closest('.exclude-btn');
        if (exBtn) {
            e.preventDefault();
            e.stopPropagation();
            var ticker = exBtn.getAttribute('data-ticker');
            if (!ticker) return;
            var ratings = getRatings();
            if (!ratings[ticker]) ratings[ticker] = {};
            ratings[ticker].excluded = !ratings[ticker].excluded;
            saveRatings(ratings);
            refreshControlsUI(ticker);
            return;
        }
        var memoBtn = e.target.closest('.memo-btn');
        if (memoBtn) {
            e.preventDefault();
            e.stopPropagation();
            var ticker = memoBtn.getAttribute('data-ticker');
            if (ticker) openMemo(ticker);
            return;
        }
        // 종목명 클릭 → 대장점수 팝업
        if (e.target.closest('.float-controls')) return;
        var scoreEl = e.target.closest('.score-click');
        if (scoreEl) {
            e.preventDefault();
            e.stopPropagation();
            var ticker = scoreEl.getAttribute('data-ticker');
            if (ticker) openScoreDetail(ticker);
            return;
        }
    });

    // 메모 모달 이벤트
    if ($memoModal) {
        $memoModalClose.addEventListener('click', closeMemo);
        $memoSave.addEventListener('click', saveMemo);
        $memoDelete.addEventListener('click', deleteMemo);
        $memoModal.addEventListener('click', function (e) { if (e.target === $memoModal) closeMemo(); });
    }

    // ── 초기화 ──
    function init() {
        showLoading(true);
        // 서버에서 최신 ratings 받아온 뒤 리포트 로드 (실패해도 진행)
        loadFromServer().finally(function () {
            StockAPI.getDates()
                .then(function (dates) {
                    state.dates = dates;
                    state.dateIndex = 0;
                    loadReport();
                })
                .catch(function () {
                    showLoading(false);
                    showMessage('날짜 목록을 불러올 수 없습니다.');
                });
        });
    }

    // 모바일 ctrl-wrap 패널: 바깥 탭하면 닫기
    document.addEventListener('click', function (e) {
        if (!e.target.closest('.ctrl-wrap')) {
            document.querySelectorAll('.ctrl-wrap.is-open').forEach(function (w) {
                w.classList.remove('is-open');
            });
        }
    });

    // ── 이벤트 ──
    $datePrev.addEventListener('click', function () {
        if (state.dateIndex < state.dates.length - 1) {
            state.dateIndex++;
            loadReport();
        }
    });
    $dateNext.addEventListener('click', function () {
        if (state.dateIndex > 0) {
            state.dateIndex--;
            loadReport();
        }
    });

    // 날짜 뱃지 클릭 → 오늘로 이동
    if ($dateBadge) {
        $dateBadge.addEventListener('click', function () {
            if (state.dateIndex !== 0) {
                state.dateIndex = 0;
                loadReport();
            }
        });
    }

    // 타이틀 클릭 → 캘린더 팝오버
    if ($reportTitle) {
        $reportTitle.addEventListener('click', function () {
            if (!window.DatePicker || !state.dates || !state.dates.length) return;
            DatePicker.open({
                trigger: $reportTitle,
                dates: state.dates,
                current: state.dates[state.dateIndex],
                onSelect: function (date) {
                    var idx = state.dates.indexOf(date);
                    if (idx < 0 || idx === state.dateIndex) return;
                    state.dateIndex = idx;
                    loadReport();
                }
            });
        });
    }

    // 상세 모달 닫기
    if ($detailModal) {
        $detailModalClose.addEventListener('click', closeDetailModal);
        $detailModal.addEventListener('click', function (e) { if (e.target === $detailModal) closeDetailModal(); });
    }

    // 카드뉴스 — 그리드 클릭 → 모달, 모달 좌우 넘김 + ESC/외부 클릭 닫기
    var $cardsGrid = document.getElementById('cardsGrid');
    var $cardsModal = document.getElementById('cardsModal');
    if ($cardsGrid) {
        $cardsGrid.addEventListener('click', function (e) {
            var btn = e.target.closest('.cards-grid__item');
            if (!btn) return;
            openCardsModal(parseInt(btn.getAttribute('data-idx'), 10) || 0);
        });
    }
    if ($cardsModal) {
        document.getElementById('cardsModalClose').addEventListener('click', closeCardsModal);
        document.getElementById('cardsModalPrev').addEventListener('click', function () { moveCardsModal(-1); });
        document.getElementById('cardsModalNext').addEventListener('click', function () { moveCardsModal(1); });
        $cardsModal.addEventListener('click', function (e) { if (e.target === $cardsModal) closeCardsModal(); });
        document.addEventListener('keydown', function (e) {
            if ($cardsModal.style.display !== 'flex') return;
            if (e.key === 'Escape') closeCardsModal();
            else if (e.key === 'ArrowLeft') moveCardsModal(-1);
            else if (e.key === 'ArrowRight') moveCardsModal(1);
        });
        // 모바일: 좌우 스와이프로 카드 넘김 (수직 스크롤은 그대로 살림)
        var SWIPE_THRESHOLD = 50;
        var touchStartX = 0, touchStartY = 0;
        $cardsModal.addEventListener('touchstart', function (e) {
            if (!e.touches.length) return;
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
        }, { passive: true });
        $cardsModal.addEventListener('touchend', function (e) {
            if (!e.changedTouches.length) return;
            var dx = e.changedTouches[0].clientX - touchStartX;
            var dy = e.changedTouches[0].clientY - touchStartY;
            if (Math.abs(dx) < SWIPE_THRESHOLD || Math.abs(dx) < Math.abs(dy)) return;
            moveCardsModal(dx > 0 ? -1 : 1);
        }, { passive: true });
    }

    // 서머리 카드 클릭 → 차트 팝업
    document.querySelector('.report__summary').addEventListener('click', function (e) {
        var card = e.target.closest('.summary-card');
        if (!card) return;
        var idx = Array.prototype.indexOf.call(card.parentElement.children, card);
        var types = [null, 'avgRate', 'limitUp', 'totalVolume'];
        if (types[idx]) openSummaryChart(types[idx]);
    });

    // 섹터/테마 카드 클릭 → 상세 팝업
    document.addEventListener('click', function (e) {
        // 모바일 토글 버튼: 패널 열기/닫기 (모달 포함 전역)
        var toggleBtn = e.target.closest('.ctrl-toggle');
        if (toggleBtn) {
            e.preventDefault(); e.stopPropagation();
            var tWrap = toggleBtn.closest('.ctrl-wrap');
            if (!tWrap) return;
            var wasOpen = tWrap.classList.contains('is-open');
            document.querySelectorAll('.ctrl-wrap.is-open').forEach(function (w) {
                if (w !== tWrap) w.classList.remove('is-open');
            });
            if (!wasOpen) tWrap.classList.add('is-open');
            else tWrap.classList.remove('is-open');
            return;
        }

        // 별점/제외/메모 (모달 포함 전역 처리)
        var starEl = e.target.closest('.star');
        if (starEl) {
            e.preventDefault(); e.stopPropagation();
            var sr = starEl.closest('.star-rating');
            if (!sr) return;
            var ticker = sr.getAttribute('data-ticker');
            var starNum = parseInt(starEl.getAttribute('data-star'));
            if (!ticker || isNaN(starNum)) return;
            var ratings = getRatings();
            if (!ratings[ticker]) ratings[ticker] = {};
            ratings[ticker].stars = ratings[ticker].stars === starNum ? 0 : starNum;
            saveRatings(ratings);
            refreshControlsUI(ticker);
            return;
        }
        var exBtn = e.target.closest('.exclude-btn');
        if (exBtn) {
            e.preventDefault(); e.stopPropagation();
            var ticker = exBtn.getAttribute('data-ticker');
            if (!ticker) return;
            var ratings = getRatings();
            if (!ratings[ticker]) ratings[ticker] = {};
            ratings[ticker].excluded = !ratings[ticker].excluded;
            saveRatings(ratings);
            refreshControlsUI(ticker);
            return;
        }
        var memoBtn = e.target.closest('.memo-btn');
        if (memoBtn) {
            e.preventDefault(); e.stopPropagation();
            var ticker = memoBtn.getAttribute('data-ticker');
            if (ticker) openMemo(ticker);
            return;
        }

        // float-controls 나머지 영역 클릭은 무시
        if (e.target.closest('.float-controls')) return;

        // 종목명/종목 행 클릭 → 대장점수 팝업 (a 태그 클릭은 제외)
        var scoreEl = e.target.closest('.score-click');
        if (scoreEl && !e.target.closest('a')) {
            e.preventDefault();
            e.stopPropagation();
            var ticker = scoreEl.getAttribute('data-ticker');
            if (ticker) openScoreDetail(ticker);
            return;
        }

        // detail-stock 행 클릭 → 대장점수 팝업
        var stockRow = e.target.closest('.detail-stock');
        if (stockRow && !e.target.closest('a')) {
            var ticker = stockRow.querySelector('.score-click');
            if (ticker) openScoreDetail(ticker.getAttribute('data-ticker'));
            return;
        }

        // 상세 팝업 내 stat 클릭 → 차트 전환
        var statClick = e.target.closest('.detail-stat--click');
        if (statClick) {
            var ct = statClick.getAttribute('data-chart');
            var nm = statClick.getAttribute('data-name');
            var tp = statClick.getAttribute('data-type');
            if (ct && nm) onDetailStatClick(ct, nm, tp);
            return;
        }
        var card = e.target.closest('.sector-card--clickable');
        if (card) {
            var name = card.getAttribute('data-card-name');
            var type = card.getAttribute('data-card-type');
            if (name) openSectorDetail(name, type);
            return;
        }
        // 전체보기 버튼
        var allBtn = e.target.closest('[data-all-type]');
        if (allBtn) {
            openAllList(allBtn.getAttribute('data-all-type'));
            return;
        }
        // 전체보기 팝업 내 아이템 클릭 → 상세
        var allItem = e.target.closest('.detail-all-item');
        if (allItem) {
            var itemName = allItem.getAttribute('data-name');
            var itemType = allItem.getAttribute('data-type');
            if (itemName) {
                closeDetailModal();
                setTimeout(function () { openSectorDetail(itemName, itemType); }, 100);
            }
        }
    });

    init();
})();
