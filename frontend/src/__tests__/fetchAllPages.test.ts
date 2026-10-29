import { describe, it, expect, vi } from "vitest";
import { fetchAllPages } from "@/api/fetchAllPages";

describe("fetchAllPages", () => {
  it("짧은 페이지가 올 때까지 skip을 늘려 이어 받는다 (plans/90 B2)", async () => {
    const fetchPage = vi.fn(({ skip }: { skip: number; limit: number }) =>
      Promise.resolve(skip < 4 ? [skip, skip + 1] : [skip]),
    );
    const all = await fetchAllPages(fetchPage, 2);
    expect(all).toEqual([0, 1, 2, 3, 4]);
    expect(fetchPage.mock.calls.map(([p]) => p)).toEqual([
      { skip: 0, limit: 2 },
      { skip: 2, limit: 2 },
      { skip: 4, limit: 2 },
    ]);
  });

  it("끝없이 꽉 찬 페이지가 와도 상한에서 멈춘다", async () => {
    const fetchPage = vi.fn(() => Promise.resolve([1]));
    const all = await fetchAllPages(fetchPage, 1);
    expect(fetchPage).toHaveBeenCalledTimes(20);
    expect(all).toHaveLength(20);
  });
});
