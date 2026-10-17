/**
 * localStorage 안전 래퍼 — 저장소가 막힌 환경(사생활 보호 모드, 사이트 데이터 차단, 일부 WebView)에선
 * 접근 자체가 예외를 던진다. 읽기 실패는 null(=저장값 없음), 쓰기·삭제 실패는 무시한다.
 * 저장값은 편의용(접힘 상태·테마·캐시)이라 실패해도 기본값으로 동작하면 충분하다.
 */
export function storageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function storageSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // 저장 실패는 무시 — 다음 방문 시 기본값
  }
}

export function storageRemove(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // 삭제 실패는 무시
  }
}

/** sessionStorage 읽기 — 차단 환경에선 null. 렌더 중(useState 초기값)에 불려도 throw하지 않는다. */
export function sessionGet(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

/** sessionStorage 쓰기 — 실패해도 호출부 흐름(로그인·생체 인증 성공 처리)을 막지 않는다. */
export function sessionSet(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    // 저장 실패 시 이번 세션 인증 마킹만 빠진다 — 다음 진입 때 한 번 더 인증
  }
}

/** localStorage 객체 자체 — 사이트 데이터 차단 시 `window.localStorage` 접근만으로 SecurityError가
 * 나므로(Chrome), 객체를 넘겨야 하는 곳(쿼리 캐시 persister)은 이걸로 받고 없으면 기능을 끈다. */
export function getLocalStorageOrUndefined(): Storage | undefined {
  try {
    return typeof window !== "undefined" ? window.localStorage : undefined;
  } catch {
    return undefined;
  }
}
