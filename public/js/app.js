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

    // ── localStorage 레이팅 ──
    function getRatings() {
        try {
            return JSON.parse(localStorage.getItem(RATINGS_KEY) || '{}');
        } catch (e) {
            return {};
        }
    }

    function saveRatings(ratings) {
        localStorage.setItem(RATINGS_KEY, JSON.stringify(ratings));
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
            if (col === 'market_cap' || col === 'trading_value') {
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
    function onDatePrev() {
        if (state.dateIndex < state.dates.length - 1) {
            state.dateIndex++;
            loadRankings();
        }
    }

    function onDateNext() {
        if (state.dateIndex > 0) {
            state.dateIndex--;
            loadRankings();
        }
    }

    function onDateBadgeClick() {
        if (isPastDate()) {
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
        loadRankings();
    }

    // ── 이벤트: 관심종목 ──
    function onWatchlistClick() {
        state.watchlistMode = !state.watchlistMode;
        if (state.watchlistMode) {
            $watchlistBtn.classList.add('active');
        } else {
            $watchlistBtn.classList.remove('active');
        }
        renderTable();
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

        // 호재점수 클릭 → 뉴스 모달
        var scoreClick = e.target.closest('.score-click');
        if (scoreClick) {
            var ticker = scoreClick.getAttribute('data-ticker');
            if (ticker) {
                StockTable.openNews(ticker);
            }
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

    function saveTag() {
        if (!_tagTicker) return;
        var ratings = getRatings();
        if (!ratings[_tagTicker]) ratings[_tagTicker] = {};
        ratings[_tagTicker].customTag = $tagInput.value.trim();
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
        saveRatings(ratings);
        closeTagEdit();
        renderTable();
    }

    // ── 테마 토글 ──
    var $themeToggle = document.getElementById('themeToggle');

    function applyThemeIcon() {
        var isLight = document.documentElement.getAttribute('data-theme') === 'light';
        $themeToggle.innerHTML = isLight ? '&#9728;' : '&#9790;';
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
