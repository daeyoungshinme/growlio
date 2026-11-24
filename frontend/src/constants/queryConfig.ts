import { defaultShouldDehydrateQuery, type Query } from "@tanstack/react-query";

export const PERSIST_CACHE_KEY = "rq-persist-cache";

/**
 * persist 캐시 버전 — main.tsx `PERSIST_QUERY_KEYS`에 든 쿼리의 응답 형태를 호환되지 않게 바꾸면(필드 삭제·이름/타입 변경,
 * 새 필드를 non-optional로 읽기 시작) 날짜로 올린다. 올리면 모든 기기의 24h 캐시가 한 번 버려진다.
 * 배포마다 자동으로 바꾸지 않는 건 매 배포 첫 부팅이 콜드가 되어 persist의 목적(즉시 표시)이 사라지기 때문이다.
 * "v1"(2026-06-09)에서 한 번도 안 올라가 그 사이 dashboard·portfolios 응답 변경이 누적돼 있었다(plans/61 B4).
 */
export const PERSIST_CACHE_BUSTER = "2026-11-11";

/**
 * 앱 재시작 시 즉시 표시할 쿼리(첫 키 기준) — 응답 형태를 바꾸면 PERSIST_CACHE_BUSTER를 올린다.
 * 홈 첫 화면 카드(지금 할 일·챌린지·시장 신호 배지·환율)도 넣어 콜드 스타트에 스켈레톤·빈 카드가 먼저 뜨지 않게 한다
 * (plans/125 C2). main.tsx가 이 키들의 gcTime을 maxAge(24h)로 맞춘다 — 기본 30분이면 관찰자가 없는 동안 캐시에서
 * 지워져 persist 저장본에서도 빠졌다.
 */
export const PERSIST_QUERY_KEYS: readonly string[] = [
  "dashboard",
  "portfolio-overview",
  "accounts",
  // dca-analysis는 홈이 더 이상 받지 않는다(목표 예상월은 대시보드 응답, plans/151 B1) — 월별 투영 배열이 커서 저장하지 않는다
  "goal-recommendation",
  "action-items",
  "challenges",
  "portfolios",
  "market-signal",
  "exchange-rate",
];
const PERSIST_QUERY_KEY_SET = new Set(PERSIST_QUERY_KEYS);

/**
 * 변형이 많은 키는 첫 화면에 쓰는 두 번째 키만 저장한다 — 기간별·연령대 추천, 계좌별 전체 overview(`all_positions`
 * 포함 큰 응답)까지 저장하면 매 저장(2초 throttle)마다 메인 스레드 직렬화와 localStorage 용량이 커진다(plans/151 A10).
 */
const PERSIST_SUBKEYS: Readonly<Record<string, readonly string[]>> = {
  "goal-recommendation": ["overall"],
  "portfolio-overview": ["lite", "all"],
};

/** gcTime을 maxAge에 맞출 프리픽스 목록(main.tsx) — `shouldPersistQuery`와 같은 범위 */
export function persistQueryPrefixes(): string[][] {
  return PERSIST_QUERY_KEYS.flatMap((key) =>
    PERSIST_SUBKEYS[key] ? PERSIST_SUBKEYS[key].map((sub) => [key, sub]) : [[key]],
  );
}

/**
 * persist 대상 판정. 커스텀 필터는 라이브러리 기본값(성공한 쿼리만)을 대체하므로 반드시 합친다 —
 * 빠뜨리면 실패·진행 중 쿼리까지 저장돼 다음 부팅이 에러 화면으로 시작한다(plans/61 B4).
 */
export function shouldPersistQuery(query: Query): boolean {
  const [head, second] = query.queryKey;
  if (!defaultShouldDehydrateQuery(query) || !PERSIST_QUERY_KEY_SET.has(head as string))
    return false;
  const subkeys = PERSIST_SUBKEYS[head as string];
  return !subkeys || subkeys.includes(second as string);
}

export const STALE_TIME = {
  /** 항상 새로 조회 — 열 때마다 최신이어야 하는 화면(승인 확인·추천 미리보기) */
  NONE: 0,
  VERY_SHORT: 15_000,
  SHORT: 30_000,
  MEDIUM: 60_000,
  LONG: 1000 * 60 * 60,
  /** 영속 캐시 maxAge(main.tsx)와 같은 하루 — 무거운 계산 결과를 gcTime으로 오래 남길 때 */
  DAY: 1000 * 60 * 60 * 24,
  EXCHANGE_RATE: 5 * 60 * 1000,
  FIVE_MINUTES: 5 * 60 * 1000,
} as const;

/** 앱 복귀(window focus) 시 이보다 오래된 쿼리만 재조회 (main.tsx QueryClient 기본값) */
export const FOCUS_REFETCH_MIN_AGE = 5 * 60 * 1000;

export const REFETCH_INTERVAL = {
  DASHBOARD: 300_000,
  PORTFOLIO: 300_000,
  /** 서버 환율 캐시가 5분마다 갱신된다 — 앱 전역 환율 구독은 다시 마운트되지 않아 이게 없으면 부팅 값에 머문다(plans/134) */
  EXCHANGE_RATE: 300_000,
} as const;
