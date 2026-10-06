import * as Sentry from "@sentry/react";
import { useEffect } from "react";
import {
  createRoutesFromChildren,
  matchRoutes,
  useLocation,
  useNavigationType,
} from "react-router-dom";

/** Sentry 초기화 — side-effect import. `App` 모듈 그래프가 평가되기 전에 실행돼야
 * 초기 모듈 로드 에러와 라우터 트랜잭션이 누락되지 않는다 (main.tsx에서 App import 앞에 배치).
 * 라우터 v7 통합은 트랜잭션 이름을 raw URL 대신 라우트 패턴으로 묶는다 — `App.tsx`의
 * `<Routes>`가 `Sentry.withSentryReactRouterV7Routing`으로 감싸져 있어야 동작한다. */
const sentryDsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: import.meta.env.MODE,
    release: import.meta.env.VITE_SENTRY_RELEASE as string | undefined,
    integrations: [
      Sentry.reactRouterV7BrowserTracingIntegration({
        useEffect,
        useLocation,
        useNavigationType,
        createRoutesFromChildren,
        matchRoutes,
      }),
    ],
    tracesSampleRate: 0.1,
  });
}
