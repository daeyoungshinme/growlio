import { apiGet, apiPost } from "./client";

export interface AuthMe {
  needs_password_reset?: boolean;
}

export const deleteAccount = (password: string) =>
  apiPost<void>("/auth/account/delete", { password });

export const fetchAuthMe = () => apiGet<AuthMe>("/auth/me");

/** 앱 DB에 사용자 행을 만든다(이미 있으면 기존 반환 — 멱등). */
export const syncProfile = () => apiPost<void>("/auth/sync-profile", {});

export const markPasswordResetComplete = () => apiPost<void>("/auth/password-reset-complete");
