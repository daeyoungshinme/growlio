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

import { usePushNotifications } from "@/hooks/usePushNotifications";
import { useAuthStore } from "@/stores/authStore";

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
    useAuthStore.setState({ isAuthenticated: true });
  });

  it("does not re-register push on route changes (plans/61 B1)", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Harness />
      </MemoryRouter>,
    );
    await waitFor(() => expect(pushMock.addListener).toHaveBeenCalledTimes(3));

    await act(async () => {
      void harness.navigate?.("/assets");
    });
    await act(async () => {
      void harness.navigate?.("/rebalancing");
    });

    expect(pushMock.register).toHaveBeenCalledTimes(1);
    expect(pushMock.requestPermissions).toHaveBeenCalledTimes(1);
    expect(pushMock.addListener).toHaveBeenCalledTimes(3);
  });
});
