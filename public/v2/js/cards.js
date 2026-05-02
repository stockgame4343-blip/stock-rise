/**
 * 카드뉴스 — 최신 랭킹 데이터로 3장(Hero / Top5 / Themes) 생성
 */
(function () {
    var $status = document.getElementById('cardsStatus');

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function formatDate(dstr) {
        if (!dstr || dstr.length !== 8) return '';
        return dstr.substring(0, 4) + '.' + dstr.substring(4, 6) + '.' + dstr.substring(6, 8);
    }

    function formatPrice(v) {
        if (typeof v !== 'number') return '-';
        return v.toLocaleString('ko-KR') + '원';
    }

    function formatTradeValue(v) {
        if (typeof v !== 'number' || v <= 0) return '-';
        if (v >= 1e12) return (v / 1e12).toFixed(1) + '조';
        if (v >= 1e8) return Math.round(v / 1e8).toLocaleString('ko-KR') + '억';
        if (v >= 1e4) return Math.round(v / 1e4).toLocaleString('ko-KR') + '만';
        return v.toLocaleString('ko-KR');
    }

    function formatRate(v) {
        if (typeof v !== 'number') return '-';
        var sign = v >= 0 ? '+' : '';
        return sign + v.toFixed(1) + '%';
    }

    function setText(id, text) {
        var el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    function renderHero(date, top) {
        setText('heroDate', formatDate(date));
        setText('heroName', top.name || '-');
        var sub = [top.market, top.theme_tag].filter(function (x) { return x; }).join(' · ');
        setText('heroTag', sub);
        setText('heroRate', formatRate(top.change_rate));
        setText('heroPrice', formatPrice(top.close_price));
        setText('heroTradeValue', formatTradeValue(top.trading_value));
        setText('heroReason', top.rise_reason || '');
        document.getElementById('cardHero').style.display = '';
    }

    function renderTop5(date, rankings) {
        setText('top5Date', formatDate(date));
        var top5 = rankings.slice(0, 5);
        var html = top5.map(function (s, i) {
            var why = s.theme_tag || s.sector || '';
            return '<div class="c2__item' + (i === 0 ? ' lead' : '') + '">'
                + '<div class="c2__rank">' + (i + 1) + '</div>'
                + '<div class="c2__info">'
                + '<div class="c2__name">' + esc(s.name) + '</div>'
                + '<div class="c2__why">' + esc(why) + '</div>'
                + '</div>'
                + '<div class="c2__rate">' + formatRate(s.change_rate) + '</div>'
                + '</div>';
        }).join('');
        document.getElementById('top5List').innerHTML = html;
        document.getElementById('cardTop5').style.display = '';
    }

    function renderThemes(date, rankings) {
        setText('themesDate', formatDate(date));
        var themeMap = {};
        rankings.forEach(function (s) {
            var t = s.theme_tag;
            if (!t) return;
            if (!themeMap[t]) themeMap[t] = { name: t, stocks: [] };
            themeMap[t].stocks.push(s.name);
        });
        var sorted = Object.keys(themeMap).map(function (k) { return themeMap[k]; });
        sorted.sort(function (a, b) { return b.stocks.length - a.stocks.length; });
        var top3 = sorted.slice(0, 3);
        if (top3.length === 0) {
            document.getElementById('cardThemes').style.display = 'none';
            return;
        }
        var html = top3.map(function (t, i) {
            var stocks = t.stocks.slice(0, 5).join(', ');
            return '<div class="c3__item">'
                + '<div class="c3__item-head">'
                + '<div class="c3__item-rank">' + (i + 1) + '</div>'
                + '<div class="c3__item-name">' + esc(t.name) + '</div>'
                + '<div class="c3__item-count">' + t.stocks.length + '종목</div>'
                + '</div>'
                + '<div class="c3__item-stocks">' + esc(stocks) + '</div>'
                + '</div>';
        }).join('');
        document.getElementById('themesList').innerHTML = html;
        document.getElementById('cardThemes').style.display = '';
    }

    function fail(msg) {
        $status.textContent = msg;
    }

    fetch('/data/dates.json')
        .then(function (r) { return r.json(); })
        .then(function (dates) {
            if (!Array.isArray(dates) || dates.length === 0) throw new Error('날짜 없음');
            var latest = dates[0];
            return fetch('/data/' + latest + '.json').then(function (r) { return r.json(); })
                .then(function (d) { return { date: latest, data: d }; });
        })
        .then(function (res) {
            var rankings = (res.data && res.data.rankings) || [];
            if (rankings.length === 0) {
                fail('데이터가 비어 있습니다.');
                return;
            }
            $status.style.display = 'none';
            renderHero(res.date, rankings[0]);
            renderTop5(res.date, rankings);
            renderThemes(res.date, rankings);
        })
        .catch(function (e) {
            fail('카드뉴스 로딩 실패: ' + (e && e.message ? e.message : e));
        });
})();
