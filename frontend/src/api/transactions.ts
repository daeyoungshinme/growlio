import { apiDelete, apiGet, apiPost, apiPut } from "./client";

export interface Transaction {
  id: string;
  account_id: string | null;
  transaction_type: "DEPOSIT" | "WITHDRAWAL" | "DIVIDEND";
  amount: number;
  fee: number | null;
  transaction_date: string;
  ticker: string | null;
  notes: string | null;
  created_at: string;
}

export interface TransactionCreate {
  account_id?: string;
  transaction_type: "DEPOSIT" | "WITHDRAWAL" | "DIVIDEND";
  amount: number;
  fee?: number;
  transaction_date: string;
  ticker?: string;
  notes?: string;
}

export const fetchTransactions = (params?: {
  account_id?: string;
  year?: number;
  transaction_type?: string;
}) => apiGet<Transaction[]>("/transactions", { params });

export const createTransaction = (data: TransactionCreate) =>
  apiPost<Transaction>("/transactions", data);

export const updateTransaction = (id: string, data: Partial<TransactionCreate>) =>
  apiPut<Transaction>(`/transactions/${id}`, data);

export const deleteTransaction = (id: string) =>
  apiDelete(`/transactions/${id}`);
