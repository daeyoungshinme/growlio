# 28. localStorage 토큰 저장 — 경계강화 결정기록 (2026-08-20)

## 배경

`docs/plans/25-security-audit-2026-08-05.md`가 "프론트엔드 토큰/재무데이터 localStorage 평문 저장"을 httpOnly 쿠키 전환이 필요한 이관 항목으로 남긴 뒤, 2026-08-20 재검토 세션에서 이 항목을 다시 다뤘다. Growlio는 웹앱 외에 Capacitor Android 앱도 함께 서비스하는데, httpOnly 쿠키는 WebView의 크로스오리진 환경에서 SameSite 제약으로 잘 동작하지 않는 경우가 많아 완전 전환은 웹/모바일 이중 인증 아키텍처를 새로 설계해야 하는 큰 작업이다. 사용자와 확인한 결과 이번 세션은 **아키텍처 변경 없는 경계강화(mitigation)만** 진행하기로 범위를 좁혔다.

## 재확인된 현재 상태

코드를 다시 읽어보니 25번 문서 작성 시점보다 잔여 리스크가 작다 — 같은 2026-08-05 세션에서 이미 상당 부분이 완화되어 있었다.

- **CSP 이미 강함**: `frontend/vercel.json`의 `Content-Security-Policy`가 `script-src 'self'`로 제한되어 있고 `unsafe-inline`/`unsafe-eval`이 없다. 고전적인 인라인 스크립트 XSS(가장 흔한 토큰 탈취 경로)는 이미 막혀 있다.
- **로그아웃 시 캐시 완전 삭제 확인**: `frontend/src/hooks/useLogout.ts`가 `queryClient.clear()` + `window.localStorage.removeItem(PERSIST_CACHE_KEY)`를 호출해, 재무 데이터가 담긴 React Query persist 캐시(`dashboard`/`portfolio-overview`/`accounts`/`dca-analysis`/`goal-recommendation`)를 로그아웃 즉시 지운다 — "로그아웃 후에도 이전 사용자 데이터가 브라우저에 남는" 문제는 이미 없음.
- **`AUTH_ME_CACHE_KEY`는 무해함**: `frontend/src/stores/authStore.ts`가 localStorage에 저장하는 낙관적 인증 캐시는 `userId`/`needsPasswordReset`(boolean)/`cachedAt`(timestamp)뿐 — 자격증명이나 세션 토큰을 포함하지 않는다.

## 남은 잔여 리스크 (수용)

Supabase `persistSession: true`(`frontend/src/lib/supabase.ts`)가 세션 JWT(access/refresh)를 `sb-*-auth-token` 키로 localStorage에 저장하는 것 자체는 여전하다. 이는 `supabase-js`의 기본 동작이며, XSS가 발생하면(현재 알려진 XSS 벡터는 없음 — 위 CSP가 1차 방어선) 이 토큰이 탈취될 수 있다.

**완전히 없애는 방법과 왜 안 하는지**:
1. httpOnly 쿠키 전환 — 가장 근본적이지만 Capacitor WebView 크로스오리진 SameSite 제약으로 모바일 인증 흐름을 별도 설계해야 함(위 배경 참고). 실자금 이동 앱의 인증 아키텍처 전체를 바꾸는 작업이라 신중한 별도 세션 필요.
2. Supabase 클라이언트에 커스텀 `storage` 어댑터를 넣어 토큰을 localStorage 밖(예: 메모리 전용)으로 옮기는 방법 — 검토했으나 기각. 메모리 전용으로 바꾸면 앱 재시작마다 재로그인이 필요해 모바일 UX가 크게 나빠지고, sessionStorage로 옮겨도 같은 오리진 XSS에는 동일하게 노출되어(다른 탭 접근만 막을 뿐) 실질적 보안 이득이 작다.

**수용 근거**: 토큰 탈취의 실제 공격 경로는 XSS이고, `script-src 'self'`(unsafe-inline 없음) CSP가 이미 그 경로를 막고 있다. Supabase 프로젝트의 access token TTL(기본 1시간, `SUPABASE_JWT_SECRET` 발급 설정)이 짧게 유지되고 있는 한 탈취 시 피해 창도 제한적이다 — 이는 코드 변경이 아닌 Supabase 프로젝트 설정이므로 별도 조치 불필요, 현재값 유지를 권장한다.

## 결론

이 항목은 **경계강화 완료로 종결**한다. httpOnly 쿠키 완전 전환은 여전히 로드맵으로 남기되, 실제 착수는 (a) 모바일 인증 아키텍처를 별도로 설계할 의지가 있을 때, 또는 (b) 알려진 XSS 벡터가 실제로 발견됐을 때만 재검토한다. `docs/plans/25-security-audit-2026-08-05.md`의 1번 항목은 이 문서로 대체 종결.
