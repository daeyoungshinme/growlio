// supabase-js가 localStorage에 저장한 세션(`sb-<project-ref>-auth-token`)을 SDK 로드 없이 동기로 읽는다.
// SDK(약 200KB)는 지연 로드라 부팅 직후 첫 API 요청이 토큰 없이 나가 401 → refreshSession → 재시도
// 왕복이 생겼다. 저장 형식은 SDK 내부 구현이므로 파싱 실패·형식 변경 시 null을 반환해 기존 경로로 폴백한다.

export interface StoredSession {
  accessToken: string;
  /** 만료 시각(ms epoch) */
  expiresAt: number;
  userId: string | null;
}

// 만료 직전 토큰으로 나가 401이 나는 것을 피하기 위한 여유
const EXPIRY_MARGIN_MS = 30_000;

function findSessionKey(): string | null {
  try {
    return (
      Object.keys(localStorage).find((k) => k.startsWith("sb-") && k.endsWith("-auth-token")) ??
      null
    );
  } catch {
    return null;
  }
}

export function hasStoredSession(): boolean {
  return findSessionKey() !== null;
}

export function readStoredSession(): StoredSession | null {
  const key = findSessionKey();
  if (!key) return null;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const { access_token, expires_at, user } = parsed as {
      access_token?: unknown;
      expires_at?: unknown;
      user?: { id?: unknown } | null;
    };
    if (typeof access_token !== "string" || typeof expires_at !== "number") return null;
    return {
      accessToken: access_token,
      expiresAt: expires_at * 1000,
      userId: typeof user?.id === "string" ? user.id : null,
    };
  } catch {
    return null;
  }
}

/** 아직 유효한 저장 토큰(만료 여유 포함) — 없거나 만료면 null */
export function readValidStoredToken(now: number = Date.now()): string | null {
  const session = readStoredSession();
  if (!session || session.expiresAt - EXPIRY_MARGIN_MS <= now) return null;
  return session.accessToken;
}
