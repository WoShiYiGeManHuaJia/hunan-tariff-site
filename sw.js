// 资费监控 · Service Worker（自毁版）
// 原 SW 采用「缓存优先」，会把旧版页面锁在本地，导致线上更新后仍显示老 UI。
// 本版只做一件事：注销自身并清空全部本地缓存，之后不再拦截任何请求。
self.addEventListener('install', function (e) {
  self.skipWaiting();
});
self.addEventListener('activate', function (e) {
  e.waitUntil(
    Promise.all([
      caches.keys().then(function (ks) {
        return Promise.all(ks.map(function (k) { return caches.delete(k); }));
      }),
      self.registration.unregister()
    ]).then(function () { return self.clients.claim(); })
  );
});
// 不再注册 fetch：任何请求都不拦截，直接走网络
