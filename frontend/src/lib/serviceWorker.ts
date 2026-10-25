import { isNativePlatform } from "@/utils/platform";

/**
 * 웹(PWA)에서만 SW를 등록한다. Capacitor는 dist를 로컬 파일로 싣기 때문에 SW 캐시가 필요 없고,
 * 오히려 API 응답이 SW의 StaleWhileRevalidate 캐시를 거치며 앱 업데이트 후 낡은 셸이 남을 수 있다 —
 * 예전 빌드가 WebView에 등록해 둔 SW와 캐시도 지운다.
 */
export function setupServiceWorker(): void {
  if (!("serviceWorker" in navigator)) return;
  if (isNativePlatform()) {
    void navigator.serviceWorker
      .getRegistrations()
      .then((regs) => Promise.all(regs.map((r) => r.unregister())))
      .catch(() => {});
    if ("caches" in window) {
      void caches
        .keys()
        .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
        .catch(() => {});
    }
    return;
  }
  if (!import.meta.env.PROD) return;
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
  });
}
