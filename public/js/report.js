/**
 * 데일리 리포트 페이지 로직
 */
(function () {
    var DAYS_KO = ['일', '월', '화', '수', '목', '금', '토'];
    var THEME_KEY = 'theme';
    var NEWS_INITIAL = 10;
    var NEWS_MORE = 30;

    var state = {
        dates: [],
        dateIndex: 0,
        allNews: [],
        newsShown: NEWS_INITIAL,
    };

    // DOM
    var $reportTitle = document.getElementById('reportTitle');
    var $loading = document.getElementById('loading');
    var $message = document.getElementById('message');
    var $content = document.getElementById('reportContent');
    var $datePrev = document.getElementById('datePrev');
    var $dateNext = document.getElementById('dateNext');
    var $lastUpdated = document.getElementById('lastUpdated');
    var $newsMoreBtn = document.getElementById('newsMoreBtn');

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

    function filterGoodNews(newsList) {
        return newsList.filter(function (n) {
            return n.title.indexOf('서울데이터랩') === -1;
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

        // 3) 테마 분석 — 카드형 TOP 5
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

        // 4) 주목 종목 (점수 TOP 5)
        result.topStocks = rankings.slice()
            .sort(function (a, b) { return b.score - a.score; })
            .slice(0, 5);

        // 5) 주요 뉴스 (점수 상위 30종목에서 수집)
        var topForNews = rankings.slice()
            .sort(function (a, b) { return b.score - a.score; })
            .slice(0, NEWS_MORE);
        var newsList = [];
        topForNews.forEach(function (r) {
            if (r.news && r.news.length > 0) {
                var good = filterGoodNews(r.news);
                var best = good.length > 0 ? good[0] : r.news[0];
                newsList.push({
                    stock: r.name, ticker: r.ticker,
                    title: best.title, link: best.link, source: best.source,
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

    function renderSectorCard(items, container) {
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

    function renderSectors(sectors) {
        renderSectorCard(sectors, document.getElementById('sectorCards'));
    }

    function renderThemes(themes) {
        var container = document.getElementById('themeCards');
        if (themes.length === 0) {
            container.innerHTML = '<p class="report__empty">테마 태그가 없습니다</p>';
            return;
        }
        renderSectorCard(themes, container);
    }

    function renderTopStocks(stocks) {
        var container = document.getElementById('stockCards');
        var html = '';
        stocks.forEach(function (s, i) {
            var naverUrl = 'https://finance.naver.com/item/main.naver?code=' + s.ticker;
            var detail = s.score_detail || {};
            var bz = detail.buzz || 0;
            var qu = detail.quality || 0;
            var ty = detail.type || 0;
            var tv = detail.turnover || 0;

            html += '<div class="stock-card">';

            // 헤더
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

            // 테마 + 상승 이유
            if (s.theme_tag || s.rise_reason) {
                html += '<div class="stock-card__reason">';
                if (s.theme_tag) html += '<span class="theme-tag">' + s.theme_tag + '</span>';
                html += '<span>' + (s.rise_reason || '') + '</span>';
                html += '</div>';
            }

            // 호재점수 상세 분석
            var cls = s.score >= 70 ? 'high' : (s.score >= 40 ? 'mid' : 'low');
            html += '<div class="score-analysis">';
            html += '<div class="score-analysis__header">';
            html += '<span class="score-analysis__title">호재점수 분석</span>';
            html += '<span class="score-badge score-badge--' + cls + '">' + s.score + '</span>';
            html += '</div>';

            // 4개 항목
            html += '<div class="score-analysis__grid">';

            html += '<div class="score-analysis__item">';
            html += '<div class="score-analysis__item-header">';
            html += '<span class="score-analysis__item-label">뉴스 양</span>';
            html += '<span class="score-analysis__item-score">' + bz + '<span class="score-analysis__item-max">/20</span></span>';
            html += '</div>';
            html += '<div class="score-analysis__bar"><div class="score-analysis__fill" style="width:' + (bz / 20 * 100) + '%"></div></div>';
            html += '<span class="score-analysis__desc">' + buzzLevel(bz) + ' — 중복 제거 후 관련 뉴스 건수</span>';
            html += '</div>';

            html += '<div class="score-analysis__item">';
            html += '<div class="score-analysis__item-header">';
            html += '<span class="score-analysis__item-label">뉴스 질</span>';
            html += '<span class="score-analysis__item-score">' + qu + '<span class="score-analysis__item-max">/25</span></span>';
            html += '</div>';
            html += '<div class="score-analysis__bar"><div class="score-analysis__fill" style="width:' + (qu / 25 * 100) + '%"></div></div>';
            html += '<span class="score-analysis__desc">' + qualityLevel(qu) + ' — 주요 언론사, 수치 포함 여부</span>';
            html += '</div>';

            html += '<div class="score-analysis__item">';
            html += '<div class="score-analysis__item-header">';
            html += '<span class="score-analysis__item-label">호재 강도</span>';
            html += '<span class="score-analysis__item-score">' + ty + '<span class="score-analysis__item-max">/30</span></span>';
            html += '</div>';
            html += '<div class="score-analysis__bar"><div class="score-analysis__fill" style="width:' + (ty / 30 * 100) + '%"></div></div>';
            html += '<span class="score-analysis__desc">' + typeLevel(ty) + ' — 테마 연동, 호재 유형 분석</span>';
            html += '</div>';

            html += '<div class="score-analysis__item">';
            html += '<div class="score-analysis__item-header">';
            html += '<span class="score-analysis__item-label">거래량 강도</span>';
            html += '<span class="score-analysis__item-score">' + tv + '<span class="score-analysis__item-max">/25</span></span>';
            html += '</div>';
            html += '<div class="score-analysis__bar"><div class="score-analysis__fill" style="width:' + (tv / 25 * 100) + '%"></div></div>';
            html += '<span class="score-analysis__desc">' + turnoverLevel(tv) + ' — 시총 대비 거래대금 비율</span>';
            html += '</div>';

            html += '</div>'; // grid
            html += '</div>'; // score-analysis

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

                // 뉴스 더보기
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
    }

    function renderNews(newsList, limit) {
        var container = document.getElementById('newsList');
        if (newsList.length === 0) {
            container.innerHTML = '<p class="report__empty">뉴스가 없습니다</p>';
            $newsMoreBtn.style.display = 'none';
            return;
        }
        var show = newsList.slice(0, limit);
        var html = '';
        show.forEach(function (n) {
            html += '<a class="news-row" href="' + n.link + '" target="_blank" rel="noopener">';
            html += '<div class="news-row__left">';
            html += '<span class="news-row__stock">' + n.stock + '</span>';
            html += '<span class="news-row__title">' + n.title + '</span>';
            html += '</div>';
            html += '<span class="news-row__source">' + (n.source || '') + '</span>';
            html += '</a>';
        });
        container.innerHTML = html;

        // 더보기 버튼
        if (newsList.length > limit) {
            $newsMoreBtn.style.display = 'block';
            $newsMoreBtn.textContent = '더보기 (' + (newsList.length - limit) + '건)';
        } else {
            $newsMoreBtn.style.display = 'none';
        }
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
                state.allNews = analysis.news;
                state.newsShown = NEWS_INITIAL;

                renderSummary(analysis.summary);
                renderSectors(analysis.sectors);
                renderThemes(analysis.themes);
                renderTopStocks(analysis.topStocks);
                renderNews(analysis.news, NEWS_INITIAL);
            })
            .catch(function () {
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
    $newsMoreBtn.addEventListener('click', function () {
        state.newsShown = state.allNews.length;
        renderNews(state.allNews, state.newsShown);
    });

    init();
})();
