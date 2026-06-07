import { create } from "zustand";
import { supabase } from "../lib/supabase";
import { api } from "../api/client";

interface AuthState {
  isAuthenticated: boolean;
  isAuthChecking: boolean;
  userId: string | null;
  email: string | null;
  needsPasswordReset: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  findAccount: (displayName: string) => Promise<string>;
  forgotPassword: (email: string) => Promise<void>;
  resetPassword: (newPassword: string) => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => {
  const setLoggedIn = (user: { email?: string | null; id: string }, needsReset = false) =>
    set({ isAuthenticated: true, email: user.email ?? null, userId: user.id, needsPasswordReset: needsReset, isAuthChecking: false });
  const setLoggedOut = () =>
    set({ isAuthenticated: false, userId: null, email: null, isAuthChecking: false });

  return {
    isAuthenticated: false,
    isAuthChecking: true,
    userId: null,
    email: null,
    needsPasswordReset: false,

    login: async (email, password) => {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password });
      if (error || !data.user) throw new Error(error?.message ?? "Login failed");

      // signInWithPassword 직후 세션이 활성화되므로 api interceptor가 토큰을 자동 첨부함.
      // sync-profile은 멱등(이미 있으면 기존 반환)이므로 매 로그인마다 호출해도 안전.
      try {
        await api.post("/auth/sync-profile", { display_name: null });
      } catch {
        // 백엔드 일시 불가 시 로그인 자체는 계속 진행 (checkAuth에서 재시도됨)
      }

      setLoggedIn(data.user);
    },

    register: async (email, password, displayName?) => {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: import.meta.env.VITE_REDIRECT_URL ?? "https://growlio-lovat.vercel.app",
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
      await supabase.auth.signOut();
    },

    checkAuth: async () => {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (session?.user) {
        try {
          const { data } = await api.get("/auth/me");
          setLoggedIn(session.user, data.needs_password_reset ?? false);
        } catch (err) {
          // 세션은 있지만 앱 DB에 user 없음 (이메일 인증 후 첫 접속)
          const httpStatus = (err as { response?: { status?: number } })?.response?.status;
          if (httpStatus === 401) {
            try {
              await api.post("/auth/sync-profile", { display_name: null });
              const { data } = await api.get("/auth/me");
              setLoggedIn(session.user, data.needs_password_reset ?? false);
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
  };
});
