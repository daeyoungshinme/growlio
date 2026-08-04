# 25. 보안 감사 이관 항목 (2026-08-05)

## 배경

2026-08-05, "프로젝트 전체 보안 이슈 감사 + 개선 계획"을 요청받아 백엔드(인증/암호화/API)·프론트엔드(XSS/토큰저장/의존성)·인프라(Docker/CI/CD) 3개 축으로 조사했다. 발견 항목 중 즉시 구현 가능한 것(Quick Win — 프론트 의존성 패치, rate limit 안전망, 로그 전역 redaction, `.gitignore` 보강, Vercel CSP 헤더, Sentry PII 제거 등)과 KIS/키움 `access_token` DB 암호화는 같은 세션에 구현 완료했다(상세는 `MEMORY.md`의 해당 세션 메모리 참고). 아래 2개 항목은 브레이킹 체인지 또는 아키텍처 변경이 필요해 별도 세션으로 이관한다.

## 1. 프론트엔드 토큰/재무데이터 localStorage 평문 저장

**현재 상태**: `frontend/src/lib/supabase.ts`가 `persistSession: true`로 Supabase access/refresh JWT를 `localStorage`(`sb-*-auth-token` 키)에 평문 저장. `frontend/src/main.tsx`도 React Query 캐시(dashboard/portfolio-overview/accounts/goal-recommendation 등 재무 데이터)를 24시간 TTL로 `localStorage`에 평문 persist.

**위험**: XSS가 발생하면(현재 알려진 XSS 취약점은 없음 — CSP도 이번 세션에 추가함) `localStorage` 전체를 읽는 것만으로 refresh token까지 탈취되어 세션 만료 후에도 영구 재로그인이 가능해지고, 재무 정보도 함께 노출된다.

**왜 이번 세션에 안 했는지**: httpOnly 쿠키 전환은 `frontend/CLAUDE.md`에 명시된 "Supabase는 이메일 인증/OAuth 콜백에만 사용, 실제 API 인증은 백엔드 JWT" 구조 자체를 건드리는 아키텍처 변경 — 백엔드가 쿠키를 발급/검증하도록 바꿔야 하고, 모바일(Capacitor WebView) 환경에서 쿠키 동작도 별도 검증이 필요하다.

**후보 접근**:
1. (근본적) 백엔드가 httpOnly 쿠키로 access/refresh 토큰을 발급하도록 전환 — 가장 안전하지만 `api/client.ts`의 axios 인터셉터, 401 자동 refresh 로직, Capacitor 네이티브 앱의 쿠키 지원 여부를 전부 재검토해야 함.
2. (절충) React Query persist 대상에서 금융 데이터가 담긴 쿼리(dashboard/portfolio-overview/accounts 등)를 제외 — `frontend/src/main.tsx`의 persist 옵션(`dehydrateOptions`)에서 쿼리 키 필터링. Supabase 세션 저장 문제는 남지만 변경 범위가 작다.

## 2. react-router-dom 6→7 메이저 업그레이드

**현재 상태**: `npm audit` 기준 `react-router-dom@6.x`에 open redirect(moderate, `<Link>`/`useNavigate`의 백슬래시 처리, CVE-2025-68470 우회)와 SSR hydration 관련 취약점이 있음. 수정은 `react-router-dom@7.18.2`로의 메이저 업그레이드가 필요(`isSemVerMajor: true`, `npm audit fix --force`로만 적용 가능).

**왜 이번 세션에 안 했는지**: v6→v7은 브레이킹 체인지(데이터 라우터 API 변경 등)가 있어 라우팅 코드 전반(`App.tsx`의 모든 `<Route>`, `useNavigate`/`useParams` 사용처)에 회귀 테스트가 필요. 이번 세션은 "Quick win + 논브레이킹 패치"로 범위를 한정했다.

**작업 범위 추정**: `frontend/src/App.tsx` 라우트 정의 + 라우팅 관련 훅 사용처 전체 grep 후 v7 마이그레이션 가이드 대조, `npm run build && npm run test`로 회귀 확인.

## 참고

- 낮은 우선순위로 확인만 하고 넘어간 것: `docker-compose.yml`의 `POSTGRES_PASSWORD:-postgres}` 기본값 — 로컬 개발 전용(운영은 Supabase, `render.yaml`이 별도 시크릿 관리)이라 실위험 낮음. 별도 계획 문서 불필요.
