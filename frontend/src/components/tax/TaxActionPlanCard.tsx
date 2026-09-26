import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ListChecks } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchTaxActionPlan, type TaxAction, type TaxActionPriority } from "@/api/tax";
import { updateIncomeBracket, type IncomeBracket } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import {
  TOUCH_TARGET_COMPACT_MOBILE_ONLY,
  TOUCH_TARGET_MIN_MOBILE_ONLY,
} from "@/constants/uiSizes";
import { invalidateIncomeBracketData } from "@/utils/queryInvalidation";
import { fmtKrw } from "@/utils/format";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";

const COLLAPSED_COUNT = 3;

const PRIORITY_STYLE: Record<TaxActionPriority, { label: string; className: string }> = {
  HIGH: {
    label: "우선",
    className: "bg-red-50 dark:bg-red-950 text-red-600 dark:text-red-400",
  },
  MEDIUM: {
    label: "권장",
    className: "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400",
  },
  LOW: {
    label: "참고",
    className: "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400",
  },
};

const BRACKET_OPTIONS: { value: IncomeBracket; label: string }[] = [
  { value: "UNDER_55M", label: "5,500만원 이하" },
  { value: "OVER_55M", label: "5,500만원 초과" },
];

/** "YYYY-MM-DD" → 로컬 자정 기준 남은 일수 */
function daysUntil(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  const target = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

function deadlineLabel(iso: string): string {
  const [, m, d] = iso.split("-").map(Number);
  const days = daysUntil(iso);
  return days >= 0 ? `${m}/${d}까지 (D-${days})` : `${m}/${d} 마감`;
}

function ActionRow({ action }: { action: TaxAction }) {
  const priority = PRIORITY_STYLE[action.priority];
  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-start gap-2">
        <span className={`shrink-0 px-2 py-0.5 text-xs rounded-full ${priority.className}`}>
          {priority.label}
        </span>
        <p className="flex-1 min-w-0 text-sm font-semibold text-gray-800 dark:text-gray-100">
          {action.title}
        </p>
      </div>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
        {action.detail}
      </p>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {action.benefit_krw != null && action.benefit_krw > 0 && (
          <span className="font-medium text-emerald-600 dark:text-emerald-400 tabular-nums">
            절세 약 {fmtKrw(action.benefit_krw)}
          </span>
        )}
        {action.deadline && (
          <span className="text-gray-500 dark:text-gray-400 tabular-nums">
            {deadlineLabel(action.deadline)}
          </span>
        )}
        <Link
          to={action.cta.link}
          className={`ml-auto gap-1 text-blue-600 dark:text-blue-400 hover:underline ${TOUCH_TARGET_MIN_MOBILE_ONLY}`}
        >
          {action.cta.label} <ArrowRight size={12} />
        </Link>
      </div>
    </li>
  );
}

function IncomeBracketPicker({ value }: { value: IncomeBracket | null }) {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: (next: IncomeBracket) => updateIncomeBracket(next),
    onSuccess: () => invalidateIncomeBracketData(qc),
    onError: (err) => toast(extractErrorMessage(err), "error"),
  });

  return (
    <div className="rounded-lg bg-gray-50 dark:bg-gray-800 p-3">
      <p className="text-xs text-gray-600 dark:text-gray-300">
        총급여가 얼마인가요?{" "}
        <span className="text-gray-400 dark:text-gray-500">
          (연금 세액공제율 16.5%/13.2% 판단용 — 금액은 저장하지 않아요)
        </span>
      </p>
      <div role="group" aria-label="총급여 구간" className="mt-2 flex gap-2">
        {BRACKET_OPTIONS.map((opt) => {
          const selected = value === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={selected}
              disabled={mutation.isPending}
              onClick={() => !selected && mutation.mutate(opt.value)}
              className={`px-3 py-1 text-xs rounded-full border transition-colors disabled:opacity-60 ${TOUCH_TARGET_COMPACT_MOBILE_ONLY} ${
                selected
                  ? "border-blue-500 bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-medium"
                  : "border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300"
              }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** 절세 액션 플랜 — "언제·얼마를·어느 계좌에 하면 얼마 아낀다"를 우선순위 순으로 보여준다.
 * 백엔드 `GET /tax/action-plan`(tax_action_service)이 연금 세액공제·ISA 이전/납입·해외 이익실현/손실수확·
 * 금융소득 한도 액션을 조합하며, 연말 절세 리마인더 이메일/푸시도 같은 목록을 쓴다. `TaxLimitsSection`
 * ("한도 현황" 탭) 최상단에 렌더되고, 아래 기존 카드(`IsaMaturityCard` 등)가 상세를 맡는다.
 * 소득 구간은 별도 설정 화면 없이 연금 관련 액션이 있을 때만 여기서 인라인으로 입력받는다. */
export default function TaxActionPlanCard() {
  const [expanded, setExpanded] = useState(false);
  const { data } = useQuery({
    queryKey: QUERY_KEYS.taxActionPlan,
    queryFn: fetchTaxActionPlan,
    staleTime: STALE_TIME.MEDIUM,
  });

  if (!data) return null;

  const { actions } = data;
  const visible = expanded ? actions : actions.slice(0, COLLAPSED_COUNT);
  const hiddenCount = actions.length - visible.length;
  const needsBracket = actions.some((a) => a.uses_income_bracket);

  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <ListChecks size={13} className="text-blue-500 shrink-0" />
        <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase">
          절세 액션 플랜 ({data.year}년)
        </p>
      </div>

      {actions.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          지금 챙길 절세 액션이 없어요. 연금·ISA 계좌를 등록하면 공제 한도 활용 방법을 알려드려요.
        </p>
      ) : (
        <>
          <ul className="divide-y divide-gray-100 dark:divide-gray-700">
            {visible.map((action) => (
              <ActionRow key={action.id} action={action} />
            ))}
          </ul>
          {actions.length > COLLAPSED_COUNT && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className={`w-full mt-1 text-xs text-blue-600 dark:text-blue-400 ${TOUCH_TARGET_MIN_MOBILE_ONLY}`}
            >
              {expanded ? "접기" : `${hiddenCount}개 더 보기`}
            </button>
          )}
        </>
      )}

      {needsBracket && (
        <div className="mt-3">
          <IncomeBracketPicker value={data.income_bracket} />
        </div>
      )}
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">{data.note}</p>
    </div>
  );
}
