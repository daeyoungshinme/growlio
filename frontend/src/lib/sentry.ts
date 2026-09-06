import * as Sentry from "@sentry/react";

/** Sentry 초기화 — side-effect import. `App` 모듈 그래프가 평가되기 전에 실행돼야
 * 초기 모듈 로드 에러와 라우터 트랜잭션이 누락되지 않는다 (main.tsx에서 App import 앞에 배치). */
const sentryDsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: import.meta.env.MODE,
    release: import.meta.env.VITE_SENTRY_RELEASE as string | undefined,
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: 0.1,
  });
}
