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
    apiGet: (url: string, ...args: unknown[]) => mockApi.get(url, ...args).then((r: { data: unknown }) => r.data),
    apiPost: (url: string, ...args: unknown[]) => mockApi.post(url, ...args).then((r: { data: unknown }) => r.data),
    apiPut: (url: string, ...args: unknown[]) => mockApi.put(url, ...args).then((r: { data: unknown }) => r.data),
    apiPatch: (url: string, ...args: unknown[]) => mockApi.patch(url, ...args).then((r: { data: unknown }) => r.data),
    apiDelete: (url: string, ...args: unknown[]) => mockApi.delete(url, ...args).then((r: { data: unknown }) => r.data),
  };
});

import { api } from "@/api/client";
import {
  fetchTransactions,
  createTransaction,
  updateTransaction,
  deleteTransaction,
} from "@/api/transactions";

const mockTx = {
  id: "tx-1",
  account_id: "acc-1",
  transaction_type: "DEPOSIT" as const,
  amount: 1000000,
  fee: null,
  transaction_date: "2024-01-01",
  ticker: null,
  notes: null,
  created_at: "2024-01-01T00:00:00Z",
};

describe("api/transactions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchTransactions calls GET /transactions without params", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [mockTx] });
    const result = await fetchTransactions();
    expect(api.get).toHaveBeenCalledWith("/transactions", { params: undefined });
    expect(result).toEqual([mockTx]);
  });

  it("fetchTransactions calls GET /transactions with params", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [mockTx] });
    await fetchTransactions({ account_id: "acc-1", year: 2024 });
    expect(api.get).toHaveBeenCalledWith("/transactions", {
      params: { account_id: "acc-1", year: 2024 },
    });
  });

  it("createTransaction calls POST /transactions", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: mockTx });
    const body = {
      transaction_type: "DEPOSIT" as const,
      amount: 1000000,
      transaction_date: "2024-01-01",
    };
    const result = await createTransaction(body);
    expect(api.post).toHaveBeenCalledWith("/transactions", body);
    expect(result).toEqual(mockTx);
  });

  it("updateTransaction calls PUT /transactions/:id", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: mockTx });
    const result = await updateTransaction("tx-1", { amount: 2000000 });
    expect(api.put).toHaveBeenCalledWith("/transactions/tx-1", { amount: 2000000 });
    expect(result).toEqual(mockTx);
  });

  it("deleteTransaction calls DELETE /transactions/:id", async () => {
    vi.mocked(api.delete).mockResolvedValue({});
    await deleteTransaction("tx-1");
    expect(api.delete).toHaveBeenCalledWith("/transactions/tx-1");
  });
});
