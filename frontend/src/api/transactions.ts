import { apiDelete, apiGet, apiPost, apiPut } from "./client";
import { fetchAllPages } from "./fetchAllPages";
import type { TxType } from "@/constants/transaction";

export interface Transaction {
  id: string;
  account_id: string | null;
  transaction_type: TxType;
  amount: number;
  fee: number | null;
  transaction_date: string;
  ticker: string | null;
  notes: string | null;
  created_at: string;
}

export interface TransactionCreate {
  account_id?: string;
  transaction_type: TxType;
  amount: number;
  fee?: number;
  transaction_date: string;
  ticker?: string;
  notes?: string;
}

type TransactionListParams = {
  account_id?: string;
  year?: number;
  transaction_type?: string;
};

export const fetchTransactions = (
  params?: TransactionListParams & { skip?: number; limit?: number },
) => apiGet<Transaction[]>("/transactions", { params });

/** 조건에 맞는 거래 전체(페이지를 끝까지 이어 받음) — 화면에서 거르거나 더하는 목록용 */
export const fetchAllTransactions = (params?: TransactionListParams) =>
  fetchAllPages((page) => fetchTransactions({ ...params, ...page }));

export interface TransactionTotal {
  account_id: string | null;
  transaction_type: TxType;
  total_amount: number;
  count: number;
}

/** 계좌·유형별 거래 합계(서버 집계) — 필터는 목록과 같다 */
export const fetchTransactionSummary = (params?: { account_id?: string; year?: number }) =>
  apiGet<TransactionTotal[]>("/transactions/summary", { params });

export const createTransaction = (data: TransactionCreate) =>
  apiPost<Transaction>("/transactions", data);

export const updateTransaction = (id: string, data: Partial<TransactionCreate>) =>
  apiPut<Transaction>(`/transactions/${id}`, data);

export const deleteTransaction = (id: string) => apiDelete(`/transactions/${id}`);
