import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => {
  const mockApi = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  };
  return {
    api: mockApi,
    apiGet: (url: string, ...args: unknown[]) =>
      mockApi.get(url, ...args).then((r: { data: unknown }) => r.data),
    apiPost: (url: string, ...args: unknown[]) =>
      mockApi.post(url, ...args).then((r: { data: unknown }) => r.data),
    apiPut: (url: string, ...args: unknown[]) =>
      mockApi.put(url, ...args).then((r: { data: unknown }) => r.data),
    apiPatch: (url: string, ...args: unknown[]) =>
      mockApi.patch(url, ...args).then((r: { data: unknown }) => r.data),
    apiDelete: (url: string, ...args: unknown[]) =>
      mockApi.delete(url, ...args).then((r: { data: unknown }) => r.data),
  };
});

import { api } from "@/api/client";
import {
  createChallenge,
  deleteChallenge,
  fetchChallengeSummary,
  fetchChallenges,
  updateChallenge,
} from "@/api/challenges";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("challenges API", () => {
  it("fetchChallenges hits GET /challenges", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchChallenges();
    expect(api.get).toHaveBeenCalledWith("/challenges");
  });

  it("fetchChallengeSummary hits GET /challenges/summary", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { needs_attention: false, count: 0 } });
    const res = await fetchChallengeSummary();
    expect(api.get).toHaveBeenCalledWith("/challenges/summary");
    expect(res.count).toBe(0);
  });

  it("createChallenge posts payload", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { id: "c1" } });
    await createChallenge({
      title: "매달 50만원",
      challenge_type: "DEPOSIT",
      target_amount: 500000,
      start_month: "2026-01",
    });
    expect(api.post).toHaveBeenCalledWith(
      "/challenges",
      expect.objectContaining({ title: "매달 50만원", challenge_type: "DEPOSIT" }),
    );
  });

  it("updateChallenge patches by id", async () => {
    vi.mocked(api.patch).mockResolvedValue({ data: { id: "c1" } });
    await updateChallenge("c1", { status: "ARCHIVED" });
    expect(api.patch).toHaveBeenCalledWith("/challenges/c1", { status: "ARCHIVED" });
  });

  it("deleteChallenge deletes by id", async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: null });
    await deleteChallenge("c1");
    expect(api.delete).toHaveBeenCalledWith("/challenges/c1");
  });
});
