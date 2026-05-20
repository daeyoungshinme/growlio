import { create } from "zustand";
import { api } from "../api/client";

interface AuthState {
  isAuthenticated: boolean;
  userId: string | null;
  email: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: !!localStorage.getItem("access_token"),
  userId: null,
  email: null,

  login: async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    set({ isAuthenticated: true, email });
  },

  register: async (email, password, displayName?) => {
    await api.post("/auth/register", { email, password, display_name: displayName });
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    set({ isAuthenticated: true, email });
  },

  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    set({ isAuthenticated: false, userId: null, email: null });
  },

  checkAuth: () => {
    const token = localStorage.getItem("access_token");
    set({ isAuthenticated: !!token });
  },
}));
