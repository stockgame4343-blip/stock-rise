/**
 * 공용 토스트 컴포넌트 — 별점·메모·태그 저장 / 오류 / 안내 메시지.
 * window.Toast.show(text, { type: 'success'|'error'|'info', duration: 2000, action: { label, onClick } })
 */
(function () {
    var DEFAULT_DURATION_MS = 2000;
    var ANIM_MS = 200;

    var stack = null;

    function ensureStack() {
        if (stack && document.body.contains(stack)) return stack;
        stack = document.createElement('div');
        stack.className = 'toast-stack';
        stack.setAttribute('role', 'status');
        stack.setAttribute('aria-live', 'polite');
        document.body.appendChild(stack);
        return stack;
    }

    function dismiss(t) {
        if (!t || !t.parentNode) return;
        t.classList.remove('toast--in');
        t.classList.add('toast--out');
        setTimeout(function () {
            if (t.parentNode) t.parentNode.removeChild(t);
        }, ANIM_MS);
    }

    function show(text, opts) {
        opts = opts || {};
        var type = opts.type || 'info';
        var duration = opts.duration === undefined ? DEFAULT_DURATION_MS : opts.duration;

        var s = ensureStack();
        var t = document.createElement('div');
        t.className = 'toast toast--' + type;

        var msg = document.createElement('span');
        msg.className = 'toast__msg';
        msg.textContent = text;
        t.appendChild(msg);

        if (opts.action && opts.action.label) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'toast__action';
            btn.textContent = opts.action.label;
            btn.addEventListener('click', function () {
                try { if (opts.action.onClick) opts.action.onClick(); } catch (e) { /* noop */ }
                dismiss(t);
            });
            t.appendChild(btn);
        }

        s.appendChild(t);
        // 다음 frame 에 in 클래스 → CSS transition 발동
        requestAnimationFrame(function () { t.classList.add('toast--in'); });

        if (duration > 0) {
            setTimeout(function () { dismiss(t); }, duration);
        }
        return t;
    }

    window.Toast = { show: show, dismiss: dismiss };
})();
