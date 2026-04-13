/**
 * 테이블 렌더링 모듈
 */
var StockTable = (function () {

    var _currentData = [];

    function formatNumber(n) {
        if (n == null) return '-';
        return n.toLocaleString('ko-KR');
    }

    function formatAmount(n) {
        if (n == null || n === 0) return '-';
        if (n >= 1e12) return (n / 1e12).toFixed(1) + '조';
        if (n >= 1e8) return Math.round(n / 1e8).toLocaleString('ko-KR') + '억';
        if (n >= 1e4) return Math.round(n / 1e4).toLocaleString('ko-KR') + '만';
        return formatNumber(n);
    }

    function formatTradingValue(n) {
        if (n == null || n === 0) return '-';
        var millions = Math.round(n / 1e6);
        return formatNumber(millions) + '백만';
    }

    function formatChange(amount, rate) {
        var sign = amount >= 0 ? '+' : '';
        var cls = amount >= 0 ? 'cell-change--up' : 'cell-change--down';
        var arrow = amount >= 0 ? '\u25B2' : '\u25BC';
        return '<span class="' + cls + '">' +
            arrow + sign + formatNumber(amount) + ' (' + sign + rate.toFixed(2) + '%)' +
            '</span>';
    }

    function intensityBadge(intensity) {
        var map = {
            '\uD3ED\uBC1C': 'boom',
            '\uAE09\uC99D': 'surge',
            '\uD65C\uBC1C': 'active',
            '\uBCF4\uD1B5': 'normal',
        };
        var cls = map[intensity] || 'normal';
        return '<span class="intensity-badge intensity-badge--' + cls + '">' + intensity + '</span>';
    }

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

    function newsCell(news, ticker) {
        if (!news || news.length === 0) {
            return '<span style="color:var(--text-muted)">-</span>';
        }
        return '<button class="news-btn" onclick="StockTable.openNews(\'' + ticker + '\')">' +
            news.length + '건</button>';
    }

    function openNews(ticker) {
        var stock = null;
        for (var i = 0; i < _currentData.length; i++) {
            if (_currentData[i].ticker === ticker) {
                stock = _currentData[i];
                break;
            }
        }
        if (!stock || !stock.news || stock.news.length === 0) return;

        var $modal = document.getElementById('newsModal');
        var $title = document.getElementById('newsModalTitle');
        var $body = document.getElementById('newsModalBody');

        $title.textContent = stock.name + ' (' + stock.ticker + ') 관련 뉴스';

        var html = '';
        stock.news.forEach(function (n) {
            html += '<div class="news-item">';
            html += '<a class="news-item__title" href="' + n.link + '" target="_blank" rel="noopener">' +
                n.title + '</a>';
            if (n.source) {
                html += '<span class="news-item__source">' + n.source + '</span>';
            }
            html += '</div>';
        });

        $body.innerHTML = html;
        $modal.style.display = 'flex';
    }

    function closeNews() {
        document.getElementById('newsModal').style.display = 'none';
    }

    function render(rankings, isPast) {
        var tbody = document.getElementById('rankingBody');
        if (!tbody) return;

        _currentData = rankings;

        if (!rankings || rankings.length === 0) {
            tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:40px;color:var(--text-muted);">데이터가 없습니다</td></tr>';
            return;
        }

        var html = '';
        rankings.forEach(function (r) {
            var detailUrl = 'https://finance.naver.com/item/main.naver?code=' + r.ticker;

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
                '" target="_blank" rel="noopener" class="naver-n">N</a></td>';

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

    function updateSortIcons(column, direction) {
        var icons = document.querySelectorAll('.sort-icon');
        icons.forEach(function (icon) {
            var th = icon.closest('th');
            var col = th ? th.getAttribute('data-sort') : null;
            if (col === column && direction) {
                icon.classList.add('sort-icon--active');
                icon.innerHTML = direction === 'asc' ? '&#9650;' : '&#9660;';
            } else {
                icon.classList.remove('sort-icon--active');
                icon.innerHTML = '&#9660;';
            }
        });
    }

    return {
        render: render,
        openNews: openNews,
        closeNews: closeNews,
        setCompareHeader: setCompareHeader,
        updateSortIcons: updateSortIcons,
        formatNumber: formatNumber,
        formatAmount: formatAmount,
    };
})();
