import { isAxiosError } from "axios";

/** 쿼리 재시도 상한 — 예전 전역 `retry: 1`과 같은 횟수 */
const MAX_RETRIES = 1;
const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS = 8_000;

/**
 * 재시도할 만한 실패인지 — 응답 없는 네트워크 오류·타임아웃·5xx·429만. 4xx(권한·검증·없음)는 다시 보내도 같은 답이라
 * 즉시 실패시킨다(401은 api/client.ts 인터셉터가 토큰 갱신 후 이미 1회 재시도했다).
 */
export function isRetryableError(error: unknown): boolean {
  if (!isAxiosError(error)) return false;
  const status = error.response?.status;
  if (status == null) return true;
  return status >= 500 || status === 429;
}

export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  return failureCount < MAX_RETRIES && isRetryableError(error);
}

/**
 * 지수 백오프 + 지터 — 잠든 서버가 깨는 동안 동시에 실패한 쿼리들이 같은 순간 다시 몰리지 않게 흩는다.
 * `random`은 테스트 주입용.
 */
export function retryDelayMs(
  failureCount: number,
  _error?: unknown,
  random: () => number = Math.random,
): number {
  const exp = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** failureCount);
  return Math.round(exp / 2 + random() * (exp / 2));
}
