import { create } from "zustand";

export type PushNotificationStatus =
  | "idle"
  | "unsupported"
  | "requesting"
  | "denied"
  | "registered"
  | "disabled"
  | "error";

interface PushNotificationState {
  status: PushNotificationStatus;
  setStatus: (status: PushNotificationStatus) => void;
}

/** usePushNotifications.ts(App.tsx 전역 마운트)가 갱신하는 등록 상태 — SettingsPage가 읽기 전용으로 구독. */
export const usePushNotificationStore = create<PushNotificationState>((set) => ({
  status: "idle",
  setStatus: (status) => set({ status }),
}));
