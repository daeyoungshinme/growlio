import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export type ChallengeType = "DEPOSIT" | "RETURN_PCT" | "TARGET_VALUE";
export type ChallengeStatus = "ACTIVE" | "COMPLETED" | "ARCHIVED";

export interface ChallengeMonth {
  month: string; // "2026-01"
  net_krw: number;
  satisfied: boolean; // 순입금 > 0
  target_met: boolean; // 순입금 >= 월 목표액
}

export interface ChallengeProgress {
  progress_pct: number | null;
  current_streak: number;
  longest_streak: number;
  this_month_net_krw: number;
  this_month_satisfied: boolean;
  this_month_target_met: boolean;
  current_value_krw: number | null;
  current_return_pct: number | null;
  months: ChallengeMonth[];
}

export interface Challenge {
  id: string;
  title: string;
  challenge_type: ChallengeType;
  target_amount: number | null;
  target_pct: number | null;
  target_months: number | null;
  account_id: string | null;
  start_month: string;
  deadline_month: string | null;
  reminder_enabled: boolean;
  status: ChallengeStatus;
  completed_at: string | null;
  created_at: string;
  progress: ChallengeProgress;
}

export interface ChallengeSummary {
  needs_attention: boolean;
  count: number;
}

export interface ChallengeCreatePayload {
  title: string;
  challenge_type: ChallengeType;
  target_amount?: number | null;
  target_pct?: number | null;
  target_months?: number | null;
  account_id?: string | null;
  start_month: string;
  deadline_month?: string | null;
  reminder_enabled?: boolean;
}

export interface ChallengeUpdatePayload {
  title?: string;
  target_amount?: number | null;
  target_pct?: number | null;
  target_months?: number | null;
  deadline_month?: string | null;
  reminder_enabled?: boolean;
  status?: ChallengeStatus;
}

export const fetchChallenges = (): Promise<Challenge[]> => apiGet<Challenge[]>("/challenges");

export const fetchChallengeSummary = (): Promise<ChallengeSummary> =>
  apiGet<ChallengeSummary>("/challenges/summary");

export const createChallenge = (payload: ChallengeCreatePayload): Promise<Challenge> =>
  apiPost<Challenge>("/challenges", payload);

export const updateChallenge = (id: string, payload: ChallengeUpdatePayload): Promise<Challenge> =>
  apiPatch<Challenge>(`/challenges/${id}`, payload);

export const deleteChallenge = (id: string): Promise<unknown> => apiDelete(`/challenges/${id}`);
