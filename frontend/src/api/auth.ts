import { apiPost } from "./client";

export const deleteAccount = (password: string) =>
  apiPost<void>("/auth/account/delete", { password });
