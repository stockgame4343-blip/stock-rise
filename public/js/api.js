/**
 * API 통신 모듈 (Vercel 정적 JSON + serverless)
 */
var StockAPI = (function () {

    function fetchJSON(url) {
        return fetch(url)
            .then(function (res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            });
    }

    /** 조회 가능 날짜 목록 (정적 JSON) */
    function getDates() {
        return fetchJSON('/data/dates.json');
    }

    /** 날짜별 상승 순위 (정적 JSON + 클라이언트 market 필터링) */
    function getRankings(date, market) {
        return fetchJSON('/data/' + date + '.json')
            .then(function (data) {
                var m = market || 'ALL';
                var rankings = data.rankings || [];

                if (m !== 'ALL') {
                    rankings = rankings.filter(function (r) {
                        return r.market === m;
                    });
                }

                return {
                    rankings: rankings,
                    collected_at: data.collected_at || '',
                    is_final: data.is_final || false,
                    mode: data.mode || 'closing',
                };
            });
    }

    /** 현재가 조회 — Vercel serverless (과거 비교용) */
    function getCurrentPrice(ticker) {
        return fetchJSON('/api/current-price?ticker=' + ticker);
    }

    return {
        getDates: getDates,
        getRankings: getRankings,
        getCurrentPrice: getCurrentPrice,
    };
})();
