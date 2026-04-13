/**
 * 앱 상태 관리 및 이벤트 바인딩
 */
(function () {
    // ── 상태 ──
    var state = {
        dates: [],
        dateIndex: 0,
        currentMarket: 'ALL',
        latestDate: null,
        rankings: [],
    };

    // ── DOM 요소 ──
    var $dateDisplay = document.getElementById('dateDisplay');
    var $datePrev = document.getElementById('datePrev');
    var $dateNext = document.getElementById('dateNext');
    var $stockCount = document.getElementById('stockCount');
    var $statusInfo = document.getElementById('statusInfo');
    var $loading = document.getElementById('loading');
    var $message = document.getElementById('message');
    var $modalOverlay = document.getElementById('priceModal');
    var $modalClose = document.getElementById('modalClose');

    // ── 유틸 ──
    function formatDateDisplay(dateStr) {
        if (!dateStr || dateStr.length !== 8) return dateStr || '-';
        return dateStr.substring(0, 4) + '.' + dateStr.substring(4, 6) + '.' + dateStr.substring(6, 8);
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

    // ── 데이터 로드 ──
    function loadRankings() {
        var date = state.dates[state.dateIndex];
        if (!date) return;

        showLoading(true);
        showMessage('');

        $dateDisplay.textContent = formatDateDisplay(date);

        StockAPI.getRankings(date, state.currentMarket)
            .then(function (data) {
                showLoading(false);
                state.rankings = data.rankings || [];

                $stockCount.textContent = state.rankings.length + '종목';
                $statusInfo.textContent = isPastDate() ? '(과거 데이터)' : '';

                var past = isPastDate();
                StockTable.setCompareHeader(past);

                if (past) {
                    fetchCurrentPrices(state.rankings).then(function (updated) {
                        StockTable.render(updated, true);
                    });
                } else {
                    StockTable.render(state.rankings, false);
                }
            })
            .catch(function (err) {
                showLoading(false);
                showMessage('데이터를 불러올 수 없습니다.');
                console.error(err);
            });
    }

    /** 과거 데이터 조회 시 현재가를 일괄 조회하여 매칭 */
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

        // 5개씩 순차 배치 처리 (서버 부하 방지)
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

    // ── 이벤트 핸들러 ──
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

    function onModalClose() {
        $modalOverlay.style.display = 'none';
    }

    // ── 초기화 ──
    function init() {
        $datePrev.addEventListener('click', onDatePrev);
        $dateNext.addEventListener('click', onDateNext);
        $modalClose.addEventListener('click', onModalClose);

        document.querySelectorAll('.tab').forEach(function (tab) {
            tab.addEventListener('click', onTabClick);
        });

        $modalOverlay.addEventListener('click', function (e) {
            if (e.target === $modalOverlay) onModalClose();
        });

        showLoading(true);

        StockAPI.getDates()
            .then(function (dates) {
                if (!dates || dates.length === 0) {
                    showLoading(false);
                    showMessage('수집된 데이터가 없습니다. 서버에서 데이터 수집을 실행해주세요.');
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

    // DOM 로드 후 초기화
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
