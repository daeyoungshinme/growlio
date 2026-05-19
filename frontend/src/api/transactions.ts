import { api } from "./client";

export interface Transaction {
  id: string;
  account_id: string | null;
  transaction_type: "DEPOSIT" | "WITHDRAWAL" | "DIVIDEND";
  amount: number;
  transaction_date: string;
  ticker: string | null;
  notes: string | null;
  created_at: string;
}

export interface TransactionCreate {
  account_id?: string;
  transaction_type: "DEPOSIT" | "WITHDRAWAL" | "DIVIDEND";
  amount: number;
  transaction_date: string;
  ticker?: string;
  notes?: string;
}

export const fetchTransactions = (params?: {
  account_id?: string;
  year?: number;
  transaction_type?: string;
}) => api.get<Transaction[]>("/transactions", { params }).then((r) => r.data);

export const createTransaction = (data: TransactionCreate) =>
  api.post<Transaction>("/transactions", data).then((r) => r.data);

export const updateTransaction = (id: string, data: Partial<TransactionCreate>) =>
  api.put<Transaction>(`/transactions/${id}`, data).then((r) => r.data);

export const deleteTransaction = (id: string) =>
  api.delete(`/transactions/${id}`);
