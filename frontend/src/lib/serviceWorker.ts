import { isNativePlatform } from "@/utils/platform";
import { sessionGet, sessionSet } from "@/utils/safeStorage";

const PRELOAD_RELOAD_KEY = "growlio:preload-reload-at";
const PRELOAD_RELOAD_WINDOW_MS = 60_000;

/**
 * 배포 직후 열린 탭이 사라진 해시 청크를 동적 import하면 Vite가 `vite:preloadError`를 던진다 — 새 index.html을 받도록
 * 한 번 새로고침한다. 1분 안에 또 나면(진짜 장애) 새로고침하지 않고 ErrorBoundary의 안내에 맡겨 무한 루프를 막는다.
 */
export function setupPreloadErrorReload(): void {
  window.addEventListener("vite:preloadError", (event) => {
    const last = Number(sessionGet(PRELOAD_RELOAD_KEY) ?? 0);
    if (Date.now() - last < PRELOAD_RELOAD_WINDOW_MS) return;
    const now = String(Date.now());
    sessionSet(PRELOAD_RELOAD_KEY, now);
    // 기록이 안 되면(저장소 차단) 루프 방지를 보장할 수 없다 — 새로고침하지 않는다
    if (sessionGet(PRELOAD_RELOAD_KEY) !== now) return;
    event.preventDefault();
    window.location.reload();
  });
}

/**
 * 웹(PWA)에서만 SW를 등록한다. Capacitor는 dist를 로컬 파일로 싣기 때문에 SW 캐시가 필요 없고,
 * 오히려 예전 빌드의 SW 캐시(API StaleWhileRevalidate 포함)가 앱 업데이트 후 낡은 셸을 남길 수 있다 —
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
