/**
 * 앱 상태 관리 및 이벤트 바인딩
 */
(function () {
    var DAYS_KO = ['일', '월', '화', '수', '목', '금', '토'];
    var RATINGS_KEY = 'stock-ratings';
    var THEME_KEY = 'theme';

    var state = {
        dates: [],
        dateIndex: 0,
        currentMarket: 'ALL',
        latestDate: null,
        rankings: [],
        sortColumn: null,
        sortDirection: null,
        watchlistMode: false,
    };

    // DOM
    var $dateDisplay = document.getElementById('dateDisplay');
    var $dateBadge = document.getElementById('dateBadge');
    var $datePrev = document.getElementById('datePrev');
    var $dateNext = document.getElementById('dateNext');
    var $loading = document.getElementById('loading');
    var $message = document.getElementById('message');
    var $newsModal = document.getElementById('newsModal');
    var $newsModalClose = document.getElementById('newsModalClose');
    var $watchlistBtn = document.getElementById('watchlistBtn');
    var $rankingBody = document.getElementById('rankingBody');
    var $memoModal = document.getElementById('memoModal');
    var $memoModalClose = document.getElementById('memoModalClose');
    var $memoModalTitle = document.getElementById('memoModalTitle');
    var $memoTextarea = document.getElementById('memoTextarea');
    var $memoSave = document.getElementById('memoSave');
    var $memoDelete = document.getElementById('memoDelete');
    var _memoTicker = null;
    var $tagModal = document.getElementById('tagModal');
    var $tagModalClose = document.getElementById('tagModalClose');
    var $tagModalTitle = document.getElementById('tagModalTitle');
    var $tagAutoLabel = document.getElementById('tagAutoLabel');
    var $tagInput = document.getElementById('tagInput');
    var $tagSave = document.getElementById('tagSave');
    var $tagReset = document.getElementById('tagReset');
    var _tagTicker = null;
    var $lastUpdated = document.getElementById('lastUpdated');

    // ── localStorage 레이팅 + 서버 동기화 ──
    var _syncTimer = null;

    function getRatings() {
        try {
            return JSON.parse(localStorage.getItem(RATINGS_KEY) || '{}');
        } catch (e) {
            return {};
        }
    }

    function saveRatings(ratings) {
        localStorage.setItem(RATINGS_KEY, JSON.stringify(ratings));
        // 3초 디바운스 후 서버 동기화
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
        // localStorage가 비어있으면 서버에서 불러오기
        var local = getRatings();
        if (Object.keys(local).length > 0) return;
        fetch('/api/sync-ratings')
            .then(function (r) { return r.json(); })
            .then(function (server) {
                if (server && Object.keys(server).length > 0) {
                    localStorage.setItem(RATINGS_KEY, JSON.stringify(server));
                    renderTable();
                }
            })
            .catch(function () {});
    }

    // ── 유틸 ──
    function formatDateKorean(dateStr) {
        if (!dateStr || dateStr.length !== 8) return dateStr || '-';
        var y = parseInt(dateStr.substring(0, 4));
        var m = parseInt(dateStr.substring(4, 6));
        var d = parseInt(dateStr.substring(6, 8));
        var date = new Date(y, m - 1, d);
        var day = DAYS_KO[date.getDay()];
        return m + '월 ' + d + '일 (' + day + ')';
    }

    function showLoading(show) {
        $loading.style.display = show ? 'block' : 'none';
    }

    function showMessage(text) {
        $message.textContent = text;
        $message.style.display = text ? 'block' : 'none';
    }

    function isPastDate() {
        return state.latestDate && state.dates[state.dateIndex] !== state.latestDate;
    }

    // ── 정렬 ──
    function applySort(rankings) {
        if (!state.sortColumn) return rankings;
        var sorted = rankings.slice();
        sorted.sort(function (a, b) {
            var col = state.sortColumn;
            var diff = 0;
            if (col === 'market_cap' || col === 'trading_value' || col === 'change_rate' || col === 'score') {
                diff = (a[col] || 0) - (b[col] || 0);
            } else if (col === 'sector') {
                diff = (a.sector || '').localeCompare(b.sector || '', 'ko');
            } else if (col === 'theme_tag') {
                diff = (a.theme_tag || '').localeCompare(b.theme_tag || '', 'ko');
            }
            return state.sortDirection === 'asc' ? diff : -diff;
        });
        return sorted;
    }

    // ── 렌더 ──
    function renderTable() {
        var data = state.rankings;
        var ratings = getRatings();

        // 관심종목 필터
        if (state.watchlistMode) {
            data = data.filter(function (r) {
                var rd = ratings[r.ticker];
                return rd && rd.stars > 0;
            });
        }

        var sorted = applySort(data);
        var past = isPastDate();
        StockTable.setCompareHeader(past);
        StockTable.render(sorted, past, ratings);
        StockTable.updateSortIcons(state.sortColumn, state.sortDirection);
    }

    // ── 데이터 로드 ──
    function loadRankings() {
        var date = state.dates[state.dateIndex];
        if (!date) return;

        showLoading(true);
        showMessage('');

        // 날짜 표시
        $dateDisplay.textContent = formatDateKorean(date);
        if (isPastDate()) {
            $dateBadge.textContent = '과거';
            $dateBadge.className = 'date-badge date-badge--past';
        } else {
            $dateBadge.textContent = '오늘';
            $dateBadge.className = 'date-badge';
        }

        StockAPI.getRankings(date, state.currentMarket)
            .then(function (data) {
                showLoading(false);
                state.rankings = data.rankings || [];

                // 업데이트 시간 표시
                if (data.collected_at && $lastUpdated) {
                    var d = new Date(data.collected_at);
                    var hh = String(d.getHours()).padStart(2, '0');
                    var mm = String(d.getMinutes()).padStart(2, '0');
                    var label = data.is_final ? '장마감' : '장중';
                    $lastUpdated.textContent = label + ' ' + hh + ':' + mm + ' 수집';
                }

                if (isPastDate()) {
                    fetchCurrentPrices(state.rankings).then(function (updated) {
                        state.rankings = updated;
                        renderTable();
                    });
                } else {
                    renderTable();
                }
            })
            .catch(function (err) {
                showLoading(false);
                showMessage('데이터를 불러올 수 없습니다.');
                console.error(err);
            });
    }

    function fetchCurrentPrices(rankings) {
        var promises = rankings.map(function (r) {
            return StockAPI.getCurrentPrice(r.ticker)
                .then(function (data) {
                    r.current_price = data.price;
                    return r;
                })
                .catch(function () {
                    r.current_price = null;
                    return r;
                });
        });

        return batchProcess(promises, 5);
    }

    function batchProcess(promises, batchSize) {
        var results = [];
        var batches = [];
        for (var i = 0; i < promises.length; i += batchSize) {
            batches.push(promises.slice(i, i + batchSize));
        }
        return batches.reduce(function (chain, batch) {
            return chain.then(function () {
                return Promise.all(batch).then(function (batchResults) {
                    results = results.concat(batchResults);
                });
            });
        }, Promise.resolve()).then(function () {
            return results;
        });
    }

    // ── 이벤트: 날짜 ──
    function exitWatchlistMode() {
        if (!state.watchlistMode) return false;
        state.watchlistMode = false;
        $watchlistBtn.classList.remove('active');
        return true;
    }

    function onDatePrev() {
        var wasWatch = exitWatchlistMode();
        if (state.dateIndex < state.dates.length - 1) {
            state.dateIndex++;
            loadRankings();
        } else if (wasWatch) {
            // 관심 모드에서 빠져나오면서 이미 가장 오래된 날짜면 그냥 현재 날짜로 리로드
            loadRankings();
        }
    }

    function onDateNext() {
        var wasWatch = exitWatchlistMode();
        if (state.dateIndex > 0) {
            state.dateIndex--;
            loadRankings();
        } else if (wasWatch) {
            loadRankings();
        }
    }

    function onDateBadgeClick() {
        var wasWatch = exitWatchlistMode();
        if (isPastDate() || wasWatch) {
            state.dateIndex = 0;
            loadRankings();
        }
    }

    // ── 이벤트: 탭 ──
    function onTabClick(e) {
        var market = e.target.getAttribute('data-market');
        if (!market) return;
        document.querySelectorAll('.tab[data-market]').forEach(function (tab) {
            tab.classList.remove('active');
        });
        e.target.classList.add('active');
        state.currentMarket = market;
        // 관심 모드 해제 (시장 탭은 날짜별 랭킹이므로)
        if (state.watchlistMode) {
            state.watchlistMode = false;
            $watchlistBtn.classList.remove('active');
        }
        loadRankings();
    }

    // ── 이벤트: 관심종목 ──
    function onWatchlistClick() {
        state.watchlistMode = !state.watchlistMode;
        if (state.watchlistMode) {
            $watchlistBtn.classList.add('active');
            loadWatchlistAcrossDates();
        } else {
            $watchlistBtn.classList.remove('active');
            loadRankings();
        }
    }

    // 모든 날짜에서 관심 종목(stars>0) 취합: 가장 최근 등장 기준
    function loadWatchlistAcrossDates() {
        var ratings = getRatings();
        var watchTickers = Object.keys(ratings).filter(function (t) {
            return ratings[t] && ratings[t].stars > 0;
        });

        $dateDisplay.textContent = '관심 종목 ' + watchTickers.length + '개';
        $dateBadge.textContent = '전체';
        $dateBadge.className = 'date-badge';

        if (watchTickers.length === 0) {
            state.rankings = [];
            showLoading(false);
            renderTable();
            showMessage('관심 등록된 종목이 없습니다. 종목 옆 ⋯ → 별점을 눌러 등록하세요.');
            return;
        }

        showLoading(true);
        showMessage('');

        // 모든 날짜 병렬 fetch (실패 무시)
        var promises = state.dates.map(function (date) {
            return StockAPI.getRankings(date, 'ALL')
                .then(function (d) { return { date: date, rankings: d.rankings || [] }; })
                .catch(function () { return { date: date, rankings: [] }; });
        });

        Promise.all(promises).then(function (results) {
            // 최신 날짜부터 역순으로 검색하여 각 ticker 의 가장 최근 데이터 찾기
            var found = {};
            results.forEach(function (r) {
                r.rankings.forEach(function (stock) {
                    if (watchTickers.indexOf(stock.ticker) < 0) return;
                    if (!found[stock.ticker] || r.date > found[stock.ticker].last_date) {
                        found[stock.ticker] = Object.assign({}, stock, { last_date: r.date });
                    }
                });
            });

            // 관심 순서: stars 높은 순 → 등록한 ticker 순
            var merged = watchTickers
                .map(function (t) { return found[t]; })
                .filter(function (r) { return r; });

            state.rankings = merged;
            showLoading(false);
            renderTable();
        }).catch(function () {
            showLoading(false);
            showMessage('관심 종목 데이터를 불러올 수 없습니다.');
        });
    }

    // ── 이벤트: 정렬 ──
    function onSortClick(e) {
        var th = e.target.closest('.sortable');
        if (!th) return;
        var column = th.getAttribute('data-sort');
        if (!column) return;

        if (state.sortColumn === column) {
            if (state.sortDirection === 'desc') {
                state.sortDirection = 'asc';
            } else {
                state.sortColumn = null;
                state.sortDirection = null;
            }
        } else {
            state.sortColumn = column;
            state.sortDirection = 'desc';
        }
        renderTable();
    }

    // ── 이벤트 위임: tbody 클릭 (별점, X, 점수) ──
    function onBodyClick(e) {
        // 모바일 토글 버튼: 패널 열기/닫기 (PC 에선 hover 로 뜨기 때문에 안 씀)
        var toggleBtn = e.target.closest('.ctrl-toggle');
        if (toggleBtn) {
            var wrap = toggleBtn.closest('.ctrl-wrap');
            if (!wrap) return;
            var wasOpen = wrap.classList.contains('is-open');
            // 다른 열려 있는 패널 닫기
            document.querySelectorAll('.ctrl-wrap.is-open').forEach(function (w) {
                if (w !== wrap) w.classList.remove('is-open');
            });
            if (!wasOpen) wrap.classList.add('is-open');
            else wrap.classList.remove('is-open');
            return;
        }

        // 별점 클릭
        var starEl = e.target.closest('.star');
        if (starEl) {
            var starRating = starEl.closest('.star-rating');
            if (!starRating) return;
            var ticker = starRating.getAttribute('data-ticker');
            var starNum = parseInt(starEl.getAttribute('data-star'));
            if (!ticker || isNaN(starNum)) return;

            var ratings = getRatings();
            if (!ratings[ticker]) ratings[ticker] = {};

            // 같은 별 다시 클릭하면 해제
            if (ratings[ticker].stars === starNum) {
                ratings[ticker].stars = 0;
            } else {
                ratings[ticker].stars = starNum;
            }
            saveRatings(ratings);
            renderTable();
            return;
        }

        // X 버튼 클릭
        var excludeBtn = e.target.closest('.exclude-btn');
        if (excludeBtn) {
            var ticker = excludeBtn.getAttribute('data-ticker');
            if (!ticker) return;

            var ratings = getRatings();
            if (!ratings[ticker]) ratings[ticker] = {};
            ratings[ticker].excluded = !ratings[ticker].excluded;
            saveRatings(ratings);
            renderTable();
            return;
        }

        // 메모 버튼 클릭
        var memoBtn = e.target.closest('.memo-btn');
        if (memoBtn) {
            var ticker = memoBtn.getAttribute('data-ticker');
            if (ticker) openMemo(ticker);
            return;
        }

        // 태그 편집 클릭
        var tagEdit = e.target.closest('.tag-edit');
        if (tagEdit) {
            var ticker = tagEdit.getAttribute('data-ticker');
            if (ticker) openTagEdit(ticker);
            return;
        }

        // 뉴스 버튼 클릭 → 뉴스 모달
        var newsBtn = e.target.closest('.news-btn');
        if (newsBtn) {
            var ticker = newsBtn.getAttribute('data-ticker');
            if (ticker) StockTable.openNews(ticker);
            return;
        }

        // 대장점수 클릭 → 상세 분석 팝업
        var scoreClick = e.target.closest('.score-click');
        if (scoreClick) {
            var ticker = scoreClick.getAttribute('data-ticker');
            if (ticker) openScoreDetail(ticker);
            return;
        }

        // 종목명 링크 클릭 시 네이버 대신 대장점수 팝업 (네이버는 팝업 헤더의 N 버튼으로)
        // Ctrl/Cmd/중간버튼 클릭은 기본 동작(네이버 새 탭) 유지
        var nameLink = e.target.closest('.cell-name__link');
        if (nameLink && !(e.ctrlKey || e.metaKey || e.shiftKey || e.button === 1)) {
            e.preventDefault();
            var ticker = nameLink.getAttribute('data-ticker');
            if (ticker) openScoreDetail(ticker);
            return;
        }
    }

    // ── 메모 모달 ──
    function openMemo(ticker) {
        _memoTicker = ticker;
        var ratings = getRatings();
        var rd = ratings[ticker] || {};
        var name = '';
        for (var i = 0; i < state.rankings.length; i++) {
            if (state.rankings[i].ticker === ticker) { name = state.rankings[i].name; break; }
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
        var text = $memoTextarea.value.trim();
        ratings[_memoTicker].memo = text || '';
        saveRatings(ratings);
        closeMemo();
        renderTable();
    }

    function deleteMemo() {
        if (!_memoTicker) return;
        var ratings = getRatings();
        if (ratings[_memoTicker]) {
            ratings[_memoTicker].memo = '';
        }
        saveRatings(ratings);
        closeMemo();
        renderTable();
    }

    // ── 태그 편집 모달 ──
    function openTagEdit(ticker) {
        _tagTicker = ticker;
        var ratings = getRatings();
        var rd = ratings[ticker] || {};
        var stock = null;
        for (var i = 0; i < state.rankings.length; i++) {
            if (state.rankings[i].ticker === ticker) { stock = state.rankings[i]; break; }
        }
        var name = stock ? stock.name : ticker;
        var autoTag = stock ? (stock.theme_tag || '') : '';

        $tagModalTitle.textContent = name + ' 테마 태그';
        $tagAutoLabel.textContent = autoTag ? '자동 추출: ' + autoTag : '자동 추출된 태그 없음';
        $tagInput.value = rd.customTag != null ? rd.customTag : autoTag;
        $tagModal.style.display = 'flex';
        $tagInput.focus();
        $tagInput.select();
    }

    function closeTagEdit() {
        $tagModal.style.display = 'none';
        _tagTicker = null;
    }

    function sendTagFeedback(action, ticker, tag, originalTag) {
        var body = { action: action, ticker: ticker };
        if (tag) body.tag = tag;
        if (originalTag) body.original_tag = originalTag;
        fetch('/api/tag-feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).catch(function () { /* 실패해도 localStorage는 이미 저장됨 */ });
    }

    function saveTag() {
        if (!_tagTicker) return;
        var ratings = getRatings();
        if (!ratings[_tagTicker]) ratings[_tagTicker] = {};
        var newTag = $tagInput.value.trim();
        var stock = null;
        for (var i = 0; i < state.rankings.length; i++) {
            if (state.rankings[i].ticker === _tagTicker) { stock = state.rankings[i]; break; }
        }
        var autoTag = stock ? (stock.theme_tag || '') : '';

        if (newTag) {
            ratings[_tagTicker].customTag = newTag;
            // 수동 수정 → 수집기 학습
            sendTagFeedback('edit', _tagTicker, newTag);
        } else {
            // 빈 값 저장 = 태그 삭제
            ratings[_tagTicker].customTag = '';
            // 자동 태그가 있었으면 bad_tag로 학습
            if (autoTag) {
                sendTagFeedback('delete', _tagTicker, '', autoTag);
            }
        }
        saveRatings(ratings);
        closeTagEdit();
        renderTable();
    }

    function resetTag() {
        if (!_tagTicker) return;
        var ratings = getRatings();
        if (ratings[_tagTicker]) {
            delete ratings[_tagTicker].customTag;
        }
        // 자동 태그로 복원
        sendTagFeedback('reset', _tagTicker);
        saveRatings(ratings);
        closeTagEdit();
        renderTable();
    }

    // ── 대장점수 상세 팝업 ──
    function openScoreDetail(ticker) {
        var stock = null;
        for (var i = 0; i < state.rankings.length; i++) {
            if (state.rankings[i].ticker === ticker) { stock = state.rankings[i]; break; }
        }
        if (!stock) return;
        var detail = stock.score_detail || {};
        var isV3 = detail.ti != null;
        var tp = detail.tp || 0, tl = detail.tl || 0, ti = detail.ti || 0;
        var cls = stock.score >= 70 ? 'high' : (stock.score >= 40 ? 'mid' : 'low');

        var capStr = (function (n) {
            if (n == null || n === 0) return '-';
            if (n >= 1e12) return (n / 1e12).toFixed(1) + '조';
            if (n >= 1e8) return Math.round(n / 1e8).toLocaleString('ko-KR') + '억';
            return n.toLocaleString('ko-KR');
        })(stock.market_cap);

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
            html += scorePopupItem('호재 강도', ty, 30, '', '테마 연동, 호재 유형');
            html += scorePopupItem('거래량 강도', tv, 25, '', '시총 대비 거래대금');
        }

        if (stock.theme_tag) {
            html += '<div class="score-popup__theme"><span class="theme-tag">' + stock.theme_tag + '</span>';
            if (stock.rise_reason) html += '<span style="font-size:12px;color:var(--text-secondary)">' + stock.rise_reason + '</span>';
            html += '</div>';
        }

        // 뉴스
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

        var $title = document.getElementById('newsModalTitle');
        var $body = document.getElementById('newsModalBody');
        $title.textContent = stock.name + ' 대장점수 분석';
        $body.innerHTML = html;
        $newsModal.style.display = 'flex';
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

    // ── 테마 토글 ──
    var $themeToggle = document.getElementById('themeToggle');

    function applyThemeIcon() {
        var isLight = document.documentElement.getAttribute('data-theme') === 'light';
        $themeToggle.innerHTML = isLight
            ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
            : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
        $themeToggle.title = isLight ? '다크 모드로 전환' : '라이트 모드로 전환';
    }

    function toggleTheme() {
        var isLight = document.documentElement.getAttribute('data-theme') === 'light';
        if (isLight) {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem(THEME_KEY, 'dark');
        } else {
            document.documentElement.setAttribute('data-theme', 'light');
            localStorage.setItem(THEME_KEY, 'light');
        }
        applyThemeIcon();
    }

    applyThemeIcon();

    // ── 초기화 ──
    function init() {
        $themeToggle.addEventListener('click', toggleTheme);

        $datePrev.addEventListener('click', onDatePrev);
        $dateNext.addEventListener('click', onDateNext);
        $dateBadge.addEventListener('click', onDateBadgeClick);

        document.querySelectorAll('.tab[data-market]').forEach(function (tab) {
            tab.addEventListener('click', onTabClick);
        });

        $watchlistBtn.addEventListener('click', onWatchlistClick);

        document.querySelectorAll('.sortable').forEach(function (th) {
            th.addEventListener('click', onSortClick);
        });

        // tbody 이벤트 위임
        $rankingBody.addEventListener('click', onBodyClick);

        // 모바일 ctrl-wrap 패널: 바깥 탭하면 닫기
        document.addEventListener('click', function (e) {
            if (!e.target.closest('.ctrl-wrap')) {
                document.querySelectorAll('.ctrl-wrap.is-open').forEach(function (w) {
                    w.classList.remove('is-open');
                });
            }
        });

        // 뉴스 모달 닫기
        $newsModalClose.addEventListener('click', StockTable.closeNews);
        $newsModal.addEventListener('click', function (e) {
            if (e.target === $newsModal) StockTable.closeNews();
        });

        // 메모 모달
        $memoModalClose.addEventListener('click', closeMemo);
        $memoSave.addEventListener('click', saveMemo);
        $memoDelete.addEventListener('click', deleteMemo);
        $memoModal.addEventListener('click', function (e) {
            if (e.target === $memoModal) closeMemo();
        });

        // 태그 편집 모달
        $tagModalClose.addEventListener('click', closeTagEdit);
        $tagSave.addEventListener('click', saveTag);
        $tagReset.addEventListener('click', resetTag);
        $tagModal.addEventListener('click', function (e) {
            if (e.target === $tagModal) closeTagEdit();
        });
        $tagInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') saveTag();
        });

        showLoading(true);
        loadFromServer();

        StockAPI.getDates()
            .then(function (dates) {
                if (!dates || dates.length === 0) {
                    showLoading(false);
                    showMessage('수집된 데이터가 없습니다.');
                    return;
                }
                state.dates = dates;
                state.latestDate = dates[0];
                state.dateIndex = 0;
                loadRankings();
            })
            .catch(function (err) {
                showLoading(false);
                showMessage('서버 연결에 실패했습니다.');
                console.error(err);
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
