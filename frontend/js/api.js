/**
 * API 통신 모듈
 */
var StockAPI = (function () {
    var BASE = '';

    function fetchJSON(url) {
        return fetch(BASE + url)
            .then(function (res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            });
    }

    /** 조회 가능 날짜 목록 */
    function getDates() {
        return fetchJSON('/api/dates').then(function (data) {
            return data.dates || [];
        });
    }

    /** 최신 수집 날짜 */
    function getLatestDate() {
        return fetchJSON('/api/latest-date').then(function (data) {
            return data.date || null;
        });
    }

    /** 날짜별 상승 순위 */
    function getRankings(date, market) {
        var m = market || 'ALL';
        return fetchJSON('/api/rankings?date=' + date + '&market=' + m);
    }

    /** 현재가 조회 (과거 비교용) */
    function getCurrentPrice(ticker) {
        return fetchJSON('/api/current-price?ticker=' + ticker);
    }

    return {
        getDates: getDates,
        getLatestDate: getLatestDate,
        getRankings: getRankings,
        getCurrentPrice: getCurrentPrice,
    };
})();
