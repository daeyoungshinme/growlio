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
