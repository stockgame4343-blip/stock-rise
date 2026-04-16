/**
 * 테이블 렌더링 모듈
 */
var StockTable = (function () {

    var _currentData = [];

    function shortenTheme(name) {
        if (!name) return name;
        var short = name.replace(/\(.*?\)/g, '').trim();
        if (short.indexOf('/') !== -1) short = short.split('/')[0].trim();
        return short || name;
    }

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
            arrow + sign + formatNumber(amount) +
            '<br><span class="change-rate">(' + sign + rate.toFixed(2) + '%)</span>' +
            '</span>';
    }

    function intensityBadge(intensity) {
        var map = {
            '\uC0C1\uD55C\uAC00': 'limit',
            '\uD3ED\uBC1C': 'boom',
            '\uAE09\uC99D': 'surge',
            '\uD65C\uBC1C': 'active',
            '\uBCF4\uD1B5': 'normal',
        };
        var cls = map[intensity] || 'normal';
        return '<span class="intensity-badge intensity-badge--' + cls + '">' + intensity + '</span>';
    }

    function scoreBadge(score, detail, ticker) {
        var cls;
        if (score >= 70) cls = 'high';
        else if (score >= 40) cls = 'mid';
        else if (score > 0) cls = 'low';
        else cls = 'none';

        var html = '<div class="score-click" data-ticker="' + ticker + '">';
        html += '<span class="score-badge score-badge--' + cls + '">' + score + '</span>';

        if (detail) {
            var parsed = (typeof detail === 'string') ? JSON.parse(detail) : detail;
            var parts;
            if (parsed.ti != null) {
                // 대장점수 (v3)
                parts = ['TP' + parsed.tp, 'TL' + parsed.tl, 'TI' + parsed.ti];
            } else {
                // 레거시 호재점수
                parts = ['B' + parsed.buzz, 'Q' + parsed.quality,
                    'T' + parsed.type, 'TV' + (parsed.turnover != null ? parsed.turnover : 0)];
            }
            html += '<div class="score-detail">' + parts.join(' ') + '</div>';
        }
        html += '</div>';
        return html;
    }

    function starRatingHtml(ticker, ratings) {
        var rating = ratings[ticker] || {};
        var stars = rating.stars || 0;
        var excluded = rating.excluded || false;
        var hasMemo = rating.memo ? true : false;
        var hasAny = stars > 0 || excluded || hasMemo;

        var html = '<span class="ctrl-wrap">';

        // 미니 인디케이터 (활성 상태만 종목명 옆에 표시)
        if (hasAny) {
            html += '<span class="mini-indicators">';
            if (stars > 0) html += '<span class="mini-star">\u2605' + stars + '</span>';
            if (excluded) html += '<span class="mini-exclude">\u2715</span>';
            if (hasMemo) html += '<span class="mini-memo">\u270E</span>';
            html += '</span>';
        }

        // 플로팅 컨트롤 패널 (호버 시 표시)
        html += '<div class="float-controls" data-ticker="' + ticker + '">';
        html += '<span class="star-rating" data-ticker="' + ticker + '">';
        for (var i = 1; i <= 5; i++) {
            html += '<span class="star' + (i <= stars ? ' star--active' : '') +
                '" data-star="' + i + '">\u2605</span>';
        }
        html += '</span>';
        html += '<button class="exclude-btn' + (excluded ? ' exclude-btn--active' : '') +
            '" data-ticker="' + ticker + '" title="제외">\u2715</button>';
        html += '<button class="memo-btn' + (hasMemo ? ' memo-btn--has' : '') +
            '" data-ticker="' + ticker + '" title="메모">\u270E</button>';
        html += '</div>';
        html += '</span>';

        return html;
    }

    function openNews(ticker) {
        var stock = null;
        for (var i = 0; i < _currentData.length; i++) {
            if (_currentData[i].ticker === ticker) {
                stock = _currentData[i];
                break;
            }
        }
        if (!stock || !stock.news || stock.news.length === 0) {
            var $modal = document.getElementById('newsModal');
            var $title = document.getElementById('newsModalTitle');
            var $body = document.getElementById('newsModalBody');
            $title.textContent = (stock ? stock.name : ticker) + ' 관련 뉴스';
            $body.innerHTML = '<div class="news-empty">관련 뉴스가 없습니다</div>';
            $modal.style.display = 'flex';
            return;
        }

        var $modal = document.getElementById('newsModal');
        var $title = document.getElementById('newsModalTitle');
        var $body = document.getElementById('newsModalBody');

        $title.textContent = stock.name + ' (' + stock.ticker + ') 관련 뉴스';

        var html = '';
        stock.news.forEach(function (n) {
            html += '<div class="news-item">';
            html += '<a class="news-item__title" href="' + n.link + '" target="_blank" rel="noopener">' +
                n.title + '</a>';
            html += '<span class="news-item__meta">';
            if (n.source) {
                html += '<span class="news-item__source">' + n.source + '</span>';
            }
            if (n.date) {
                html += '<span class="news-item__date">' + n.date + '</span>';
            }
            html += '</span>';
            html += '</div>';
        });

        $body.innerHTML = html;
        $modal.style.display = 'flex';
    }

    function closeNews() {
        document.getElementById('newsModal').style.display = 'none';
    }

    function render(rankings, isPast, ratings) {
        var tbody = document.getElementById('rankingBody');
        if (!tbody) return;

        _currentData = rankings;
        ratings = ratings || {};

        if (!rankings || rankings.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:40px;color:var(--text-muted);">데이터가 없습니다</td></tr>';
            return;
        }

        var html = '';
        rankings.forEach(function (r) {
            var detailUrl = 'https://finance.naver.com/item/main.naver?code=' + r.ticker;
            var ratingData = ratings[r.ticker] || {};
            var isExcluded = ratingData.excluded || false;

            html += '<tr' + (isExcluded ? ' class="row--excluded"' : '') + '>';
            html += '<td class="cell-rank">' + r.rank + '</td>';
            html += '<td class="cell-name"><div class="cell-name__wrap">' +
                '<a href="' + detailUrl + '" target="_blank" rel="noopener" class="cell-name__link">' + r.name + '</a>' +
                '<span class="cell-name__market">' + r.market + '</span>' +
                starRatingHtml(r.ticker, ratings) +
                '</div></td>';
            html += '<td class="cell-price">' + formatNumber(r.close_price) + '</td>';

            // 현재가 비교 (과거일 때만)
            if (isPast && r.current_price != null) {
                var diff = ((r.current_price - r.close_price) / r.close_price * 100).toFixed(2);
                var cls = diff > 0 ? 'cell-compare--up' : (diff < 0 ? 'cell-compare--down' : 'cell-compare--neutral');
                var sign = diff > 0 ? '+' : '';
                html += '<td class="cell-compare ' + cls + '">' +
                    formatNumber(r.current_price) + '<br>' +
                    sign + diff + '%</td>';
            } else if (isPast) {
                html += '<td class="cell-compare cell-compare--neutral">-</td>';
            }

            html += '<td class="cell-change">' + formatChange(r.change_amount, r.change_rate) + '</td>';
            html += '<td class="cell-volume">' + formatTradingValue(r.trading_value) + '</td>';
            html += '<td class="cell-cap">' + formatAmount(r.market_cap) + '</td>';
            html += '<td class="cell-sector">' + (r.sector || '-') + '</td>';
            var rawTag = (ratingData.customTag != null ? ratingData.customTag : r.theme_tag) || '';
            var displayTag = ratingData.customTag != null ? rawTag : shortenTheme(rawTag);
            var isCustom = ratingData.customTag != null && ratingData.customTag !== r.theme_tag;
            var subTag = '';
            if (!isCustom && r.theme_tags && r.theme_tags.length > 1) {
                var sub = shortenTheme(r.theme_tags[1]);
                if (sub !== displayTag) subTag = sub;  // primary와 같으면 스킵
            }
            var reason = r.rise_reason || '-';
            html += '<td class="cell-reason">' +
                '<span class="tag-edit' + (displayTag ? ' theme-tag' : ' tag-edit--empty') +
                (isCustom ? ' theme-tag--custom' : '') +
                '" data-ticker="' + r.ticker + '">' +
                (displayTag || '+') + '</span>' +
                (subTag ? '<span class="theme-tag theme-tag--sub">' + subTag + '</span>' : '') +
                reason + '</td>';
            html += '<td style="text-align:center">' + scoreBadge(r.score, r.score_detail, r.ticker) + '</td>';
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
            // .col-price 뒤에 삽입 (현재가와 전일대비 사이)
            var colPrice = thead.querySelector('.col-price');
            if (colPrice && colPrice.nextSibling) {
                thead.insertBefore(th, colPrice.nextSibling);
            } else {
                thead.appendChild(th);
            }
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
