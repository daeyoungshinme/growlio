import { lazy, Suspense, useMemo, useState } from "react";
import ErrorBoundary from "@/components/ErrorBoundary";
import { Plus, Wand2, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ACCOUNT_TAX_TYPE_LABELS,
  AccountTaxType,
  AssetAccount,
  INVESTMENT_HORIZON_LABELS,
  InvestmentHorizon,
} from "@/api/assets";
import { Portfolio, PortfolioItem } from "@/api/portfolios";
import {
  BASE_TYPE_STOCK_ONLY,
  BASE_TYPE_TOTAL_ASSETS,
  CASH_EQUIVALENT_TICKER,
} from "@/constants/assets";
import CollapsibleSection from "@/components/common/CollapsibleSection";
import { INPUT_SM } from "@/constants/inputStyles";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";
import type { PortfolioOverview } from "@/types";
import { useCollapsible } from "@/hooks/useCollapsible";
import { useModalBehavior } from "@/hooks/useModalBehavior";
import { usePortfolioItemsEditor } from "@/hooks/usePortfolioItemsEditor";
import { inferHorizonTaxTypeFromAccounts } from "@/utils/portfolio";
const PortfolioWeightChart = lazy(() => import("./PortfolioWeightChart"));
import PortfolioAccountSelector from "./PortfolioAccountSelector";
import PortfolioItemRow from "./PortfolioItemRow";

interface Props {
  initial?: Portfolio | null;
  /** 신규 생성 모드(`initial`이 없을 때)에서 종목/이름/분석 대상 계좌를 미리 채울 때 사용 (예: 추천 비중 카드에서 생성). */
  initialItems?: PortfolioItem[];
  initialName?: string;
  initialAccountIds?: string[];
  accounts?: AssetAccount[]; // 주식 계좌 목록 (STOCK_KIS, STOCK_OTHER)
  onSave: (
    name: string,
    items: PortfolioItem[],
    baseType: string,
    accountIds: string[] | null,
    investmentHorizon: InvestmentHorizon | null,
    taxType: AccountTaxType | null,
  ) => void;
  onClose: () => void;
  saving?: boolean;
}

