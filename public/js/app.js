/**
 * 앱 상태 관리 및 이벤트 바인딩
 */
(function () {
    var DAYS_KO = ['일', '월', '화', '수', '목', '금', '토'];

    var state = {
        dates: [],
        dateIndex: 0,
        currentMarket: 'ALL',
        latestDate: null,
        rankings: [],
        sortColumn: null,
        sortDirection: null,
    };

    // DOM
    var $dateDisplay = document.getElementById('dateDisplay');
    var $dateBadge = document.getElementById('dateBadge');
    var $datePrev = document.getElementById('datePrev');
    var $dateNext = document.getElementById('dateNext');
    var $stockCount = document.getElementById('stockCount');
    var $loading = document.getElementById('loading');
    var $message = document.getElementById('message');
    var $newsModal = document.getElementById('newsModal');
    var $newsModalClose = document.getElementById('newsModalClose');

    // 유틸
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

    // 정렬
    function applySort(rankings) {
        if (!state.sortColumn) return rankings;
        var sorted = rankings.slice();
        sorted.sort(function (a, b) {
            if (state.sortColumn === 'market_cap') {
                var diff = (a.market_cap || 0) - (b.market_cap || 0);
                return state.sortDirection === 'asc' ? diff : -diff;
            }
            if (state.sortColumn === 'sector') {
                var cmp = (a.sector || '').localeCompare(b.sector || '', 'ko');
                return state.sortDirection === 'asc' ? cmp : -cmp;
            }
            return 0;
        });
        return sorted;
    }

    function renderTable() {
        var sorted = applySort(state.rankings);
        var past = isPastDate();
        StockTable.setCompareHeader(past);
        StockTable.render(sorted, past);
        StockTable.updateSortIcons(state.sortColumn, state.sortDirection);
    }

    // 데이터 로드
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

                $stockCount.textContent = state.rankings.length + '종목';

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

    // 이벤트
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

    function onTabClick(e) {
        var market = e.target.getAttribute('data-market');
        if (!market) return;
        document.querySelectorAll('.tab').forEach(function (tab) {
            tab.classList.remove('active');
        });
        e.target.classList.add('active');
        state.currentMarket = market;
        loadRankings();
    }

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

    // 초기화
    function init() {
        $datePrev.addEventListener('click', onDatePrev);
        $dateNext.addEventListener('click', onDateNext);

        document.querySelectorAll('.tab').forEach(function (tab) {
            tab.addEventListener('click', onTabClick);
        });

        document.querySelectorAll('.sortable').forEach(function (th) {
            th.addEventListener('click', onSortClick);
        });

        // 뉴스 모달 닫기
        $newsModalClose.addEventListener('click', StockTable.closeNews);
        $newsModal.addEventListener('click', function (e) {
            if (e.target === $newsModal) StockTable.closeNews();
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
