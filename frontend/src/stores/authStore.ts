import { create } from "zustand";
import { getSupabase } from "@/lib/supabase";
import { hasStoredSession, readStoredSession } from "@/lib/storedSession";
// 인증 부트스트랩(세션 복원·프로필 동기화·401 재시도) 전용이라 도메인 api 모듈을 거치지 않고 client를 직접 쓴다.
import { api } from "@/api/client";
import { getHttpStatus } from "@/utils/error";
import { BIOMETRIC_SESSION_KEY } from "@/hooks/useBiometric";
import { sessionSet, storageGet, storageRemove, storageSet } from "@/utils/safeStorage";
import { CACHE_OWNER_CHANGED_EVENT, claimCacheOwner } from "@/utils/cacheOwner";
import { usePushNotificationStore } from "@/stores/pushNotificationStore";
import { registerPushToken } from "@/api/settings";

/** 로그아웃이 푸시 토큰 삭제 응답을 기다리는 최대 시간 — api 기본 타임아웃(60s)만큼 막히지 않게 한다. */
const LOGOUT_PUSH_CLEAR_TIMEOUT_MS = 3000;

export const AUTH_ME_CACHE_KEY = "growlio:auth-me";
// /auth/me 재검증을 생략하는 기간 — 지나면 checkAuth가 다시 조회한다
const AUTH_ME_TTL = 30 * 60 * 1000;
// 저장 세션 + /auth/me 캐시가 있으면 이 기간 동안은 검증을 기다리지 않고 바로 로그인 상태로 렌더한다
// (검증은 checkAuth가 백그라운드로 수행, 실패 시 로그아웃). 30분 TTL에 묶여 있으면 30분 넘게 지나 앱을 열 때마다
// SDK 로드 + getSession + /auth/me를 전체 화면 스피너로 기다려 영속 쿼리 캐시가 무의미해졌다.
const OPTIMISTIC_AUTH_MAX_AGE = 7 * 24 * 60 * 60 * 1000;

interface AuthMeCache {
  userId: string;
  needsPasswordReset: boolean;
  cachedAt: number;
}

export interface AuthState {
  isAuthenticated: boolean;
  isAuthChecking: boolean;
  userId: string | null;
  email: string | null;
  needsPasswordReset: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: (onSessionFound?: () => void) => Promise<void>;
  findAccount: (displayName: string) => Promise<string>;
  forgotPassword: (email: string) => Promise<void>;
  resetPassword: (newPassword: string) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  resendConfirmationEmail: (email: string) => Promise<void>;
}

interface OptimisticAuth {
  isAuthChecking: boolean;
  isAuthenticated: boolean;
  userId: string | null;
  needsPasswordReset: boolean;
}

function getOptimisticAuthState(): OptimisticAuth {
  const fallback: OptimisticAuth = {
    isAuthChecking: true,
    isAuthenticated: false,
    userId: null,
    needsPasswordReset: false,
  };
  try {
    const raw = storageGet(AUTH_ME_CACHE_KEY);
    if (!raw) return fallback;
    const cached: AuthMeCache = JSON.parse(raw);
    if (Date.now() - cached.cachedAt >= OPTIMISTIC_AUTH_MAX_AGE) return fallback;
    if (!hasStoredSession()) return fallback;
    // 저장 형식을 해석할 수 있으면 다른 계정의 세션인지도 확인한다
    const stored = readStoredSession();
    if (stored?.userId && stored.userId !== cached.userId) return fallback;
    return {
      isAuthChecking: false,
      isAuthenticated: true,
      userId: cached.userId,
      needsPasswordReset: cached.needsPasswordReset,
    };
  } catch {
    return fallback;
  }
}

/** 비밀번호를 새로 정한 뒤 재설정 안내 배너 플래그를 서버·/auth/me 캐시 양쪽에서 끈다.
 * 비밀번호 변경은 이미 끝났으므로 실패해도 막지 않는다(배너는 다음 재설정 때 다시 시도된다). */
