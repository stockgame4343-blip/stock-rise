/**
 * 데일리 리포트 페이지 로직
 */
(function () {
    var DAYS_KO = ['일', '월', '화', '수', '목', '금', '토'];
    var THEME_KEY = 'theme';
    var RATINGS_KEY = 'stock-ratings';
    var STOCK_INITIAL = 5;
    var STOCK_MORE = 15;

    var state = {
        dates: [],
        dateIndex: 0,
        allRankings: [],
        allTopStocks: [],
        stocksShown: STOCK_INITIAL,
    };

    // DOM
    var $reportTitle = document.getElementById('reportTitle');
    var $loading = document.getElementById('loading');
    var $message = document.getElementById('message');
    var $content = document.getElementById('reportContent');
    var $datePrev = document.getElementById('datePrev');
    var $dateNext = document.getElementById('dateNext');
    var $lastUpdated = document.getElementById('lastUpdated');
    var $stockMoreBtn = document.getElementById('stockMoreBtn');

    // ── 유틸 ──
    function formatDateKorean(ds) {
        var y = ds.substring(0, 4);
        var m = parseInt(ds.substring(4, 6), 10);
        var d = parseInt(ds.substring(6, 8), 10);
        var dt = new Date(+y, m - 1, +d);
        return m + '월 ' + d + '일 (' + DAYS_KO[dt.getDay()] + ')';
    }

    function formatNumber(n) {
        if (n == null) return '-';
        return n.toLocaleString('ko-KR');
    }

    function formatAmount(n) {
        if (n == null || n === 0) return '-';
        if (n >= 1e12) return (n / 1e12).toFixed(1) + '조';
        if (n >= 1e8) return Math.round(n / 1e8).toLocaleString('ko-KR') + '억';
        return formatNumber(n);
    }

    function daysSince(dateStr, currentDate) {
        if (!dateStr || dateStr.length < 8) return -1;
        var y1 = +currentDate.substring(0,4), m1 = +currentDate.substring(4,6)-1, d1 = +currentDate.substring(6,8);
        var y2 = +dateStr.substring(0,4), m2 = +dateStr.substring(4,6)-1, d2 = +dateStr.substring(6,8);
        return Math.round((new Date(y1,m1,d1) - new Date(y2,m2,d2)) / 86400000);
    }

    function showLoading(v) {
        $loading.style.display = v ? 'block' : 'none';
        $content.style.display = v ? 'none' : 'block';
    }
    function showMessage(msg) {
        $message.style.display = msg ? 'block' : 'none';
        $message.textContent = msg;
    }

    function filterGoodNews(newsList) {
        return newsList.filter(function (n) {
            return n.title.indexOf('서울데이터랩') === -1;
        });
    }

    // ── localStorage 레이팅 ──
    function getRatings() {
        try { return JSON.parse(localStorage.getItem(RATINGS_KEY) || '{}'); }
        catch (e) { return {}; }
    }
    function saveRatings(r) {
        localStorage.setItem(RATINGS_KEY, JSON.stringify(r));
    }
    function controlsHtml(ticker, ratings) {
        var rd = ratings[ticker] || {};
        var stars = rd.stars || 0;
        var excluded = rd.excluded || false;
        var hasMemo = rd.memo ? true : false;
        var hasAny = stars > 0 || excluded || hasMemo;

        var html = '<span class="ctrl-wrap">';
        if (hasAny) {
            html += '<span class="mini-indicators">';
            if (stars > 0) html += '<span class="mini-star">\u2605' + stars + '</span>';
            if (excluded) html += '<span class="mini-exclude">\u2715</span>';
            if (hasMemo) html += '<span class="mini-memo">\u270E</span>';
            html += '</span>';
        }
        html += '<div class="float-controls" data-ticker="' + ticker + '">';
        html += '<span class="star-rating" data-ticker="' + ticker + '">';
        for (var i = 1; i <= 5; i++) {
            html += '<span class="star' + (i <= stars ? ' star--active' : '') + '" data-star="' + i + '">\u2605</span>';
        }
        html += '</span>';
        html += '<button class="exclude-btn' + (excluded ? ' exclude-btn--active' : '') + '" data-ticker="' + ticker + '" title="\uC81C\uC678">\u2715</button>';
        html += '<button class="memo-btn' + (hasMemo ? ' memo-btn--has' : '') + '" data-ticker="' + ticker + '" title="\uBA54\uBAA8">\u270E</button>';
        html += '</div></span>';
        return html;
    }

    function refreshControlsUI(ticker) {
        var ratings = getRatings();
        var rd = ratings[ticker] || {};
        var stars = rd.stars || 0;
        var excluded = !!rd.excluded;
        var hasMemo = !!rd.memo;
        var hasAny = stars > 0 || excluded || hasMemo;

        document.querySelectorAll('.float-controls[data-ticker="' + ticker + '"]').forEach(function (fc) {
            fc.querySelectorAll('.star').forEach(function (s, i) {
                s.classList.toggle('star--active', i < stars);
            });
            var ex = fc.querySelector('.exclude-btn');
            if (ex) ex.classList.toggle('exclude-btn--active', excluded);
            var memo = fc.querySelector('.memo-btn');
            if (memo) memo.classList.toggle('memo-btn--has', hasMemo);

            var wrap = fc.closest('.ctrl-wrap');
            if (!wrap) return;
            var oldMini = wrap.querySelector('.mini-indicators');
            if (oldMini) oldMini.remove();
            if (hasAny) {
                var m = '<span class="mini-indicators">';
                if (stars > 0) m += '<span class="mini-star">\u2605' + stars + '</span>';
                if (excluded) m += '<span class="mini-exclude">\u2715</span>';
                if (hasMemo) m += '<span class="mini-memo">\u270E</span>';
                m += '</span>';
                fc.insertAdjacentHTML('beforebegin', m);
            }
        });
    }

    // 점수 레벨 텍스트
    function buzzLevel(v) {
        if (v >= 18) return '매우 많음';
        if (v >= 13) return '많음';
        if (v >= 8) return '보통';
        if (v >= 4) return '적음';
        return '거의 없음';
    }
    function qualityLevel(v) {
        if (v >= 20) return '매우 높음';
        if (v >= 15) return '높음';
        if (v >= 10) return '보통';
        if (v >= 5) return '낮음';
        return '매우 낮음';
    }
    function typeLevel(v) {
        if (v >= 25) return '핵심 호재';
        if (v >= 15) return '보통 호재';
        if (v >= 5) return '약한 호재';
        return '미분류';
    }
    function turnoverLevel(v) {
        if (v >= 23) return '폭발적';
        if (v >= 18) return '매우 활발';
        if (v >= 12) return '활발';
        if (v >= 6) return '보통';
        return '평이';
    }

    // ── 테마 토글 (공통) ──
    var $themeToggle = document.getElementById('themeToggle');
    function applyThemeIcon() {
        var isDark = !document.documentElement.hasAttribute('data-theme');
        $themeToggle.innerHTML = isDark
            ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
            : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>';
    }
    function toggleTheme() {
        var isDark = !document.documentElement.hasAttribute('data-theme');
        if (isDark) {
            document.documentElement.setAttribute('data-theme', 'light');
            localStorage.setItem(THEME_KEY, 'light');
        } else {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem(THEME_KEY, 'dark');
        }
        applyThemeIcon();
    }
    $themeToggle.addEventListener('click', toggleTheme);
    applyThemeIcon();

    // ── 데이터 분석 ──
    function analyzeData(rankings) {
        var result = {};

        // 1) 요약
        var totalCount = rankings.length;
        var avgRate = rankings.reduce(function (s, r) { return s + r.change_rate; }, 0) / totalCount;
        var limitUp = rankings.filter(function (r) { return r.change_rate >= 29.9; }).length;
        var totalVolume = rankings.reduce(function (s, r) { return s + (r.trading_value || 0); }, 0);
        result.summary = { count: totalCount, avgRate: avgRate, limitUp: limitUp, totalVolume: totalVolume };

        // 2) 섹터 분석
        var sectorMap = {};
        rankings.forEach(function (r) {
            var sec = r.sector || '기타';
            if (!sectorMap[sec]) sectorMap[sec] = { name: sec, stocks: [], totalRate: 0, totalVolume: 0 };
            sectorMap[sec].stocks.push(r);
            sectorMap[sec].totalRate += r.change_rate;
            sectorMap[sec].totalVolume += (r.trading_value || 0);
        });
        result.sectors = Object.values(sectorMap)
            .filter(function (s) { return s.stocks.length >= 2; })
            .map(function (s) {
                s.avgRate = s.totalRate / s.stocks.length;
                s.stocks.sort(function (a, b) { return b.change_rate - a.change_rate; });
                return s;
            })
            .sort(function (a, b) { return b.stocks.length - a.stocks.length; })
            .slice(0, 5);

        // 3) 테마 분석
        var themeMap = {};
        rankings.forEach(function (r) {
            if (!r.theme_tag) return;
            var tags = r.theme_tag.split(/[,\/]/).map(function (t) { return t.trim(); }).filter(Boolean);
            tags.forEach(function (tag) {
                if (!themeMap[tag]) themeMap[tag] = { name: tag, count: 0, totalRate: 0, totalVolume: 0, stocks: [] };
                themeMap[tag].count++;
                themeMap[tag].totalRate += r.change_rate;
                themeMap[tag].totalVolume += (r.trading_value || 0);
                themeMap[tag].stocks.push(r);
            });
        });
        result.themes = Object.values(themeMap)
            .filter(function (t) { return t.count >= 2; })
            .map(function (t) {
                t.avgRate = t.totalRate / t.count;
                t.stocks.sort(function (a, b) { return b.change_rate - a.change_rate; });
                return t;
            })
            .sort(function (a, b) { return b.count - a.count; })
            .slice(0, 5);

        // 4) 주목 종목 (점수 TOP 15)
        result.topStocks = rankings.slice()
            .sort(function (a, b) { return b.score - a.score; })
            .slice(0, STOCK_MORE);

        // 5) 52주 신고가 / 근접
        var highList = [];
        var nearHighList = [];
        rankings.forEach(function (r) {
            var h = r.high_52w || 0;
            if (h <= 0) return;
            var ratio = r.close_price / h;
            if (ratio >= 1.0) {
                highList.push({ stock: r, ratio: ratio });
            } else if (ratio >= 0.9) {
                nearHighList.push({ stock: r, ratio: ratio, gap: ((1 - ratio) * 100).toFixed(1) });
            }
        });
        highList.sort(function (a, b) { return b.stock.change_rate - a.stock.change_rate; });
        nearHighList.sort(function (a, b) { return a.gap - b.gap; });
        result.highList = highList;
        result.nearHighList = nearHighList;

        return result;
    }

    // ── 급등 후 조정 분석 (과거 데이터 비교) ──
    function analyzePullbacks(currentDate, allDates) {
        // 과거 30일 데이터에서 20%+ 급등 또는 신고가 돌파 종목 찾기
        var pastDates = allDates.filter(function (d) { return d < currentDate; }).slice(0, 30);
        if (pastDates.length === 0) return Promise.resolve([]);

        var peakStocks = {}; // ticker → { name, peakPrice, peakDate, reason }

        var promises = pastDates.map(function (date) {
            return StockAPI.getRankings(date, 'ALL')
                .then(function (data) {
                    (data.rankings || []).forEach(function (r) {
                        var dominated = r.change_rate >= 20;
                        var hitHigh = r.high_52w > 0 && r.close_price >= r.high_52w;
                        if (!dominated && !hitHigh) return;

                        var existing = peakStocks[r.ticker];
                        if (!existing || r.close_price > existing.peakPrice) {
                            peakStocks[r.ticker] = {
                                name: r.name,
                                market: r.market,
                                sector: r.sector,
                                peakPrice: r.close_price,
                                peakDate: date,
                                reason: dominated ? '+' + r.change_rate.toFixed(1) + '% 급등' : '52주 신고가',
                            };
                        }
                    });
                })
                .catch(function () {});
        });

        return Promise.all(promises).then(function () {
            // 현재가 조회 (배치)
            var tickers = Object.keys(peakStocks);
            if (tickers.length === 0) return [];

            var pricePromises = tickers.map(function (ticker) {
                return StockAPI.getCurrentPrice(ticker)
                    .then(function (data) {
                        return { ticker: ticker, price: data.price };
                    })
                    .catch(function () {
                        return { ticker: ticker, price: null };
                    });
            });

            return batchProcess(pricePromises, 5).then(function (prices) {
                var pullbacks = [];
                prices.forEach(function (p) {
                    if (!p.price) return;
                    var peak = peakStocks[p.ticker];
                    var dropPct = ((peak.peakPrice - p.price) / peak.peakPrice * 100);
                    if (dropPct >= 25) {
                        pullbacks.push({
                            ticker: p.ticker,
                            name: peak.name,
                            market: peak.market,
                            sector: peak.sector,
                            peakPrice: peak.peakPrice,
                            peakDate: peak.peakDate,
                            currentPrice: p.price,
                            dropPct: dropPct,
                            reason: peak.reason,
                        });
                    }
                });
                pullbacks.sort(function (a, b) { return b.dropPct - a.dropPct; });
                return pullbacks;
            });
        });
    }

    function batchProcess(promises, batchSize) {
        var results = [];
        var batches = [];
        for (var i = 0; i < promises.length; i += batchSize) {
            batches.push(promises.slice(i, i + batchSize));
        }
        var chain = Promise.resolve();
        batches.forEach(function (batch) {
            chain = chain.then(function () {
                return Promise.all(batch).then(function (batchResults) {
                    results = results.concat(batchResults);
                });
            });
        });
        return chain.then(function () { return results; });
    }

    // ── 렌더링 ──
    function renderSummary(summary) {
        document.getElementById('sumCount').textContent = summary.count + '개';
        document.getElementById('sumAvgRate').textContent = '+' + summary.avgRate.toFixed(2) + '%';
        document.getElementById('sumLimit').textContent = summary.limitUp + '종목';
        document.getElementById('sumVolume').textContent = formatAmount(summary.totalVolume);
    }

    function renderSectorCard(items, container, ratings) {
        ratings = ratings || getRatings();
        var html = '';
        items.forEach(function (sec, i) {
            var topStocks = sec.stocks.slice(0, 3);
            html += '<div class="sector-card">';
            html += '<div class="sector-card__header">';
            html += '<span class="sector-card__rank">' + (i + 1) + '</span>';
            html += '<span class="sector-card__name">' + sec.name + '</span>';
            html += '<span class="sector-card__count">' + sec.stocks.length + '종목</span>';
            html += '</div>';
            html += '<div class="sector-card__stats">';
            html += '<span class="sector-card__rate">평균 +' + sec.avgRate.toFixed(2) + '%</span>';
            html += '<span class="sector-card__volume">거래대금 ' + formatAmount(sec.totalVolume) + '</span>';
            html += '</div>';
            html += '<div class="sector-card__stocks">';
            topStocks.forEach(function (s) {
                html += '<div class="sector-card__stock">';
                html += '<span class="sector-card__stock-name">' + s.name + controlsHtml(s.ticker, ratings) + '</span>';
                html += '<span class="sector-card__stock-rate">+' + s.change_rate.toFixed(2) + '%</span>';
                html += '</div>';
            });
            if (sec.stocks.length > 3) {
                html += '<span class="sector-card__more">외 ' + (sec.stocks.length - 3) + '종목</span>';
            }
            html += '</div>';
            html += '</div>';
        });
        container.innerHTML = html;
    }

    function renderThemes(themes, ratings) {
        var c = document.getElementById('themeCards');
        if (themes.length === 0) { c.innerHTML = '<p class="report__empty">테마 태그가 없습니다</p>'; return; }
        renderSectorCard(themes, c, ratings);
    }

    function renderTopStocks(stocks, limit, ratings) {
        ratings = ratings || getRatings();
        var show = stocks.slice(0, limit);
        var container = document.getElementById('stockCards');
        var html = '';
        show.forEach(function (s, i) {
            var naverUrl = 'https://finance.naver.com/item/main.naver?code=' + s.ticker;
            var detail = s.score_detail || {};
            var bz = detail.buzz || 0, qu = detail.quality || 0;
            var ty = detail.type || 0, tv = detail.turnover || 0;

            html += '<div class="stock-card">';
            html += '<div class="stock-card__top">';
            html += '<span class="stock-card__rank">' + (i + 1) + '</span>';
            html += '<div class="stock-card__info">';
            html += '<span class="stock-card__name">' + s.name + controlsHtml(s.ticker, ratings) + '</span>';
            html += '<span class="stock-card__market">' + s.market + ' &middot; ' + (s.sector || '-') + '</span>';
            html += '</div>';
            html += '<div class="stock-card__numbers">';
            html += '<span class="stock-card__rate">+' + s.change_rate.toFixed(2) + '%</span>';
            html += '<span class="stock-card__price">' + formatNumber(s.close_price) + '원</span>';
            html += '</div>';
            html += '</div>';

            if (s.rise_reason) {
                var reason = s.rise_reason;
                // theme_tag가 rise_reason에 포함되지 않은 경우에만 태그 표시
                var showTag = s.theme_tag && reason.indexOf(s.theme_tag) === -1;
                html += '<div class="stock-card__reason">';
                if (showTag) html += '<span class="theme-tag">' + s.theme_tag + '</span>';
                html += '<span>' + reason + '</span>';
                html += '</div>';
            }

            // 호재점수 상세 분석
            var cls = s.score >= 70 ? 'high' : (s.score >= 40 ? 'mid' : 'low');
            html += '<div class="score-analysis">';
            html += '<div class="score-analysis__header">';
            html += '<span class="score-analysis__title">호재점수 분석</span>';
            html += '<span class="score-badge score-badge--' + cls + '">' + s.score + '</span>';
            html += '</div>';
            html += '<div class="score-analysis__grid">';
            html += scoreItem('뉴스 양', bz, 20, buzzLevel(bz), '중복 제거 후 관련 뉴스 건수');
            html += scoreItem('뉴스 질', qu, 25, qualityLevel(qu), '주요 언론사, 수치 포함 여부');
            html += scoreItem('호재 강도', ty, 30, typeLevel(ty), '테마 연동, 호재 유형 분석');
            html += scoreItem('거래량 강도', tv, 25, turnoverLevel(tv), '시총 대비 거래대금 비율');
            html += '</div></div>';

            // 뉴스 3건
            if (s.news && s.news.length > 0) {
                var goodNews = filterGoodNews(s.news);
                var showNews = (goodNews.length > 0 ? goodNews : s.news).slice(0, 3);
                html += '<div class="stock-card__news-list">';
                showNews.forEach(function (n) {
                    html += '<a class="stock-card__news" href="' + n.link + '" target="_blank" rel="noopener">';
                    html += '<span class="stock-card__news-title">' + n.title + '</span>';
                    if (n.source) html += '<span class="stock-card__news-source">' + n.source + '</span>';
                    html += '</a>';
                });
                html += '</div>';
                var newsUrl = 'https://finance.naver.com/item/news.naver?code=' + s.ticker;
                html += '<div class="stock-card__links">';
                html += '<a class="stock-card__link" href="' + newsUrl + '" target="_blank" rel="noopener">뉴스 더보기</a>';
                html += '<a class="stock-card__link stock-card__link--naver" href="' + naverUrl + '" target="_blank" rel="noopener">네이버 금융에서 보기</a>';
                html += '</div>';
            } else {
                html += '<div class="stock-card__links">';
                html += '<a class="stock-card__link stock-card__link--naver" href="' + naverUrl + '" target="_blank" rel="noopener">네이버 금융에서 보기</a>';
                html += '</div>';
            }
            html += '</div>';
        });
        container.innerHTML = html;

        if (stocks.length > limit) {
            $stockMoreBtn.style.display = 'block';
            $stockMoreBtn.textContent = '더보기 (' + (stocks.length - limit) + '종목)';
        } else {
            $stockMoreBtn.style.display = 'none';
        }
    }

    function scoreItem(label, val, max, level, desc) {
        var pct = Math.round(val / max * 100);
        return '<div class="score-analysis__item">' +
            '<div class="score-analysis__item-header">' +
            '<span class="score-analysis__item-label">' + label + '</span>' +
            '<span class="score-analysis__item-score">' + val + '<span class="score-analysis__item-max">/' + max + '</span></span>' +
            '</div>' +
            '<div class="score-analysis__bar"><div class="score-analysis__fill" style="width:' + pct + '%"></div></div>' +
            '<span class="score-analysis__desc">' + level + ' — ' + desc + '</span>' +
            '</div>';
    }

    // ── 52주 신고가 렌더링 (돌파 + 근접 통합, 2칼럼) ──
    function renderHighSection(highList, nearHighList, currentDate, ratings) {
        ratings = ratings || getRatings();
        var container = document.getElementById('highList');
        if (highList.length === 0 && nearHighList.length === 0) {
            container.innerHTML = '<div class="compact-list"><p class="report__empty">52주 신고가 데이터가 아직 수집되지 않았습니다.</p></div>';
            return;
        }

        // 근접: 최근 고점 순 (days asc)
        nearHighList.sort(function (a, b) {
            var daysA = a.stock.high_52w_date ? daysSince(a.stock.high_52w_date, currentDate) : 9999;
            var daysB = b.stock.high_52w_date ? daysSince(b.stock.high_52w_date, currentDate) : 9999;
            if (daysA !== daysB) return daysA - daysB;
            return parseFloat(a.gap) - parseFloat(b.gap);
        });

        var html = '<div class="compact-list compact-list--grid">';

        // 돌파 먼저
        highList.forEach(function (item) {
            var s = item.stock;
            var url = 'https://finance.naver.com/item/main.naver?code=' + s.ticker;
            html += '<a class="compact-row" href="' + url + '" target="_blank" rel="noopener">';
            html += '<span class="compact-row__name">' + s.name + '<span class="compact-row__market">' + s.market + '</span>' + controlsHtml(s.ticker, ratings) + '</span>';
            html += '<span class="compact-row__tag--break">52주 최고가 돌파</span>';
            html += '<span class="compact-row__rate compact-row__rate--up">+' + s.change_rate.toFixed(2) + '%</span>';
            html += '</a>';
        });

        // 근접: 최근 → 과거 순
        nearHighList.forEach(function (item) {
            var s = item.stock;
            var url = 'https://finance.naver.com/item/main.naver?code=' + s.ticker;
            var daysText = '';
            if (s.high_52w_date) {
                var days = daysSince(s.high_52w_date, currentDate);
                if (days >= 0) daysText = days + '일 전 ';
            }
            html += '<a class="compact-row" href="' + url + '" target="_blank" rel="noopener">';
            html += '<span class="compact-row__name">' + s.name + '<span class="compact-row__market">' + s.market + '</span>' + controlsHtml(s.ticker, ratings) + '</span>';
            html += '<span class="compact-row__tag">' + daysText + '고점 대비 -' + item.gap + '%</span>';
            html += '<span class="compact-row__rate compact-row__rate--up">+' + s.change_rate.toFixed(2) + '%</span>';
            html += '</a>';
        });

        html += '</div>';
        container.innerHTML = html;
    }

    function renderPullbacks(pullbacks, ratings) {
        ratings = ratings || getRatings();
        var container = document.getElementById('pullbackList');
        if (pullbacks.length === 0) {
            container.innerHTML = '<div class="compact-list"><p class="report__empty">조건에 해당하는 종목이 없습니다</p></div>';
            return;
        }
        var html = '<div class="compact-list">';
        pullbacks.forEach(function (p) {
            var url = 'https://finance.naver.com/item/main.naver?code=' + p.ticker;
            html += '<a class="compact-row" href="' + url + '" target="_blank" rel="noopener">';
            html += '<span class="compact-row__name">' + p.name + '<span class="compact-row__market">' + p.market + '</span>' + controlsHtml(p.ticker, ratings) + '</span>';
            html += '<span class="compact-row__detail">';
            html += '<span class="compact-row__peak">고점 ' + formatNumber(p.peakPrice) + '</span>';
            html += '<span class="compact-row__arrow">&rarr;</span>';
            html += '<span class="compact-row__current">현재 ' + formatNumber(p.currentPrice) + '</span>';
            html += '</span>';
            html += '<span class="compact-row__rate compact-row__rate--down">-' + p.dropPct.toFixed(1) + '%</span>';
            html += '<span class="compact-row__tag">' + p.reason + ' (' + formatDateKorean(p.peakDate) + ')</span>';
            html += '</a>';
        });
        html += '</div>';
        container.innerHTML = html;
    }

    // ── 데이터 로드 ──
    function loadReport() {
        var date = state.dates[state.dateIndex];
        if (!date) return;

        showLoading(true);
        showMessage('');
        $reportTitle.textContent = formatDateKorean(date) + ' 데일리 리포트';
        $dateNext.disabled = state.dateIndex <= 0;
        $datePrev.disabled = state.dateIndex >= state.dates.length - 1;

        StockAPI.getRankings(date, 'ALL')
            .then(function (data) {
                showLoading(false);
                if (!data.rankings || data.rankings.length === 0) {
                    showMessage('해당 날짜의 데이터가 없습니다.');
                    $content.style.display = 'none';
                    return;
                }

                if (data.collected_at && $lastUpdated) {
                    var d = new Date(data.collected_at);
                    var hh = String(d.getHours()).padStart(2, '0');
                    var mm = String(d.getMinutes()).padStart(2, '0');
                    var label = data.is_final ? '장마감' : '장중';
                    $lastUpdated.textContent = label + ' ' + hh + ':' + mm + ' 수집';
                }

                var analysis = analyzeData(data.rankings);
                state.allRankings = data.rankings;
                state.allTopStocks = analysis.topStocks;
                state.stocksShown = STOCK_INITIAL;
                var ratings = getRatings();

                renderSummary(analysis.summary);
                renderSectorCard(analysis.sectors, document.getElementById('sectorCards'), ratings);
                renderThemes(analysis.themes, ratings);
                renderTopStocks(analysis.topStocks, STOCK_INITIAL, ratings);
                renderHighSection(analysis.highList, analysis.nearHighList, date, ratings);

                // 급등 후 조정 (비동기)
                document.getElementById('pullbackList').innerHTML = '<p class="report__empty" style="padding:16px">조정 종목 분석 중...</p>';
                analyzePullbacks(date, state.dates).then(function (pullbacks) {
                    renderPullbacks(pullbacks, getRatings());
                });
            })
            .catch(function () {
                showLoading(false);
                showMessage('데이터를 불러올 수 없습니다.');
                $content.style.display = 'none';
            });
    }

    // ── 메모 모달 (리포트) ──
    var $memoModal = document.getElementById('memoModal');
    var $memoModalClose = document.getElementById('memoModalClose');
    var $memoModalTitle = document.getElementById('memoModalTitle');
    var $memoTextarea = document.getElementById('memoTextarea');
    var $memoSave = document.getElementById('memoSave');
    var $memoDelete = document.getElementById('memoDelete');
    var _memoTicker = null;

    function openMemo(ticker) {
        _memoTicker = ticker;
        var ratings = getRatings();
        var rd = ratings[ticker] || {};
        var name = '';
        for (var i = 0; i < state.allRankings.length; i++) {
            if (state.allRankings[i].ticker === ticker) { name = state.allRankings[i].name; break; }
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
        ratings[_memoTicker].memo = $memoTextarea.value.trim();
        saveRatings(ratings);
        closeMemo();
        refreshControlsUI(_memoTicker);
    }
    function deleteMemo() {
        if (!_memoTicker) return;
        var ratings = getRatings();
        if (ratings[_memoTicker]) ratings[_memoTicker].memo = '';
        saveRatings(ratings);
        closeMemo();
        refreshControlsUI(_memoTicker);
    }

    // ── 이벤트 위임 (별점, X, 메모) — 리포트 전체 영역 ──
    document.getElementById('reportContent').addEventListener('click', function (e) {
        var starEl = e.target.closest('.star');
        if (starEl) {
            e.preventDefault();
            e.stopPropagation();
            var sr = starEl.closest('.star-rating');
            if (!sr) return;
            var ticker = sr.getAttribute('data-ticker');
            var starNum = parseInt(starEl.getAttribute('data-star'));
            if (!ticker || isNaN(starNum)) return;
            var ratings = getRatings();
            if (!ratings[ticker]) ratings[ticker] = {};
            ratings[ticker].stars = ratings[ticker].stars === starNum ? 0 : starNum;
            saveRatings(ratings);
            refreshControlsUI(ticker);
            return;
        }
        var exBtn = e.target.closest('.exclude-btn');
        if (exBtn) {
            e.preventDefault();
            e.stopPropagation();
            var ticker = exBtn.getAttribute('data-ticker');
            if (!ticker) return;
            var ratings = getRatings();
            if (!ratings[ticker]) ratings[ticker] = {};
            ratings[ticker].excluded = !ratings[ticker].excluded;
            saveRatings(ratings);
            refreshControlsUI(ticker);
            return;
        }
        var memoBtn = e.target.closest('.memo-btn');
        if (memoBtn) {
            e.preventDefault();
            e.stopPropagation();
            var ticker = memoBtn.getAttribute('data-ticker');
            if (ticker) openMemo(ticker);
            return;
        }
    });

    // 메모 모달 이벤트
    if ($memoModal) {
        $memoModalClose.addEventListener('click', closeMemo);
        $memoSave.addEventListener('click', saveMemo);
        $memoDelete.addEventListener('click', deleteMemo);
        $memoModal.addEventListener('click', function (e) { if (e.target === $memoModal) closeMemo(); });
    }

    // ── 초기화 ──
    function init() {
        showLoading(true);
        StockAPI.getDates()
            .then(function (dates) {
                state.dates = dates;
                state.dateIndex = 0;
                loadReport();
            })
            .catch(function () {
                showLoading(false);
                showMessage('날짜 목록을 불러올 수 없습니다.');
            });
    }

    // ── 이벤트 ──
    $datePrev.addEventListener('click', function () {
        if (state.dateIndex < state.dates.length - 1) {
            state.dateIndex++;
            loadReport();
        }
    });
    $dateNext.addEventListener('click', function () {
        if (state.dateIndex > 0) {
            state.dateIndex--;
            loadReport();
        }
    });
    $stockMoreBtn.addEventListener('click', function () {
        state.stocksShown = STOCK_MORE;
        renderTopStocks(state.allTopStocks, STOCK_MORE, getRatings());
    });

    init();
})();