export default function UnifiedPortfolioEditor({
  initial,
  initialItems,
  initialName,
  initialAccountIds,
  accounts = [],
  onSave,
  onClose,
  saving,
}: Props) {
  const qc = useQueryClient();
  const [name, setName] = useState(initial?.name ?? initialName ?? "");
  const [baseType, setBaseType] = useState(initial?.base_type ?? BASE_TYPE_STOCK_ONLY);
  // 신규 생성 모드에서 추천 비중 카드가 넘긴 initialAccountIds의 태그가 전부 동일하면 계좌
  // 특성으로부터 투자 기간·세제 유형 초기값을 자동으로 채운다.
  const inferredTags = useMemo(() => {
    if (initial || !initialAccountIds?.length) return null;
    const matched = accounts.filter((a) => initialAccountIds.includes(a.id));
    return inferHorizonTaxTypeFromAccounts(matched);
  }, [initial, initialAccountIds, accounts]);
  const [investmentHorizon, setInvestmentHorizon] = useState<InvestmentHorizon | "">(
    initial?.investment_horizon ?? inferredTags?.horizon ?? "",
  );
  const [taxType, setTaxType] = useState<AccountTaxType | "">(
    initial?.tax_type ?? inferredTags?.taxType ?? "",
  );
  // 수정 모드거나 추천 비중 카드 등에서 계좌를 미리 선택해 넘긴 경우(계좌 태그 매칭이 이미 의미 있는 상황)엔
  // 기본으로 펼쳐두고, 완전히 새로 만드는 포트폴리오는 접어서 초심자 화면을 단순하게 유지한다.
  const [tagSectionOpen, toggleTagSection] = useCollapsible(
    !!(initial || initialAccountIds?.length),
  );
  const { dialogRef, overlayRef } = useModalBehavior(onClose);
  const {
    items,
    totalWeight,
    weightOk,
    suggestions,
    activeRow,
    setActiveRow,
    editingRows,
    addItem,
    updateItem,
    removeItem,
    addCash,
    addRealEstate,
    addCashEquivalent,
    fillFromHoldings,
    handleTickerInput,
    selectSuggestion,
    startEditing,
    registerInputRef,
  } = usePortfolioItemsEditor(initial?.items ?? initialItems ?? []);

  // null = 모든 계좌 (동적), Set = 사용자가 명시적으로 선택한 계좌
  const [userOverrideIds, setUserOverrideIds] = useState<Set<string> | null>(() => {
    if (initial?.account_ids?.length) return new Set(initial.account_ids);
    if (initialAccountIds?.length) return new Set(initialAccountIds);
    return null;
  });

  // accounts가 바뀌어도 userOverrideIds가 null이면 항상 전체 계좌를 반영
  const selectedAccountIds = useMemo(() => {
    if (userOverrideIds === null) return new Set(accounts.map((a) => a.id));
    return userOverrideIds;
  }, [accounts, userOverrideIds]);

  const isAllSelected =
    userOverrideIds === null || accounts.every((a) => selectedAccountIds.has(a.id));

  function toggleAccount(id: string) {
    setUserOverrideIds((prev) => {
      const base = prev === null ? new Set(accounts.map((a) => a.id)) : prev;
      const next = new Set(base);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleSubmit() {
    if (!name.trim() || !weightOk) return;
    const accountIds = isAllSelected ? null : Array.from(selectedAccountIds);
    onSave(name.trim(), items, baseType, accountIds, investmentHorizon || null, taxType || null);
  }

  return (
    <ErrorBoundary variant="section">
      <div
        ref={overlayRef}
        className="fixed inset-0 bg-black/40 flex items-end sm:items-center justify-center z-[60] sm:p-4 pb-16 lg:pb-0"
      >
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby="portfolio-editor-title"
          className="bg-white dark:bg-gray-900 rounded-t-2xl sm:rounded-2xl border border-gray-200 dark:border-gray-700 w-full max-w-2xl max-h-[85dvh] sm:max-h-[90vh] flex flex-col"
        >
          {/* 헤더 */}
          <div className="flex items-center justify-between px-4 py-3 sm:px-6 sm:py-4 border-b border-gray-100 dark:border-gray-700 shrink-0">
            <h2
              id="portfolio-editor-title"
              className="font-semibold text-gray-800 dark:text-gray-50"
            >
              {initial ? "포트폴리오 수정" : "새 포트폴리오 만들기"}
            </h2>
            <button
              onClick={onClose}
              aria-label="닫기"
              className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-50 dark:text-gray-500 dark:hover:text-gray-300 dark:hover:bg-gray-800 rounded-lg transition-colors`}
            >
              <X size={18} />
            </button>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 sm:px-6 space-y-5">
            {/* 이름 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                포트폴리오 이름
              </label>
              <input
                className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 placeholder-gray-400 dark:placeholder-gray-500 rounded-lg px-3 py-2.5 sm:py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="예: 성장형 포트폴리오"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            {/* 기준 자산 (리밸런싱용) */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                리밸런싱 기준 자산
              </label>
              <div className="flex gap-4">
                {[
                  { value: BASE_TYPE_STOCK_ONLY, label: "주식 자산만" },
                  { value: BASE_TYPE_TOTAL_ASSETS, label: "전체 자산" },
                ].map(({ value, label }) => (
                  <label
                    key={value}
                    className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-2 cursor-pointer`}
                  >
                    <input
                      type="radio"
                      name="baseType"
                      value={value}
                      checked={baseType === value}
                      onChange={() => setBaseType(value)}
                      className="accent-blue-600"
                    />
                    <span className="text-sm text-gray-700 dark:text-gray-300">{label}</span>
                  </label>
                ))}
              </div>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                백테스팅에는 영향 없음. 현금·부동산·현금성 자산 항목은 백테스팅에서 자동 제외됩니다.
              </p>
            </div>

            {/* 목표 역산 추천 매칭용 기간/세제유형 태그 */}
            <CollapsibleSection
              label="투자 기간 · 세제 유형 설정(선택, 목표 역산 추천 매칭용)"
              isOpen={tagSectionOpen}
              onToggle={toggleTagSection}
              collapsedHint="지정하면 리밸런싱 탭의 기간별 목표 역산 추천이 이 포트폴리오에 자동 매칭됩니다."
            >
              <div className="grid grid-cols-2 gap-3">
                <select
                  className={INPUT_SM}
                  value={investmentHorizon}
                  onChange={(e) => setInvestmentHorizon(e.target.value as InvestmentHorizon | "")}
                >
                  <option value="">투자 기간 미지정</option>
                  {Object.entries(INVESTMENT_HORIZON_LABELS).map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
                <select
                  className={INPUT_SM}
                  value={taxType}
                  onChange={(e) => setTaxType(e.target.value as AccountTaxType | "")}
                >
                  <option value="">세제 유형 미지정</option>
                  {Object.entries(ACCOUNT_TAX_TYPE_LABELS).map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                지정하면 리밸런싱 탭의 기간별 목표 역산 추천이 이 포트폴리오에 자동 매칭됩니다.
                미지정 시 기준으로 지정된 계좌들의 태그가 전부 동일할 때만 자동 추론합니다.
              </p>
            </CollapsibleSection>

            {/* 종목 목록 */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  종목 및 비중
                </label>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() =>
                      fillFromHoldings(
                        qc.getQueryData<PortfolioOverview>(QUERY_KEYS.portfolioOverview()),
                      )
                    }
                    className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-1 text-xs text-purple-600 dark:text-purple-400 hover:text-purple-700 hover:bg-purple-50 dark:hover:bg-purple-900/20 px-2 py-1 rounded-lg transition-colors`}
                    title="현재 보유 종목을 현재 비중으로 자동 채웁니다"
                  >
                    <Wand2 size={12} /> 현재 보유 종목으로 채우기
                  </button>
                  <span
                    className={`text-xs font-medium ${weightOk ? "text-green-600" : "text-orange-500"}`}
                  >
                    합계 {totalWeight.toFixed(1)}% {weightOk ? "✓" : "(100% 필요)"}
                  </span>
                </div>
              </div>

              <div className="space-y-2">
                {items.map((item, idx) => (
                  <PortfolioItemRow
                    key={idx}
                    item={item}
                    idx={idx}
                    isEditing={editingRows.has(idx)}
                    isActive={activeRow === idx}
                    suggestions={suggestions}
                    onRegisterInputRef={registerInputRef}
                    onTickerInput={handleTickerInput}
                    onFocus={setActiveRow}
                    onSelectSuggestion={selectSuggestion}
                    onStartEditing={startEditing}
                    onUpdateWeight={(i, weight) => updateItem(i, { weight })}
                    onRemove={removeItem}
                  />
                ))}
              </div>

              {/* 비중 도넛차트 */}
              <Suspense fallback={<div className="h-32" />}>
                <PortfolioWeightChart items={items} />
              </Suspense>

              <div className="flex flex-wrap gap-2 mt-3">
                <button
                  onClick={addItem}
                  className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-1 text-sm text-blue-600 hover:text-blue-700 px-2 py-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors`}
                >
                  <Plus size={14} /> 종목 추가
                </button>
                <button
                  onClick={addCash}
                  disabled={items.some((i) => i.ticker === "CASH")}
                  className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-1 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 px-2 py-1.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-40`}
                >
                  <Plus size={14} /> 현금 추가
                </button>
                <button
                  onClick={addRealEstate}
                  disabled={items.some((i) => i.market === "KR_PROPERTY")}
                  className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-1 text-sm text-amber-600 hover:text-amber-700 px-2 py-1.5 rounded-lg hover:bg-amber-50 transition-colors disabled:opacity-40`}
                >
                  <Plus size={14} /> 부동산 추가
                </button>
                <button
                  onClick={addCashEquivalent}
                  disabled={items.some((i) => i.ticker === CASH_EQUIVALENT_TICKER)}
                  className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-1 text-sm text-teal-600 hover:text-teal-700 px-2 py-1.5 rounded-lg hover:bg-teal-50 transition-colors disabled:opacity-40`}
                >
                  <Plus size={14} /> 현금성 자산 추가
                </button>
              </div>
            </div>
            {/* 분석 대상 계좌 — 주식 계좌가 2개 이상일 때만 표시 */}
            {accounts.length > 1 && (
              <PortfolioAccountSelector
                accounts={accounts}
                selectedAccountIds={selectedAccountIds}
                isAllSelected={isAllSelected}
                onToggleAccount={toggleAccount}
                onSelectAll={() => setUserOverrideIds(null)}
              />
            )}
          </div>

          {/* 하단 버튼 */}
          <div className="flex gap-3 px-4 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))] sm:px-6 sm:py-4 border-t border-gray-100 dark:border-gray-700 shrink-0">
            <button
              onClick={onClose}
              className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} flex-1 sm:flex-none px-5 py-2.5 sm:py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
            >
              취소
            </button>
            <button
              onClick={handleSubmit}
              disabled={!name.trim() || !weightOk || saving}
              className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} flex-1 sm:flex-none bg-blue-600 text-white px-5 py-2.5 sm:py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
            >
              {saving ? "저장 중..." : "저장"}
            </button>
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
}
