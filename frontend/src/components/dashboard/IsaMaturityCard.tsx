import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchIsaStatus, type IsaAccountStatus } from "@/api/tax";
import { updateIsaPnlOverride } from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateAccountData } from "@/utils/queryInvalidation";
import { INPUT_SM } from "@/constants/inputStyles";
import { fmtKrw, fmtKrwPreview, parseYmd } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";
import SegmentedControl from "@/components/portfolio/allocation/SegmentedControl";

/** 백엔드 date("YYYY-MM-DD") → "M/D". `new Date()`는 UTC 자정으로 해석해 UTC보다 늦은 타임존에서 전날이 된다. */
function fmtMonthDay(ymd: string): string {
  const { month, day } = parseYmd(ymd);
  return `${month}/${day}`;
}

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
  // 숫자 키패드엔 마이너스 키가 없어 손실을 입력할 수 없다 — 부호는 토글로 받고 칸엔 절댓값만
  const [pnlSign, setPnlSign] = useState<"GAIN" | "LOSS">(
    status.estimated_cumulative_pnl_krw < 0 ? "LOSS" : "GAIN",
  );
  const [value, setValue] = useState(String(Math.abs(status.estimated_cumulative_pnl_krw)));
  const signedValue = (Number(value) || 0) * (pnlSign === "LOSS" ? -1 : 1);

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
      {status.tax_saved_krw > 0 && (
        <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
          {status.is_mature
            ? `의무가입 충족 · 지금 인출 시 일반계좌 대비 약 ${fmtKrw(status.tax_saved_krw)} 절세`
            : `현재까지 누적 기준 일반계좌 대비 약 ${fmtKrw(status.tax_saved_krw)} 절세 예상`}
          {status.tax_calculation_basis === "MANUAL_OVERRIDE_APPROX" && (
            <span className="text-gray-400 dark:text-gray-500"> (직접입력 기준 근사치)</span>
          )}
        </p>
      )}
      <div className="mt-1.5">
        {editing ? (
          <div>
            <label
              htmlFor={`isa-pnl-${status.account_id}`}
              className="block text-xs text-gray-500 dark:text-gray-400 mb-1"
            >
              오늘 기준 누적손익 (원)
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <SegmentedControl
                ariaLabel="누적손익 부호"
                options={[
                  { value: "GAIN", label: "이익" },
                  { value: "LOSS", label: "손실" },
                ]}
                value={pnlSign}
                onChange={setPnlSign}
              />
              <input
                id={`isa-pnl-${status.account_id}`}
                type="text"
                inputMode="numeric"
                className={`${INPUT_SM} flex-1 sm:flex-none sm:w-36 min-w-0`}
                value={value}
                onChange={(e) => setValue(e.target.value.replace(/[^0-9]/g, ""))}
                placeholder="0"
              />
              <button
                onClick={() => mutation.mutate(signedValue)}
                disabled={mutation.isPending}
                className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} px-2 text-xs text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-50`}
              >
                저장
              </button>
              <button
                onClick={() => setEditing(false)}
                className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} px-2 text-xs text-gray-400 dark:text-gray-500 hover:underline`}
              >
                취소
              </button>
            </div>
            {value !== "" && !Number.isNaN(Number(value)) && (
              <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mt-1">
                {fmtKrwPreview(signedValue)}
              </p>
            )}
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              입력한 금액을 오늘 기준으로 저장하고, 이후 가격변동·배당은 자동으로 반영됩니다.
            </p>
          </div>
        ) : (
          <div className="flex items-center gap-3 flex-wrap">
            <button
              onClick={() => setEditing(true)}
              className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} px-2 text-xs text-blue-600 dark:text-blue-400 hover:underline`}
            >
              직접 입력
            </button>
            {status.is_manual_override && (
              <button
                onClick={() => mutation.mutate(null)}
                disabled={mutation.isPending}
                className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} px-2 text-xs text-gray-400 dark:text-gray-500 hover:underline disabled:opacity-50`}
              >
                자동 추정으로 되돌리기
              </button>
            )}
            {status.is_manual_override && status.isa_baseline_captured_at && (
              <span className="text-xs text-gray-400 dark:text-gray-500">
                기준일 {fmtMonthDay(status.isa_baseline_captured_at)}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** ISA 계좌의 의무가입(3년) 진행 상황과 비과세 한도 대비 예상 세금을 보여준다. ISA 계좌가 없으면 표시하지 않는다.
 * `TaxLimitsSection`(`TaxTabContainer`의 "한도 현황" 탭)이 렌더하므로 이 컴포넌트는 헤더/보더 없이 본문만 그린다. */
export default function IsaMaturityCard() {
  const { data } = useQuery({
    queryKey: QUERY_KEYS.isaStatus,
    queryFn: fetchIsaStatus,
    staleTime: STALE_TIME.MEDIUM,
  });

  if (!data || data.accounts.length === 0) return null;

  return (
    <div>
      <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase mb-1.5">
        ISA 만기·세제 현황
      </p>
      <div>
        {data.accounts.map((status) => (
          <IsaAccountRow key={status.account_id} status={status} />
        ))}
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">{data.note}</p>
    </div>
  );
}
