import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("@/api/settings", () => ({
  updateNotificationEmail: vi.fn().mockResolvedValue({}),
  sendTestEmail: vi.fn().mockResolvedValue({}),
}));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

import { NotificationEmailSection } from "@/components/settings/NotificationEmailSection";
import { updateNotificationEmail } from "@/api/settings";

describe("NotificationEmailSection (plans/117 C1)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("저장된 알림 이메일을 보여주고 저장하면 그 값을 그대로 보낸다", async () => {
    render(
      <NotificationEmailSection
        userEmail="login@example.com"
        savedEmail="me@work.com"
        onSettingsChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("textbox")).toHaveValue("me@work.com");
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(updateNotificationEmail).toHaveBeenCalledWith("me@work.com"));
  });

  it("알림 이메일이 없으면 비워두고 로그인 이메일은 placeholder로만 보인다", () => {
    render(
      <NotificationEmailSection
        userEmail="login@example.com"
        savedEmail={null}
        onSettingsChange={vi.fn()}
      />,
    );
    const input = screen.getByRole("textbox");
    expect(input).toHaveValue("");
    expect(input).toHaveAttribute("placeholder", "login@example.com");
  });
});
