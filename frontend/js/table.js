/**
 * 테이블 렌더링 모듈
 */
var StockTable = (function () {

    /** 숫자를 천단위 콤마 포맷 */
    function formatNumber(n) {
        if (n == null) return '-';
        return n.toLocaleString('ko-KR');
    }

    /** 금액을 억/조 단위로 변환 */
    function formatAmount(n) {
        if (n == null || n === 0) return '-';
        if (n >= 1e12) return (n / 1e12).toFixed(1) + '조';
        if (n >= 1e8) return Math.round(n / 1e8).toLocaleString('ko-KR') + '억';
        if (n >= 1e4) return Math.round(n / 1e4).toLocaleString('ko-KR') + '만';
        return formatNumber(n);
    }

    /** 거래대금을 백만 단위로 표시 */
    function formatTradingValue(n) {
        if (n == null || n === 0) return '-';
        var millions = Math.round(n / 1e6);
        return formatNumber(millions) + '백만';
    }

    /** 등락률 포맷 (+빨강 / -파랑) */
    function formatChange(amount, rate) {
        var sign = amount >= 0 ? '+' : '';
        var cls = amount >= 0 ? 'cell-change--up' : 'cell-change--down';
        var arrow = amount >= 0 ? '\u25B2' : '\u25BC';
        return '<span class="' + cls + '">' +
            arrow + sign + formatNumber(amount) + ' (' + sign + rate.toFixed(2) + '%)' +
            '</span>';
    }

    /** 거래 강도 뱃지 HTML */
    function intensityBadge(intensity) {
        var map = {
            '\uD3ED\uBC1C': 'boom',    // 폭발
            '\uAE09\uC99D': 'surge',   // 급증
            '\uD65C\uBC1C': 'active',  // 활발
            '\uBCF4\uD1B5': 'normal',  // 보통
        };
        var cls = map[intensity] || 'normal';
        return '<span class="intensity-badge intensity-badge--' + cls + '">' + intensity + '</span>';
    }

    /** 호재 점수 뱃지 HTML */
    function scoreBadge(score, detail) {
        var cls;
        if (score >= 70) cls = 'high';
        else if (score >= 40) cls = 'mid';
        else if (score > 0) cls = 'low';
        else cls = 'none';

        var html = '<span class="score-badge score-badge--' + cls + '">' + score + '</span>';

        if (detail) {
            var parsed = (typeof detail === 'string') ? JSON.parse(detail) : detail;
            html += '<div class="score-detail">' +
                'B' + parsed.buzz + ' Q' + parsed.quality +
                ' T' + parsed.type + ' D' + parsed.durability +
                '</div>';
        }
        return html;
    }

    /** 뉴스 목록 HTML */
    function newsCell(news, ticker) {
        if (!news || news.length === 0) {
            return '<span style="color:var(--text-muted)">-</span>';
        }
        var id = 'news-' + ticker;
        var html = '<button class="news-toggle" onclick="StockTable.toggleNews(\'' + id + '\')">' +
            news.length + '건</button>';
        html += '<div class="news-dropdown" id="' + id + '">';
        news.forEach(function (n) {
            html += '<div class="news-item">' +
                '<a href="' + n.link + '" target="_blank" rel="noopener">' + n.title + '</a>' +
                (n.source ? '<span class="news-item__source">' + n.source + '</span>' : '') +
                '</div>';
        });
        html += '</div>';
        return html;
    }

    /** 뉴스 드롭다운 토글 */
    function toggleNews(id) {
        var el = document.getElementById(id);
        if (el) el.classList.toggle('open');
    }

    /** 테이블 전체 렌더링 */
    function render(rankings, isPast) {
        var tbody = document.getElementById('rankingBody');
        if (!tbody) return;

        if (!rankings || rankings.length === 0) {
            tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:40px;color:var(--text-muted);">데이터가 없습니다</td></tr>';
            return;
        }

        var html = '';
        rankings.forEach(function (r) {
            var detailUrl = r.detail_link ||
                'https://finance.naver.com/item/main.naver?code=' + r.ticker;

            html += '<tr>';
            html += '<td class="cell-rank">' + r.rank + '</td>';
            html += '<td class="cell-name">' + r.name +
                '<span class="cell-name__market">' + r.market + '</span></td>';
            html += '<td class="cell-price">' + formatNumber(r.close_price) + '</td>';
            html += '<td class="cell-change">' + formatChange(r.change_amount, r.change_rate) + '</td>';
            html += '<td class="cell-volume">' + formatTradingValue(r.trading_value) +
                intensityBadge(r.trading_intensity) + '</td>';
            html += '<td class="cell-cap">' + formatAmount(r.market_cap) + '</td>';
            html += '<td class="cell-sector">' + (r.sector || '-') + '</td>';
            html += '<td class="cell-reason">' + (r.rise_reason || '-') + '</td>';
            html += '<td style="text-align:center">' + scoreBadge(r.score, r.score_detail) + '</td>';
            html += '<td style="text-align:center">' + newsCell(r.news, r.ticker) + '</td>';
            html += '<td style="text-align:center"><a href="' + detailUrl +
                '" target="_blank" rel="noopener" class="detail-btn">상세</a></td>';

            // 과거 데이터일 때 현재가 비교 컬럼 표시
            if (isPast && r.current_price != null) {
                var diff = ((r.current_price - r.close_price) / r.close_price * 100).toFixed(2);
                var cls = diff > 0 ? 'cell-compare--up' : (diff < 0 ? 'cell-compare--down' : 'cell-compare--neutral');
                var sign = diff > 0 ? '+' : '';
                html += '<td class="cell-compare ' + cls + '">' +
                    formatNumber(r.current_price) + '<br>' +
                    sign + diff + '%</td>';
            }

            html += '</tr>';
        });

        tbody.innerHTML = html;
    }

    /** 과거 데이터용 비교 컬럼 헤더 추가/제거 */
    function setCompareHeader(show) {
        var thead = document.querySelector('#rankingTable thead tr');
        var existing = thead.querySelector('.col-compare');
        if (show && !existing) {
            var th = document.createElement('th');
            th.className = 'col-compare';
            th.textContent = '현재가 비교';
            th.style.width = '110px';
            th.style.textAlign = 'right';
            thead.appendChild(th);
        } else if (!show && existing) {
            existing.remove();
        }
    }

    return {
        render: render,
        toggleNews: toggleNews,
        setCompareHeader: setCompareHeader,
        formatNumber: formatNumber,
        formatAmount: formatAmount,
    };
})();
