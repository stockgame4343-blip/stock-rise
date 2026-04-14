/**
 * 데일리 리포트 페이지 로직
 */
(function () {
    var DAYS_KO = ['일', '월', '화', '수', '목', '금', '토'];
    var THEME_KEY = 'theme';

    var state = {
        dates: [],
        dateIndex: 0,
    };

    // DOM
    var $reportTitle = document.getElementById('reportTitle');
    var $loading = document.getElementById('loading');
    var $message = document.getElementById('message');
    var $content = document.getElementById('reportContent');
    var $datePrev = document.getElementById('datePrev');
    var $dateNext = document.getElementById('dateNext');
    var $lastUpdated = document.getElementById('lastUpdated');

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

    function showLoading(v) {
        $loading.style.display = v ? 'block' : 'none';
        $content.style.display = v ? 'none' : 'block';
    }
    function showMessage(msg) {
        $message.style.display = msg ? 'block' : 'none';
        $message.textContent = msg;
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
        result.summary = {
            count: totalCount,
            avgRate: avgRate,
            limitUp: limitUp,
            totalVolume: totalVolume,
        };

        // 2) 섹터 분석
        var sectorMap = {};
        rankings.forEach(function (r) {
            var sec = r.sector || '기타';
            if (!sectorMap[sec]) sectorMap[sec] = { name: sec, stocks: [], totalRate: 0, totalVolume: 0 };
            sectorMap[sec].stocks.push(r);
            sectorMap[sec].totalRate += r.change_rate;
            sectorMap[sec].totalVolume += (r.trading_value || 0);
        });
        var sectors = Object.values(sectorMap)
            .filter(function (s) { return s.stocks.length >= 2; })
            .map(function (s) {
                s.avgRate = s.totalRate / s.stocks.length;
                s.stocks.sort(function (a, b) { return b.change_rate - a.change_rate; });
                return s;
            })
            .sort(function (a, b) { return b.stocks.length - a.stocks.length; })
            .slice(0, 5);
        result.sectors = sectors;

        // 3) 테마 분석
        var themeMap = {};
        rankings.forEach(function (r) {
            if (!r.theme_tag) return;
            // 복합 태그 분리 (쉼표, 슬래시)
            var tags = r.theme_tag.split(/[,\/]/).map(function (t) { return t.trim(); }).filter(Boolean);
            tags.forEach(function (tag) {
                if (!themeMap[tag]) themeMap[tag] = { name: tag, count: 0, totalRate: 0, stocks: [] };
                themeMap[tag].count++;
                themeMap[tag].totalRate += r.change_rate;
                themeMap[tag].stocks.push(r);
            });
        });
        var themes = Object.values(themeMap)
            .map(function (t) { t.avgRate = t.totalRate / t.count; return t; })
            .sort(function (a, b) { return b.count - a.count; });
        result.themes = themes;

        // 4) 주목 종목 (점수 TOP 5)
        var topStocks = rankings.slice()
            .sort(function (a, b) { return b.score - a.score; })
            .slice(0, 5);
        result.topStocks = topStocks;

        // 5) 상승 원인 분석
        var reasonMap = {};
        rankings.forEach(function (r) {
            if (!r.rise_reason) return;
            // 복합 원인 분리
            var reasons = r.rise_reason.split(/[,]/).map(function (s) { return s.trim(); }).filter(Boolean);
            reasons.forEach(function (reason) {
                if (!reasonMap[reason]) reasonMap[reason] = { name: reason, count: 0 };
                reasonMap[reason].count++;
            });
        });
        var reasons = Object.values(reasonMap)
            .sort(function (a, b) { return b.count - a.count; })
            .slice(0, 8);
        result.reasons = reasons;

        // 6) 주요 뉴스 (점수 상위 10종목의 첫 뉴스)
        var topForNews = rankings.slice()
            .sort(function (a, b) { return b.score - a.score; })
            .slice(0, 10);
        var newsList = [];
        topForNews.forEach(function (r) {
            if (r.news && r.news.length > 0) {
                // 서울데이터랩 제외한 첫 뉴스
                var best = null;
                for (var i = 0; i < r.news.length; i++) {
                    if (r.news[i].title.indexOf('서울데이터랩') === -1) {
                        best = r.news[i];
                        break;
                    }
                }
                if (!best) best = r.news[0];
                newsList.push({
                    stock: r.name,
                    ticker: r.ticker,
                    title: best.title,
                    link: best.link,
                    source: best.source,
                    score: r.score,
                });
            }
        });
        result.news = newsList;

        return result;
    }

    // ── 렌더링 ──
    function renderSummary(summary) {
        document.getElementById('sumCount').textContent = summary.count + '개';
        document.getElementById('sumAvgRate').textContent = '+' + summary.avgRate.toFixed(2) + '%';
        document.getElementById('sumLimit').textContent = summary.limitUp + '종목';
        document.getElementById('sumVolume').textContent = formatAmount(summary.totalVolume);
    }

    function renderSectors(sectors) {
        var container = document.getElementById('sectorCards');
        var html = '';
        sectors.forEach(function (sec, i) {
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
                html += '<span class="sector-card__stock-name">' + s.name + '</span>';
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

    function renderThemes(themes) {
        var container = document.getElementById('themeCloud');
        if (themes.length === 0) {
            container.innerHTML = '<p class="report__empty">테마 태그가 없습니다</p>';
            return;
        }
        var html = '';
        themes.forEach(function (t) {
            var size = t.count >= 5 ? 'lg' : (t.count >= 3 ? 'md' : 'sm');
            html += '<div class="theme-chip theme-chip--' + size + '">';
            html += '<span class="theme-chip__name">' + t.name + '</span>';
            html += '<span class="theme-chip__meta">' + t.count + '종목 &middot; +' + t.avgRate.toFixed(1) + '%</span>';
            html += '</div>';
        });
        container.innerHTML = html;
    }

    function renderTopStocks(stocks) {
        var container = document.getElementById('stockCards');
        var html = '';
        stocks.forEach(function (s, i) {
            var naverUrl = 'https://finance.naver.com/item/main.naver?code=' + s.ticker;
            html += '<div class="stock-card">';
            html += '<div class="stock-card__top">';
            html += '<span class="stock-card__rank">' + (i + 1) + '</span>';
            html += '<div class="stock-card__info">';
            html += '<span class="stock-card__name">' + s.name + '</span>';
            html += '<span class="stock-card__market">' + s.market + ' &middot; ' + (s.sector || '-') + '</span>';
            html += '</div>';
            html += '<div class="stock-card__numbers">';
            html += '<span class="stock-card__rate">+' + s.change_rate.toFixed(2) + '%</span>';
            html += '<span class="stock-card__price">' + formatNumber(s.close_price) + '원</span>';
            html += '</div>';
            html += '</div>';

            // 점수 바
            var cls = s.score >= 70 ? 'high' : (s.score >= 40 ? 'mid' : 'low');
            html += '<div class="stock-card__score-row">';
            html += '<span class="stock-card__score-label">호재점수</span>';
            html += '<div class="stock-card__score-bar"><div class="stock-card__score-fill stock-card__score-fill--' + cls + '" style="width:' + s.score + '%"></div></div>';
            html += '<span class="stock-card__score-num score-badge score-badge--' + cls + '">' + s.score + '</span>';
            html += '</div>';

            // 테마 + 상승 이유
            if (s.theme_tag || s.rise_reason) {
                html += '<div class="stock-card__reason">';
                if (s.theme_tag) {
                    html += '<span class="theme-tag">' + s.theme_tag + '</span>';
                }
                html += '<span>' + (s.rise_reason || '') + '</span>';
                html += '</div>';
            }

            // 뉴스 미리보기
            if (s.news && s.news.length > 0) {
                var best = null;
                for (var j = 0; j < s.news.length; j++) {
                    if (s.news[j].title.indexOf('서울데이터랩') === -1) { best = s.news[j]; break; }
                }
                if (!best) best = s.news[0];
                html += '<a class="stock-card__news" href="' + best.link + '" target="_blank" rel="noopener">';
                html += '<span class="stock-card__news-icon">&#128240;</span>';
                html += '<span class="stock-card__news-title">' + best.title + '</span>';
                if (best.source) html += '<span class="stock-card__news-source">' + best.source + '</span>';
                html += '</a>';
            }

            html += '<a class="stock-card__naver" href="' + naverUrl + '" target="_blank" rel="noopener">네이버 금융에서 보기</a>';
            html += '</div>';
        });
        container.innerHTML = html;
    }

    function renderReasons(reasons) {
        var container = document.getElementById('reasonBars');
        if (reasons.length === 0) {
            container.innerHTML = '<p class="report__empty">데이터가 없습니다</p>';
            return;
        }
        var maxCount = reasons[0].count;
        var html = '';
        reasons.forEach(function (r) {
            var pct = Math.round(r.count / maxCount * 100);
            html += '<div class="reason-row">';
            html += '<span class="reason-row__label">' + r.name + '</span>';
            html += '<div class="reason-row__bar-wrap">';
            html += '<div class="reason-row__bar" style="width:' + pct + '%"></div>';
            html += '</div>';
            html += '<span class="reason-row__count">' + r.count + '건</span>';
            html += '</div>';
        });
        container.innerHTML = html;
    }

    function renderNews(newsList) {
        var container = document.getElementById('newsList');
        if (newsList.length === 0) {
            container.innerHTML = '<p class="report__empty">뉴스가 없습니다</p>';
            return;
        }
        var html = '';
        newsList.forEach(function (n) {
            html += '<a class="news-row" href="' + n.link + '" target="_blank" rel="noopener">';
            html += '<div class="news-row__left">';
            html += '<span class="news-row__stock">' + n.stock + '</span>';
            html += '<span class="news-row__title">' + n.title + '</span>';
            html += '</div>';
            html += '<span class="news-row__source">' + (n.source || '') + '</span>';
            html += '</a>';
        });
        container.innerHTML = html;
    }

    // ── 데이터 로드 ──
    function loadReport() {
        var date = state.dates[state.dateIndex];
        if (!date) return;

        showLoading(true);
        showMessage('');
        $reportTitle.textContent = formatDateKorean(date) + ' 데일리 리포트';

        // 네비 버튼 상태
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

                // 업데이트 시간
                if (data.collected_at && $lastUpdated) {
                    var d = new Date(data.collected_at);
                    var hh = String(d.getHours()).padStart(2, '0');
                    var mm = String(d.getMinutes()).padStart(2, '0');
                    var label = data.is_final ? '장마감' : '장중';
                    $lastUpdated.textContent = label + ' ' + hh + ':' + mm + ' 수집';
                }

                var analysis = analyzeData(data.rankings);
                renderSummary(analysis.summary);
                renderSectors(analysis.sectors);
                renderThemes(analysis.themes);
                renderTopStocks(analysis.topStocks);
                renderReasons(analysis.reasons);
                renderNews(analysis.news);
            })
            .catch(function (err) {
                showLoading(false);
                showMessage('데이터를 불러올 수 없습니다.');
                $content.style.display = 'none';
            });
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

    init();
})();
