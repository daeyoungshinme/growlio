import { create } from "zustand";
import { api } from "../api/client";

interface AuthState {
  isAuthenticated: boolean;
  isAuthChecking: boolean;
  userId: string | null;
  email: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
  findAccount: (displayName: string) => Promise<string[]>;
  forgotPassword: (email: string) => Promise<void>;
  resetPassword: (token: string, newPassword: string) => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: false,
  isAuthChecking: true,
  userId: null,
  email: null,

  login: async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    set({ isAuthenticated: true, email: data.email, userId: String(data.id), isAuthChecking: false });
  },

  register: async (email, password, displayName?) => {
    await api.post("/auth/register", { email, password, display_name: displayName });
    const { data } = await api.post("/auth/login", { email, password });
    set({ isAuthenticated: true, email: data.email, userId: String(data.id), isAuthChecking: false });
  },

  logout: async () => {
    set({ isAuthenticated: false, userId: null, email: null });
    try {
      await api.post("/auth/logout");
    } catch {
      // 서버 쿠키 삭제 실패해도 로컬 상태는 이미 초기화됨
    }
  },

  checkAuth: async () => {
    try {
      const { data } = await api.get("/auth/me");
      set({ isAuthenticated: true, email: data.email, userId: String(data.id), isAuthChecking: false });
    } catch {
      set({ isAuthenticated: false, userId: null, email: null, isAuthChecking: false });
    }
  },

  findAccount: async (displayName: string) => {
    const { data } = await api.post("/auth/find-account", { display_name: displayName });
    return data.masked_emails as string[];
  },

  forgotPassword: async (email: string) => {
    await api.post("/auth/forgot-password", { email });
  },

  resetPassword: async (token: string, newPassword: string) => {
    await api.post("/auth/reset-password", { token, new_password: newPassword });
  },
}));
