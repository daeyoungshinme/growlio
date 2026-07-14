import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck2 } from "lucide-react";
import { fetchIsaStatus, type IsaAccountStatus } from "@/api/tax";
import { updateIsaPnlOverride } from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateAccountData } from "@/utils/queryInvalidation";
import { INPUT_SM } from "@/constants/inputStyles";
import { fmtKrw } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";

function MaturityBadge({ status }: { status: IsaAccountStatus }) {
  if (status.needs_open_date) {
    return (
      <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">
        가입일 미입력
      </span>
    );
  }
  if (status.is_mature) {
    return (
      <span className="px-2 py-0.5 text-xs rounded-full bg-green-50 dark:bg-green-950 text-green-600 dark:text-green-400">
        의무가입 충족
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 text-xs rounded-full bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400">
      D-{status.days_remaining}
    </span>
  );
}

function IsaAccountRow({ status }: { status: IsaAccountStatus }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(String(status.estimated_cumulative_pnl_krw));

  const mutation = useMutation({
    mutationFn: (pnl: number | null) => updateIsaPnlOverride(status.account_id, pnl),
    onSuccess: async () => {
      await invalidateAccountData(qc);
      toast("저장되었습니다", "success");
      setEditing(false);
    },
    onError: (err) => toast(extractErrorMessage(err), "error"),
  });

  const limitPct = Math.min(
    Math.max((status.estimated_cumulative_pnl_krw / status.tax_free_limit_krw) * 100, 0),
    100,
  );

  return (
    <div className="py-2.5 border-b border-gray-100 dark:border-gray-700 last:border-b-0">
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
          {status.account_name}
        </span>
        <MaturityBadge status={status} />
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className={`text-sm font-semibold ${pnlColor(status.estimated_cumulative_pnl_krw)}`}>
          {fmtKrw(status.estimated_cumulative_pnl_krw)}
        </span>
        <span className="text-xs text-gray-400 dark:text-gray-500">
          한도 {fmtKrw(status.tax_free_limit_krw)}
        </span>
      </div>
      <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1 mt-1">
        <div
          className={`h-full rounded-full ${status.taxable_excess_krw > 0 ? "bg-amber-500" : "bg-blue-500"}`}
          style={{ width: `${limitPct}%` }}
        />
      </div>
      {status.taxable_excess_krw > 0 && (
        <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
          한도 초과 {fmtKrw(status.taxable_excess_krw)} · 예상세금{" "}
          {fmtKrw(status.estimated_tax_krw)}
          (9.9%)
        </p>
      )}
      <div className="mt-1.5">
        {editing ? (
          <div className="flex items-center gap-2">
            <input
              type="number"
              className={`${INPUT_SM} w-32`}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="누적손익(원)"
            />
            <button
              onClick={() => mutation.mutate(Number(value) || 0)}
              disabled={mutation.isPending}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-50"
            >
              저장
            </button>
            <button
              onClick={() => setEditing(false)}
              className="text-xs text-gray-400 dark:text-gray-500 hover:underline"
            >
              취소
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <button
              onClick={() => setEditing(true)}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
            >
              직접 입력
            </button>
            {status.is_manual_override && (
              <button
                onClick={() => mutation.mutate(null)}
                disabled={mutation.isPending}
                className="text-xs text-gray-400 dark:text-gray-500 hover:underline disabled:opacity-50"
              >
                자동 추정으로 되돌리기
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** ISA 계좌의 의무가입(3년) 진행 상황과 비과세 한도 대비 예상 세금을 보여준다. ISA 계좌가 없으면 표시하지 않는다. */
export default function IsaMaturityCard({ embedded = false }: { embedded?: boolean }) {
  const { data } = useQuery({
    queryKey: QUERY_KEYS.isaStatus,
    queryFn: fetchIsaStatus,
    staleTime: STALE_TIME.MEDIUM,
  });

  if (!data || data.accounts.length === 0) return null;

  const body = (
    <>
      <div>
        {data.accounts.map((status) => (
          <IsaAccountRow key={status.account_id} status={status} />
        ))}
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">{data.note}</p>
    </>
  );

  if (embedded) {
    return (
      <div>
        <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase mb-1.5">
          ISA 만기·세제 현황
        </p>
        {body}
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 flex items-center gap-1.5">
          <CalendarCheck2 size={16} className="text-blue-500" />
          ISA 만기·세제 현황
        </h2>
      </div>
      {body}
    </div>
  );
}
