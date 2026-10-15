import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from "vitest";
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";

const refreshSession = vi.fn();

vi.mock("@/lib/supabase", () => ({
  getSupabase: () =>
    Promise.resolve({
      auth: {
        getSession: () => Promise.resolve({ data: { session: null } }),
        onAuthStateChange: vi.fn(),
        refreshSession,
      },
    }),
}));

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

const { api } = await import("@/api/client");

let validToken = "";

/** Authorization이 이번 테스트의 유효 토큰이 아니면 401을 내는 가짜 어댑터 — 만료 토큰으로 나간 요청을 흉내낸다.
 * client.ts는 갱신한 토큰을 모듈 변수에 캐시하므로 테스트마다 유효 토큰을 바꿔 이전 테스트의 캐시를 무효로 만든다. */
function installAdapter() {
  const seen: { url?: string; auth?: string }[] = [];
  api.defaults.adapter = (config: InternalAxiosRequestConfig) => {
    const auth = config.headers?.["Authorization"] as string | undefined;
    seen.push({ url: config.url, auth });
    if (auth === `Bearer ${validToken}`) {
      const res: AxiosResponse = {
        data: { ok: config.url },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      };
      return Promise.resolve(res);
    }
    const res: AxiosResponse = {
      data: {},
      status: 401,
      statusText: "Unauthorized",
      headers: {},
      config,
    };
    return Promise.reject(new AxiosError("401", "ERR_BAD_REQUEST", config, null, res));
  };
  return seen;
}

describe("api client 401 refresh queue", () => {
  let expired: Mock<(e: Event) => void>;

  let testNo = 0;

  beforeEach(() => {
    validToken = `fresh-${++testNo}`;
    refreshSession.mockReset();
    expired = vi.fn<(e: Event) => void>();
    window.addEventListener("growlio:session-expired", expired);
  });

  afterEach(() => {
    window.removeEventListener("growlio:session-expired", expired);
  });

  it("401이면 세션을 갱신하고 새 토큰으로 한 번 재시도한다", async () => {
    const seen = installAdapter();
    refreshSession.mockResolvedValue({ data: { session: { access_token: validToken } } });

    const res = await api.get("/dashboard");

    expect(res.data).toEqual({ ok: "/dashboard" });
    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(seen[seen.length - 1]?.auth).toBe(`Bearer ${validToken}`);
    expect(expired).not.toHaveBeenCalled();
  });

  it("동시에 401이 나도 갱신은 한 번만 하고 대기 요청은 새 토큰으로 재시도된다", async () => {
    installAdapter();
    let resolveRefresh: (v: unknown) => void = () => {};
    refreshSession.mockReturnValue(new Promise((r) => (resolveRefresh = r)));

    const first = api.get("/a");
    const second = api.get("/b");
    // 두 요청이 모두 401을 받고 두 번째가 큐에 들어갈 때까지 기다린다
    await vi.waitFor(() => expect(refreshSession).toHaveBeenCalledTimes(1));
    await new Promise((r) => setTimeout(r, 0));
    resolveRefresh({ data: { session: { access_token: validToken } } });

    const [a, b] = await Promise.all([first, second]);
    expect(a.data).toEqual({ ok: "/a" });
    expect(b.data).toEqual({ ok: "/b" });
    expect(refreshSession).toHaveBeenCalledTimes(1);
  });

  it("갱신 결과 세션이 없으면 세션 만료 이벤트를 보내고 요청을 실패시킨다", async () => {
    installAdapter();
    refreshSession.mockResolvedValue({ data: { session: null } });

    await expect(api.get("/dashboard")).rejects.toBeInstanceOf(AxiosError);
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it("/auth/ 엔드포인트의 401은 갱신을 시도하지 않는다", async () => {
    installAdapter();

    await expect(api.post("/auth/sync-profile")).rejects.toBeInstanceOf(AxiosError);
    expect(refreshSession).not.toHaveBeenCalled();
  });
});
