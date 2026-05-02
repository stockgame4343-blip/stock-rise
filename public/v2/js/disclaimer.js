/**
 * 면책 배너 — 신규 사용자가 "투자 신호 아님"을 인지하도록 헤더 아래 sticky 노출.
 * localStorage 의 dismiss 키를 KST 날짜(YYYYMMDD)로 저장하여, 새 거래일에는 다시 노출.
 */
(function () {
    var DISMISS_KEY = 'disclaimer-dismissed';

    function kstYmd() {
        var now = new Date();
        var kstMs = now.getTime() + (9 * 60 - now.getTimezoneOffset()) * 60 * 1000;
        var kst = new Date(kstMs);
        var y = kst.getUTCFullYear();
        var m = String(kst.getUTCMonth() + 1).padStart(2, '0');
        var d = String(kst.getUTCDate()).padStart(2, '0');
        return '' + y + m + d;
    }

    function init() {
        var banner = document.getElementById('disclaimerBanner');
        if (!banner) return;

        var today = kstYmd();
        try {
            if (localStorage.getItem(DISMISS_KEY) === today) {
                banner.style.display = 'none';
                return;
            }
        } catch (e) { /* localStorage 차단 환경 — 그래도 배너는 띄움 */ }

        banner.style.display = '';
        var closeBtn = banner.querySelector('.disclaimer-banner__close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function () {
                try { localStorage.setItem(DISMISS_KEY, kstYmd()); } catch (e) {}
                banner.style.display = 'none';
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
