import { describe, expect, it, vi } from "vitest";

type Listener = (event: string) => void;
const listeners: Listener[] = [];

vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      onAuthStateChange: (cb: Listener) => {
        listeners.push(cb);
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      },
    },
  }),
}));

describe("consumePasswordRecovery", () => {
  it("부팅 시 기록한 PASSWORD_RECOVERY를 한 번만 돌려준다", async () => {
    const { getSupabase, consumePasswordRecovery } = await import("@/lib/supabase");
    await getSupabase();

    expect(consumePasswordRecovery()).toBe(false);
    listeners.forEach((cb) => cb("PASSWORD_RECOVERY"));

    expect(consumePasswordRecovery()).toBe(true);
    // 같은 탭에서 나중에 재설정 페이지를 다시 열면 일반 로그인 세션만으로는 폼이 열리지 않아야 한다
    expect(consumePasswordRecovery()).toBe(false);
  });
});
