import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { fetchAccounts } from "@/api/assets";
import { fetchPortfolios } from "@/api/portfolios";
import { updateAutoDca, type SettingsData } from "@/api/settings";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { SectionCard, inputClass, labelClass } from "./shared";

interface Props {
  current: SettingsData | null;
  onSettingsChange: () => void;
  flat?: boolean;
}

export function DCASettingsSection({ current, onSettingsChange, flat = false }: Props) {
  const [dcaForm, setDcaForm] = useState(() => ({
    enabled: current?.auto_dca_enabled ?? false,
    day: current?.auto_dca_day ? String(current.auto_dca_day) : "1",
    amount: current?.auto_dca_amount ? String(current.auto_dca_amount) : "",
    portfolio_id: current?.auto_dca_portfolio_id ?? "",
    account_id: current?.auto_dca_account_id ?? "",
  }));

  const { data: portfolios = [] } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
    staleTime: STALE_TIME.MEDIUM,
  });

  const { data: accounts = [] } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
    staleTime: STALE_TIME.MEDIUM,
  });

  const kisAccounts = accounts.filter((a) => a.asset_type === "STOCK_KIS" && a.is_active);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateAutoDca({
        enabled: dcaForm.enabled,
        day: dcaForm.day ? Number(dcaForm.day) : null,
        amount: dcaForm.amount ? Number(dcaForm.amount) : null,
        portfolio_id: dcaForm.portfolio_id || null,
        account_id: dcaForm.account_id || null,
      }),
    onSuccess: () => {
      toast("자동 정기매수 설정이 저장되었습니다", "success");
      onSettingsChange();
    },
    onError: (e) => toast(extractErrorMessage(e, "저장에 실패했습니다"), "error"),
  });

  const inner = (
    <>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        매월 설정한 날에 지정 포트폴리오 비중대로 KIS 계좌에서 자동 매수합니다. 실거래 주문이
        실행되므로 신중히 설정하세요.
      </p>
      <div className="flex items-center gap-3">
        <label className="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            checked={dcaForm.enabled}
            onChange={(e) => setDcaForm((f) => ({ ...f, enabled: e.target.checked }))}
            className="sr-only peer"
          />
          <div className="w-11 h-6 bg-gray-200 dark:bg-gray-700 peer-focus:ring-2 peer-focus:ring-blue-500 rounded-full peer peer-checked:bg-blue-600 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-full" />
        </label>
        <span className="text-sm text-gray-700 dark:text-gray-300 font-medium">
          {dcaForm.enabled ? "자동매수 활성화" : "자동매수 비활성화"}
        </span>
      </div>
      {dcaForm.enabled && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>실행일 (매월)</label>
              <select
                className={inputClass}
                value={dcaForm.day}
                onChange={(e) => setDcaForm((f) => ({ ...f, day: e.target.value }))}
              >
                {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                  <option key={d} value={d}>
                    {d}일
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass}>월 매수 금액 (원)</label>
              <input
                type="number"
                inputMode="decimal"
                className={inputClass}
                value={dcaForm.amount}
                onChange={(e) => setDcaForm((f) => ({ ...f, amount: e.target.value }))}
                placeholder="500000"
                min="0"
              />
            </div>
          </div>
          <div>
            <label className={labelClass}>비중 기준 포트폴리오</label>
            <select
              className={inputClass}
              value={dcaForm.portfolio_id}
              onChange={(e) => setDcaForm((f) => ({ ...f, portfolio_id: e.target.value }))}
            >
              <option value="">선택하세요</option>
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass}>매수 실행 계좌 (KIS)</label>
            <select
              className={inputClass}
              value={dcaForm.account_id}
              onChange={(e) => setDcaForm((f) => ({ ...f, account_id: e.target.value }))}
            >
              <option value="">선택하세요</option>
              {kisAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
            {kisAccounts.length === 0 && (
              <p className="text-xs text-orange-500 dark:text-orange-400 mt-1">
                KIS 계좌를 먼저 등록해주세요.
              </p>
            )}
          </div>
        </div>
      )}
      <button
        onClick={() => saveMutation.mutate()}
        disabled={saveMutation.isPending}
        aria-busy={saveMutation.isPending}
        className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
      >
        {saveMutation.isPending ? "저장 중..." : "저장"}
      </button>
      {current?.auto_dca_last_executed_at && (
        <p className="text-xs text-gray-400 dark:text-gray-500">
          마지막 자동매수: {new Date(current.auto_dca_last_executed_at).toLocaleString("ko-KR")}
        </p>
      )}
    </>
  );

  if (flat) return <div className="space-y-4">{inner}</div>;

  return <SectionCard title="자동 정기매수 (DCA)">{inner}</SectionCard>;
}