async function markPasswordResetDone(): Promise<void> {
  try {
    await api.post("/auth/password-reset-complete");
    const raw = storageGet(AUTH_ME_CACHE_KEY);
    if (raw) {
      const cached: AuthMeCache = JSON.parse(raw);
      storageSet(
        AUTH_ME_CACHE_KEY,
        JSON.stringify({ ...cached, needsPasswordReset: false } satisfies AuthMeCache),
      );
    }
  } catch {
    /* ignore */
  }
}

export const useAuthStore = create<AuthState>((set, get) => {
  const setLoggedIn = (user: { email?: string | null; id: string }, needsReset = false) => {
    // 이벤트는 동기로 처리되므로 새 사용자 상태로 렌더하기 전에 이전 사용자 캐시가 비워진다
    if (claimCacheOwner(user.id)) window.dispatchEvent(new Event(CACHE_OWNER_CHANGED_EVENT));
    set({
      isAuthenticated: true,
      email: user.email ?? null,
      userId: user.id,
      needsPasswordReset: needsReset,
      isAuthChecking: false,
    });
  };
  const setLoggedOut = () =>
    set({ isAuthenticated: false, userId: null, email: null, isAuthChecking: false });

  const optimistic = getOptimisticAuthState();

  return {
    isAuthenticated: optimistic.isAuthenticated,
    isAuthChecking: optimistic.isAuthChecking,
    userId: optimistic.userId,
    email: null,
    needsPasswordReset: optimistic.needsPasswordReset,

    login: async (email, password) => {
      const supabase = await getSupabase();
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });
      if (error || !data.user) throw new Error(error?.message ?? "Login failed");

      // sync-profile은 멱등(이미 있으면 기존 반환)이므로 await 없이 백그라운드 실행해도 안전.
      api.post("/auth/sync-profile", { display_name: null }).catch(() => {});

      // 이메일/비밀번호 인증 = 생체인증과 동급 → 이번 세션 마킹으로 BiometricGuard 통과
      sessionSet(BIOMETRIC_SESSION_KEY, "1");

      setLoggedIn(data.user);

      // 백그라운드: /auth/me 결과를 캐시 → 다음 앱 재시작 시 낙관적 isAuthChecking=false 가능
      const userId = data.user.id;
      void (async () => {
        try {
          const res = await api.get("/auth/me");
          if (!res?.data) return;
          storageSet(
            AUTH_ME_CACHE_KEY,
            JSON.stringify({
              userId,
              needsPasswordReset: res.data.needs_password_reset ?? false,
              cachedAt: Date.now(),
            } satisfies AuthMeCache),
          );
        } catch {
          /* ignore */
        }
      })();
    },

    register: async (email, password, displayName?) => {
      const supabase = await getSupabase();
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: `${import.meta.env.VITE_REDIRECT_URL}/auth/callback`,
        },
      });
      if (error || !data.user) throw new Error(error?.message ?? "Registration failed");

      if (!data.session) {
        // 이메일 인증 필요 — sync-profile은 인증 후 checkAuth()에서 처리
        throw new Error("EMAIL_CONFIRMATION_REQUIRED");
      }

      await api.post("/auth/sync-profile", { display_name: displayName ?? null });
      setLoggedIn(data.user);
    },

    logout: async () => {
      // FCM 토큰은 기기 단위다 — 지우지 않으면 이 기기가 로그아웃한 계정의 알림을 계속 받는다(plans/61 B2).
      // 인증이 살아 있는 지금 best-effort로 지운다(실패·지연은 로그아웃을 막지 않는다).
      if (usePushNotificationStore.getState().status === "registered") {
        await Promise.race([
          registerPushToken(null).catch(() => undefined),
          new Promise((resolve) => setTimeout(resolve, LOGOUT_PUSH_CLEAR_TIMEOUT_MS)),
        ]);
        usePushNotificationStore.getState().setStatus("idle");
      }
      set({ isAuthenticated: false, userId: null, email: null, needsPasswordReset: false });
      storageRemove(AUTH_ME_CACHE_KEY);
      const supabase = await getSupabase();
      await supabase.auth.signOut();
    },

    checkAuth: async (onSessionFound) => {
      const supabase = await getSupabase();
      let session: Awaited<ReturnType<typeof supabase.auth.getSession>>["data"]["session"];
      try {
        const {
          data: { session: fetchedSession },
        } = await supabase.auth.getSession();
        session = fetchedSession;
      } catch {
        // 세션 조회 자체가 실패하면 isAuthChecking이 영구히 true로 남아
        // PrivateRoute가 스피너에서 벗어나지 못하는 것을 방지
        setLoggedOut();
        return;
      }
      if (session?.user) {
        onSessionFound?.();

        // AUTH_ME_TTL(30분) 이내 동일 유저 캐시가 있으면 네트워크 요청 생략
        try {
          const raw = storageGet(AUTH_ME_CACHE_KEY);
          if (raw) {
            const cached: AuthMeCache = JSON.parse(raw);
            if (cached.userId === session.user.id && Date.now() - cached.cachedAt < AUTH_ME_TTL) {
              setLoggedIn(session.user, cached.needsPasswordReset);
              return;
            }
          }
        } catch {
          // 파싱 실패 시 무시하고 네트워크 요청으로 fallback
        }

        try {
          const { data } = await api.get("/auth/me");
          const needsPasswordReset = data.needs_password_reset ?? false;
          storageSet(
            AUTH_ME_CACHE_KEY,
            JSON.stringify({
              userId: session.user.id,
              needsPasswordReset,
              cachedAt: Date.now(),
            } satisfies AuthMeCache),
          );
          setLoggedIn(session.user, needsPasswordReset);
        } catch (err) {
          // 세션은 있지만 앱 DB에 user 없음 (이메일 인증 후 첫 접속)
          const httpStatus = getHttpStatus(err);
          // 네트워크 오류(오프라인·서버 기상 중)는 인증 실패가 아니다 — 낙관적 로그인 상태로 캐시 화면을
          // 이미 보여주고 있다면 쫓아내지 않는다(다음 checkAuth/요청에서 다시 검증).
          if (
            httpStatus === undefined &&
            get().isAuthenticated &&
            get().userId === session.user.id
          ) {
            set({ email: session.user.email ?? null, isAuthChecking: false });
            return;
          }
          if (httpStatus === 401) {
            try {
              await api.post("/auth/sync-profile", { display_name: null });
              const { data } = await api.get("/auth/me");
              const needsPasswordReset = data.needs_password_reset ?? false;
              storageSet(
                AUTH_ME_CACHE_KEY,
                JSON.stringify({
                  userId: session.user.id,
                  needsPasswordReset,
                  cachedAt: Date.now(),
                } satisfies AuthMeCache),
              );
              setLoggedIn(session.user, needsPasswordReset);
              return;
            } catch {
              // sync-profile도 실패
            }
          }
          setLoggedOut();
        }
      } else {
        setLoggedOut();
      }
    },

    findAccount: async (displayName: string) => {
      const { data } = await api.post("/auth/find-account", { display_name: displayName });
      return data.message as string;
    },

    forgotPassword: async (email: string) => {
      const supabase = await getSupabase();
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/reset-password`,
      });
      if (error) throw error;
    },

    resetPassword: async (newPassword: string) => {
      const supabase = await getSupabase();
      const { error } = await supabase.auth.updateUser({ password: newPassword });
      if (error) throw error;
      set({ needsPasswordReset: false });
      await markPasswordResetDone();
    },

    changePassword: async (currentPassword: string, newPassword: string) => {
      const email = get().email;
      if (!email) throw new Error("로그인 정보를 확인할 수 없습니다.");

      const supabase = await getSupabase();
      // 현재 비밀번호 재인증 — 세션이 유효해도 본인 확인 없이 변경되지 않도록 검증
      const { error: verifyError } = await supabase.auth.signInWithPassword({
        email,
        password: currentPassword,
      });
      if (verifyError) throw new Error("현재 비밀번호가 일치하지 않습니다.");

      const { error } = await supabase.auth.updateUser({ password: newPassword });
      if (error) throw error;
      set({ needsPasswordReset: false });
      await markPasswordResetDone();
    },

    resendConfirmationEmail: async (email: string) => {
      const supabase = await getSupabase();
      const { error } = await supabase.auth.resend({
        type: "signup",
        email,
        options: {
          emailRedirectTo: `${import.meta.env.VITE_REDIRECT_URL}/auth/callback`,
        },
      });
      if (error) throw error;
    },
  };
});
