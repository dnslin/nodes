// Turnstile Patch - 隐藏自动化标识，加速 Turnstile 验证
// 在 document_start 阶段执行，确保在页面脚本之前生效

(function () {
    "use strict";

    // 1. 隐藏 navigator.webdriver 标识
    // Chrome 自动化模式下 navigator.webdriver = true，Turnstile 会检测此属性
    try {
        Object.defineProperty(navigator, "webdriver", {
            get: function () {
                return false;
            },
            configurable: true,
        });
    } catch (e) {}

    // 2. 移除 Chrome 自动化相关的 Runtime 属性
    try {
        if (window.chrome && window.chrome.runtime) {
            delete window.chrome.runtime.onConnect;
            delete window.chrome.runtime.onMessage;
        }
    } catch (e) {}

    // 3. 覆盖 permissions.query，隐藏 notifications 权限异常
    try {
        var origQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = function (params) {
            if (params.name === "notifications") {
                return Promise.resolve({ state: Notification.permission });
            }
            return origQuery(params);
        };
    } catch (e) {}

    // 4. 修补 plugin 数量，模拟正常浏览器
    try {
        Object.defineProperty(navigator, "plugins", {
            get: function () {
                return [1, 2, 3, 4, 5];
            },
            configurable: true,
        });
    } catch (e) {}

    // 5. 修补 languages 属性
    try {
        Object.defineProperty(navigator, "languages", {
            get: function () {
                return ["en-US", "en"];
            },
            configurable: true,
        });
    } catch (e) {}

})();
