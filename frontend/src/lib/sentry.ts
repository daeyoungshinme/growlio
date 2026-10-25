import type * as SentryNs from "@sentry/react";

/**
 * Sentry 지연 초기화. `@sentry/react`(+browser)가 엔트리 청크에 들어가 부팅 시 수십 KB를 먼저 파싱하던 것을
 * 첫 렌더 이후 유휴 시간에 동적 import로 옮겼다(plans/72 3-3). 그 전에 난 오류는 버퍼링했다가 init 후 넘긴다.
 * 라우트 패턴 단위 트랜잭션(reactRouterV7BrowserTracingIntegration)은 `<Routes>` 래핑이 필요해 포기하고,
 * 일반 browserTracingIntegration(페이지 로드·이동, URL 기준)만 쓴다.
 *
 * 앱 코드는 `@sentry/react`를 직접 import하지 말고 여기 `captureException`을 쓴다 — 직접 import하면 다시
 * 엔트리 청크로 끌려온다.
 */

type CaptureContext = Parameters<typeof SentryNs.captureException>[1];
type Pending = { error: unknown; context?: CaptureContext };

const sentryDsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
const MAX_PENDING = 20;

let sentryPromise: Promise<typeof SentryNs> | null = null;
let pending: Pending[] = [];

function buffer(item: Pending) {
  if (pending.length < MAX_PENDING) pending.push(item);
}

const onWindowError = (e: ErrorEvent) => buffer({ error: e.error ?? e.message });
const onUnhandledRejection = (e: PromiseRejectionEvent) => buffer({ error: e.reason });

function load(): Promise<typeof SentryNs> {
  sentryPromise ??= import("@sentry/react").then((Sentry) => {
    Sentry.init({
      dsn: sentryDsn,
      environment: import.meta.env.MODE,
      release: import.meta.env.VITE_SENTRY_RELEASE as string | undefined,
      integrations: [Sentry.browserTracingIntegration()],
      tracesSampleRate: 0.1,
    });
    // 이후로는 Sentry가 전역 핸들러를 직접 단다
    window.removeEventListener("error", onWindowError);
    window.removeEventListener("unhandledrejection", onUnhandledRejection);
    const queued = pending;
    pending = [];
    queued.forEach(({ error, context }) => Sentry.captureException(error, context));
    return Sentry;
  });
  return sentryPromise;
}

/** main.tsx에서 렌더 직후 1회 호출 — DSN이 없으면 아무것도 하지 않는다 */
export function initSentryDeferred(): void {
  if (!sentryDsn) return;
  window.addEventListener("error", onWindowError);
  window.addEventListener("unhandledrejection", onUnhandledRejection);
  const start = () => void load().catch(() => {});
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(start, { timeout: 3000 });
  } else {
    setTimeout(start, 1500);
  }
}

export function captureException(error: unknown, context?: CaptureContext): void {
  if (!sentryDsn) return;
  if (sentryPromise) {
    void sentryPromise.then((Sentry) => Sentry.captureException(error, context)).catch(() => {});
  } else {
    buffer({ error, context });
  }
}
