/**
 * 모달 접근성 헬퍼 — 모든 .modal-overlay 에 공통으로 ESC 닫기 적용.
 * 페이지 진입 시 자동 활성화. 추가 설정 불필요.
 *
 * 닫기 동작은 .modal__close / .cards-modal__close 버튼의 click() 을 호출하므로
 * 기존 닫기 핸들러가 그대로 실행됨 (메모 저장 상태 등 사이드이펙트 안 깨짐).
 */
(function () {
    function isOpen(el) {
        if (!el) return false;
        var s = el.style && el.style.display;
        if (s === 'flex' || s === 'block') return true;
        // inline style 없으면 computed 로
        var cs = getComputedStyle(el);
        return cs.display !== 'none';
    }

    function findOpenModal() {
        var all = document.querySelectorAll('.modal-overlay');
        for (var i = all.length - 1; i >= 0; i--) {
            if (isOpen(all[i])) return all[i];
        }
        return null;
    }

    function onKey(e) {
        if (e.key !== 'Escape') return;
        var modal = findOpenModal();
        if (!modal) return;
        var btn = modal.querySelector('.modal__close, .cards-modal__close');
        if (btn) {
            btn.click();
            e.preventDefault();
        }
    }

    document.addEventListener('keydown', onKey);
})();
