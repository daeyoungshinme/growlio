import { useEffect } from "react";
import { act, render, waitFor } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.hoisted(() => ({
  requestPermissions: vi.fn(async () => ({ receive: "granted" })),
  register: vi.fn(async () => undefined),
  addListener: vi.fn(async () => ({ remove: vi.fn(async () => undefined) })),
}));

vi.mock("@capacitor/push-notifications", () => ({ PushNotifications: pushMock }));
vi.mock("@/utils/platform", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/utils/platform")>()),
  isNativePlatform: () => true,
}));
vi.mock("@/api/settings", () => ({ registerPushToken: vi.fn(async () => undefined) }));

import {
  disablePushNotifications,
  retryPushRegistration,
  usePushNotifications,
} from "@/hooks/usePushNotifications";
import { pushOptOutKey } from "@/constants/storageKeys";
import { useAuthStore } from "@/stores/authStore";
import { usePushNotificationStore } from "@/stores/pushNotificationStore";

const harness: { navigate: ReturnType<typeof useNavigate> | null } = { navigate: null };

function Harness() {
  usePushNotifications();
  const navigate = useNavigate();
  useEffect(() => {
    harness.navigate = navigate;
  }, [navigate]);
  return null;
}

describe("usePushNotifications lifecycle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useAuthStore.setState({ isAuthenticated: true, userId: "user-1" });
  });

  it("does not re-register push on route changes (plans/61 B1)", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Harness />
      </MemoryRouter>,
    );
    await waitFor(() => expect(pushMock.addListener).toHaveBeenCalledTimes(4));

    await act(async () => {
      void harness.navigate?.("/assets");
    });
    await act(async () => {
      void harness.navigate?.("/rebalancing");
    });

    expect(pushMock.register).toHaveBeenCalledTimes(1);
    expect(pushMock.requestPermissions).toHaveBeenCalledTimes(1);
    expect(pushMock.addListener).toHaveBeenCalledTimes(4);
  });

  it("권한 요청이 throw하면 requesting에 멈추지 않고 error로 바꾼다(plans/115 B4)", async () => {
    pushMock.requestPermissions.mockRejectedValueOnce(new Error("plugin missing"));
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Harness />
      </MemoryRouter>,
    );
    await waitFor(() => expect(usePushNotificationStore.getState().status).toBe("error"));
    expect(pushMock.register).not.toHaveBeenCalled();
  });

  it("설정에서 끈 푸시는 앱을 다시 켜도 자동 등록하지 않는다(plans/117 C2)", async () => {
    await disablePushNotifications();
    expect(localStorage.getItem(pushOptOutKey("user-1"))).toBe("1");

    render(
      <MemoryRouter initialEntries={["/"]}>
        <Harness />
      </MemoryRouter>,
    );
    await waitFor(() => expect(usePushNotificationStore.getState().status).toBe("disabled"));
    expect(pushMock.requestPermissions).not.toHaveBeenCalled();
    expect(pushMock.register).not.toHaveBeenCalled();
    // 다시 켤 때 토큰을 받을 리스너는 붙어 있어야 한다
    expect(pushMock.addListener).toHaveBeenCalledTimes(4);

    await retryPushRegistration();
    expect(localStorage.getItem(pushOptOutKey("user-1"))).toBeNull();
    expect(pushMock.register).toHaveBeenCalledTimes(1);
  });

  it("거부된 뒤에도 리스너를 붙여 두어 다시 시도가 토큰을 받는다(plans/117 C3)", async () => {
    pushMock.requestPermissions.mockResolvedValueOnce({ receive: "denied" });
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Harness />
      </MemoryRouter>,
    );
    await waitFor(() => expect(usePushNotificationStore.getState().status).toBe("denied"));
    expect(pushMock.addListener).toHaveBeenCalledTimes(4);
  });

  it("다시 시도 중 예외가 나면 requesting에 멈추지 않는다(plans/117 C3)", async () => {
    pushMock.requestPermissions.mockRejectedValueOnce(new Error("boom"));
    await retryPushRegistration();
    expect(usePushNotificationStore.getState().status).toBe("error");
  });
});
