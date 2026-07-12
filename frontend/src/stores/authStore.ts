import { create } from "zustand";
import { supabase } from "@/lib/supabase";
import { api } from "@/api/client";
import { getHttpStatus } from "@/utils/error";
import { BIOMETRIC_SESSION_KEY } from "@/hooks/useBiometric";

export const AUTH_ME_CACHE_KEY = "growlio:auth-me";
const AUTH_ME_TTL = 30 * 60 * 1000;

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
    const raw = localStorage.getItem(AUTH_ME_CACHE_KEY);
    if (!raw) return fallback;
    const cached: AuthMeCache = JSON.parse(raw);
    if (Date.now() - cached.cachedAt >= AUTH_ME_TTL) return fallback;
    const hasSbSession = Object.keys(localStorage).some(
      (k) => k.startsWith("sb-") && k.endsWith("-auth-token"),
    );
    if (!hasSbSession) return fallback;
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

export const useAuthStore = create<AuthState>((set) => {
  const setLoggedIn = (user: { email?: string | null; id: string }, needsReset = false) =>
    set({
      isAuthenticated: true,
      email: user.email ?? null,
      userId: user.id,
      needsPasswordReset: needsReset,
      isAuthChecking: false,
    });
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
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });
      if (error || !data.user) throw new Error(error?.message ?? "Login failed");

      // sync-profile은 멱등(이미 있으면 기존 반환)이므로 await 없이 백그라운드 실행해도 안전.
      api.post("/auth/sync-profile", { display_name: null }).catch(() => {});

      // 이메일/비밀번호 인증 = 생체인증과 동급 → 이번 세션 마킹으로 BiometricGuard 통과
      sessionStorage.setItem(BIOMETRIC_SESSION_KEY, "1");

      setLoggedIn(data.user);

      // 백그라운드: /auth/me 결과를 캐시 → 다음 앱 재시작 시 낙관적 isAuthChecking=false 가능
      const userId = data.user.id;
      void (async () => {
        try {
          const res = await api.get("/auth/me");
          if (!res?.data) return;
          localStorage.setItem(
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
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: import.meta.env.VITE_REDIRECT_URL,
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
      set({ isAuthenticated: false, userId: null, email: null, needsPasswordReset: false });
      localStorage.removeItem(AUTH_ME_CACHE_KEY);
      await supabase.auth.signOut();
    },

    checkAuth: async (onSessionFound) => {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (session?.user) {
        onSessionFound?.();

        // AUTH_ME_TTL(30분) 이내 동일 유저 캐시가 있으면 네트워크 요청 생략
        try {
          const raw = localStorage.getItem(AUTH_ME_CACHE_KEY);
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
          localStorage.setItem(
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
          if (httpStatus === 401) {
            try {
              await api.post("/auth/sync-profile", { display_name: null });
              const { data } = await api.get("/auth/me");
              const needsPasswordReset = data.needs_password_reset ?? false;
              localStorage.setItem(
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
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/reset-password`,
      });
      if (error) throw error;
    },

    resetPassword: async (newPassword: string) => {
      const { error } = await supabase.auth.updateUser({ password: newPassword });
      if (error) throw error;
      set({ needsPasswordReset: false });
    },

    resendConfirmationEmail: async (email: string) => {
      const { error } = await supabase.auth.resend({
        type: "signup",
        email,
        options: {
          emailRedirectTo: import.meta.env.VITE_REDIRECT_URL,
        },
      });
      if (error) throw error;
    },
  };
});
