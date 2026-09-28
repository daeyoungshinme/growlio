import { Info } from "lucide-react";
import type { AssetAccountCreate } from "@/api/assets";
import { ACCOUNT_TAX_TYPE_LABELS, INVESTMENT_HORIZON_LABELS, ISA_TYPE_LABELS } from "@/api/assets";
import { INPUT_SM } from "@/constants/inputStyles";
import CollapsibleSection from "@/components/common/CollapsibleSection";
import Tooltip from "@/components/common/Tooltip";
import type { useForm } from "@/hooks/useForm";

const LABEL_CLASS = "text-sm font-medium text-gray-700 dark:text-gray-300";

interface Props {
  form: AssetAccountCreate;
  set: ReturnType<typeof useForm<AssetAccountCreate>>["set"];
  isOpen: boolean;
  onToggle: () => void;
}

/** 증권계좌 모달의 "세제·투자기간 설정" 섹션 — 세제 유형·투자 기간(기간별 추천 매칭 키)과,
 * ISA일 때만 가입일·유형을 받는다. */
export default function StockAccountTaxFields({ form, set, isOpen, onToggle }: Props) {
  return (
    <CollapsibleSection
      label="세제·투자기간 설정(선택)"
      isOpen={isOpen}
      onToggle={onToggle}
      collapsedHint="목표 역산 추천 매칭에 사용됩니다. 나중에 계좌 수정에서도 설정할 수 있어요."
    >
      <div className="space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="stock-tax-type" className={LABEL_CLASS}>
              세제 유형
            </label>
            <select
              id="stock-tax-type"
              className={`mt-1 w-full ${INPUT_SM}`}
              value={form.tax_type ?? "GENERAL"}
              onChange={(e) => set("tax_type", e.target.value as AssetAccountCreate["tax_type"])}
            >
              {Object.entries(ACCOUNT_TAX_TYPE_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="stock-horizon" className={`flex items-center gap-1 ${LABEL_CLASS}`}>
              투자 기간
              <Tooltip content="세제 유형과 함께 리밸런싱 탭의 기간별 목표 역산 추천이 어느 포트폴리오에 적용될지 매칭하는 데 사용됩니다.">
                <Info size={12} className="text-gray-400 cursor-help" />
              </Tooltip>
            </label>
            <select
              id="stock-horizon"
              className={`mt-1 w-full ${INPUT_SM}`}
              value={form.investment_horizon ?? ""}
              onChange={(e) =>
                set(
                  "investment_horizon",
                  (e.target.value || undefined) as AssetAccountCreate["investment_horizon"],
                )
              }
            >
              <option value="">미지정</option>
              {Object.entries(INVESTMENT_HORIZON_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </div>
        </div>

        {form.tax_type === "ISA" && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="stock-isa-open-date" className={LABEL_CLASS}>
                ISA 가입일
              </label>
              <input
                id="stock-isa-open-date"
                type="date"
                className={`mt-1 w-full ${INPUT_SM}`}
                value={form.isa_open_date ?? ""}
                onChange={(e) => set("isa_open_date", e.target.value || undefined)}
              />
            </div>
            <div>
              <label htmlFor="stock-isa-type" className={LABEL_CLASS}>
                ISA 유형
              </label>
              <select
                id="stock-isa-type"
                className={`mt-1 w-full ${INPUT_SM}`}
                value={form.isa_type ?? "GENERAL"}
                onChange={(e) => set("isa_type", e.target.value as AssetAccountCreate["isa_type"])}
              >
                {Object.entries(ISA_TYPE_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
