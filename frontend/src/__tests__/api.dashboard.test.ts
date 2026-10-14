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
import { fetchDashboard } from "@/api/dashboard";

describe("api/dashboard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchDashboard calls GET /dashboard", async () => {
    const mockData = { total_assets_krw: 10000000 };
    vi.mocked(api.get).mockResolvedValue({ data: mockData });
    const result = await fetchDashboard();
    expect(api.get).toHaveBeenCalledWith("/dashboard");
    expect(result).toEqual(mockData);
  });
});
