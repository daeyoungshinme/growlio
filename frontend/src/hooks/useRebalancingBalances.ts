import { useQueryClient } from "@tanstack/react-query";
import { AssetAccount } from "../api/assets";
import {
  KisBalanceResponse,
  fetchAllBrokerBalances,
  fetchBrokerBalance,
} from "../api/rebalancing";
import { QUERY_KEYS } from "../constants/queryKeys";
import { extractErrorMessage } from "../utils/error";
import { toast } from "../utils/toast";
import type { ExecutionAction } from "./useRebalancingExecution";

export function useRebalancingBalances(
  dispatch: React.Dispatch<ExecutionAction>,
  kisAccounts: AssetAccount[]
) {
  const queryClient = useQueryClient();

  async function loadLiveBalance(accountId: string) {
    dispatch({ type: "BALANCE_LOADING", accountId });
    try {
      const res: KisBalanceResponse = await fetchBrokerBalance(accountId);
      dispatch({ type: "BALANCE_LOADED", accountId, positions: res.positions, deposit: res.deposit_krw, orderable: res.orderable_krw });
    } catch (err: unknown) {
      const is404 = (err as { response?: { status?: number } }).response?.status === 404;
      dispatch({ type: "BALANCE_ERROR", accountId, is404 });
      if (is404) {
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.accounts });
      } else {
        toast(extractErrorMessage(err, "잔고 조회에 실패했습니다"), "error");
      }
    }
  }

  async function loadAllLiveBalances() {
    if (kisAccounts.length === 0) return;
    dispatch({ type: "BALANCES_START", accountIds: kisAccounts.map((a) => a.id) });
    try {
      const responses: KisBalanceResponse[] = await fetchAllBrokerBalances();
      const balances: Record<string, import("../api/rebalancing").KisBalancePosition[]> = {};
      const deposits: Record<string, number> = {};
      const orderables: Record<string, number> = {};
      const states: Record<string, import("./useRebalancingExecution").BalanceLoadState> = {};
      responses.forEach((res) => {
        if (res.error) {
          states[res.account_id] = "error";
        } else {
          balances[res.account_id] = res.positions;
          deposits[res.account_id] = res.deposit_krw;
          if (res.orderable_krw !== null && res.orderable_krw !== undefined) {
            orderables[res.account_id] = res.orderable_krw;
          }
          states[res.account_id] = "loaded";
        }
      });
      dispatch({ type: "BALANCES_LOADED", balances, deposits, orderables, states });
    } catch {
      dispatch({ type: "BALANCES_ERROR", accountIds: kisAccounts.map((a) => a.id) });
    }
  }

  return { loadLiveBalance, loadAllLiveBalances };
}
