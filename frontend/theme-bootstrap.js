(function () {
    let theme = 'system';
    // 主题现在存在 v2k_prefs.ui.theme 里（旧版在 vtn_prefs.ui.theme，新键优先、旧键只读）；
    // 散装 'theme' 键只在更老的迁移前还可能读到。与 script.js 的 readStoredPrefs 同口径：
    // 逐个键尝试，缺席或损坏（非法 JSON / 不是对象）就落到下一个，而不是整体放弃。
    const candidate = (function () {
        for (const key of ['v2k_prefs', 'vtn_prefs']) {
            try {
                const raw = localStorage.getItem(key);
                if (!raw) continue;
                const stored = JSON.parse(raw);
                if (stored && typeof stored === 'object' && stored.ui && stored.ui.theme) {
                    return stored.ui.theme;
                }
            } catch (_error) {
                // 单个键损坏不挡后面的键；Private browsing can disable localStorage.
            }
        }
        try {
            return localStorage.getItem('theme');
        } catch (_error) {
            return null;
        }
    })();
    if (candidate === 'light' || candidate === 'dark' || candidate === 'system') theme = candidate;
    document.documentElement.dataset.theme = theme;

    // 脚本健康看门狗：script.js 完成初始化后会设置 __videoToNoReady。
    // 如果页面渲染成功但脚本因缓存错位、浏览器过旧等没有运行，
    // 所有按钮都会「点了没反应」——这里给出可见提示而不是静默失败。
    window.__videoToNoReady = false;
    window.addEventListener('DOMContentLoaded', function () {
        window.setTimeout(function () {
            if (window.__videoToNoReady) return;
            var banner = document.createElement('div');
            banner.className = 'script-failure-banner';
            banner.setAttribute('role', 'alert');
            banner.textContent =
                '页面脚本未正常加载，按钮可能无响应。请按 Ctrl+F5 强制刷新；' +
                '若仍无效，请通过托盘菜单「打开界面」重新访问。';
            document.body.appendChild(banner);
        }, 2500);
    });
})();