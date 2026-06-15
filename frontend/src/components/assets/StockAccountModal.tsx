import { useState } from "react";
import { X, CheckCircle, XCircle, Lock } from "lucide-react";
import type { AssetAccount, AssetAccountCreate } from "@/api/assets";
import { INPUT_SM, TEXTAREA_SM } from "@/constants/inputStyles";
import { verifyKisCredentials } from "@/api/assets";
import { useCurrencyInput } from "@/hooks/useCurrencyInput";
import { useForm } from "@/hooks/useForm";
import { extractErrorMessage } from "@/utils/error";
import { convertUsdToKrw, fmtKrw } from "@/utils/format";
import { STOCK_TYPE_LABELS } from "@/constants";

const STOCK_ASSET_TYPE_OPTIONS: Record<string, string> = {
  STOCK_KIS: "주식 (KIS 한국투자증권)",
  STOCK_KIWOOM: "주식 (키움증권)",
  STOCK_OTHER: "주식 (타증권사 / 수동)",
  CASH_OTHER: "예수금 (기타)",
};

function defaultAssetTypeForSource(source: string): string {
  if (source === "KIS_API") return "STOCK_KIS";
  if (source === "KIWOOM_API") return "STOCK_KIWOOM";
  return "STOCK_OTHER";
}

const INSTITUTION_FOR_SOURCE: Record<string, string> = {
  KIS_API: "한국투자증권",
  KIWOOM_API: "키움증권",
};

interface Props {
  initialAccount?: AssetAccount;
  onClose: () => void;
  onSubmit: (data: AssetAccountCreate) => void;
  isLoading: boolean;
}

export default function StockAccountModal({ initialAccount, onClose, onSubmit, isLoading }: Props) {
  const isEdit = !!initialAccount;

  const { form, set } = useForm<AssetAccountCreate>({
    name: initialAccount?.name ?? "",
    asset_type: initialAccount?.asset_type ?? "STOCK_KIS",
    data_source: initialAccount?.data_source ?? "KIS_API",
    institution: initialAccount?.institution ?? "한국투자증권",
    is_mock_mode: initialAccount?.is_mock_mode ?? true,
    notes: initialAccount?.notes ?? "",
    include_in_total: initialAccount?.include_in_total ?? true,
  });

  const {
    depositKrw, depositUsd, usdRate, usdAsKrw, totalKrw, hasAnyDeposit, usdPending,
    setDepositKrw, setDepositUsd,
  } = useCurrencyInput(
    isEdit ? (initialAccount?.deposit_krw ?? undefined) : undefined,
    isEdit ? (initialAccount?.deposit_usd ?? undefined) : undefined,
  );

  const isKis = form.data_source === "KIS_API";
  const KIS_ACCOUNT_NO_REGEX = /^\d{8}-\d{2}$|^\d{10}$/;
  const kisAccountNoValid = !isKis || isEdit || (!!form.kis_account_no && KIS_ACCOUNT_NO_REGEX.test(form.kis_account_no));
  const kisValid = !isKis || isEdit || (kisAccountNoValid && !!form.kis_app_key && !!form.kis_app_secret);

  const [verifyState, setVerifyState] = useState<"idle" | "loading" | "ok" | "error">("idle");
  const [verifyError, setVerifyError] = useState("");

  const handleVerify = async () => {
    if (!form.kis_app_key || !form.kis_app_secret) return;
    setVerifyState("loading");
    try {
      await verifyKisCredentials({
        kis_app_key: form.kis_app_key,
        kis_app_secret: form.kis_app_secret,
        is_mock: form.is_mock_mode ?? true,
      });
      setVerifyState("ok");
    } catch (e) {
      setVerifyState("error");
      setVerifyError(extractErrorMessage(e, "자격증명 확인 실패"));
    }
  };

  const resetVerify = () => setVerifyState("idle");

  const handleSourceChange = (source: string) => {
    set("data_source", source);
    set("asset_type", defaultAssetTypeForSource(source));
    set("institution", INSTITUTION_FOR_SOURCE[source] ?? "");
    if (source !== "MANUAL") {
      set("manual_amount", undefined);
      setDepositKrw(undefined);
      setDepositUsd(undefined);
    }
  };

  const handleCreateSubmit = () => {
    let submitForm = form;
    if (form.data_source === "MANUAL") {
      const usdConverted = convertUsdToKrw(depositUsd, usdRate);
      const total = (depositKrw ?? 0) + usdConverted;
      submitForm = { ...form, manual_amount: total > 0 ? total : undefined };
    }
    onSubmit(submitForm);
  };

  const handleEditSubmit = () => {
    const data: AssetAccountCreate = {
      name: form.name,
      asset_type: initialAccount!.asset_type,
      institution: form.institution || undefined,
      notes: form.notes || undefined,
      include_in_total: form.include_in_total,
      deposit_krw: depositKrw ?? 0,
      deposit_usd: depositUsd ?? 0,
    };
    if (initialAccount!.data_source === "MANUAL") {
      const usdConverted = convertUsdToKrw(depositUsd, usdRate);
      const total = (depositKrw ?? 0) + usdConverted;
      data.manual_amount = total > 0 ? total : undefined;
    }
    if (form.kis_app_key) data.kis_app_key = form.kis_app_key;
    if (form.kis_app_secret) data.kis_app_secret = form.kis_app_secret;
    if (form.kiwoom_app_key) data.kiwoom_app_key = form.kiwoom_app_key;
    if (form.kiwoom_app_secret) data.kiwoom_app_secret = form.kiwoom_app_secret;
    onSubmit(data);
  };

  const handleSubmit = isEdit ? handleEditSubmit : handleCreateSubmit;

  const createDisabled = isLoading || !form.name || !kisValid || (isKis && !isEdit && verifyState !== "ok") || (form.data_source === "MANUAL" && usdPending);
  const editDisabled = isLoading || !form.name || usdPending;

  const accountNo = initialAccount?.kis_account_no ?? initialAccount?.kiwoom_account_no;
  const typeLabel = STOCK_TYPE_LABELS[initialAccount?.asset_type ?? ""] ?? initialAccount?.asset_type;

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 w-full max-w-md max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-bold text-gray-900 dark:text-gray-50">
            {isEdit ? "증권계좌 수정" : "증권사 계좌 등록"}
          </h2>
          <button onClick={onClose} aria-label="닫기" className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">
          {isEdit ? "계좌 정보를 수정합니다. 계좌번호·유형·데이터 소스는 변경할 수 없습니다." : "주식 계좌를 등록하면 포트폴리오에서 조회할 수 있습니다"}
        </p>

        {isEdit && (
          <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 flex items-center gap-2 flex-wrap">
            <span className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500">
              <Lock size={11} /> 변경 불가
            </span>
            <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-xs rounded-full">{typeLabel}</span>
            {accountNo && <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">{accountNo}</span>}
            <span className={`px-2 py-0.5 text-xs rounded-full ${initialAccount?.is_mock_mode ? "bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400" : "bg-green-50 dark:bg-green-950 text-green-600 dark:text-green-400"}`}>
              {initialAccount?.is_mock_mode ? "모의투자" : "실투자"}
            </span>
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label htmlFor="stock-name" className="text-sm font-medium text-gray-700 dark:text-gray-300">계좌명 *</label>
            <input id="stock-name" className={`mt-1 w-full ${INPUT_SM}`} value={form.name}
              onChange={(e) => set("name", e.target.value)} placeholder="예: KIS 주식계좌" />
          </div>

          {!isEdit && (
            <>
              <div>
                <label htmlFor="stock-data-source" className="text-sm font-medium text-gray-700 dark:text-gray-300">데이터 소스</label>
                <select id="stock-data-source" className={`mt-1 w-full ${INPUT_SM}`} value={form.data_source}
                  onChange={(e) => handleSourceChange(e.target.value)}>
                  <option value="MANUAL">수동 입력</option>
                  <option value="KIS_API">KIS 한국투자증권 (자동)</option>
                  <option value="KIWOOM_API">키움증권 (자동)</option>
                </select>
              </div>
              <div>
                <label htmlFor="stock-asset-type" className="text-sm font-medium text-gray-700 dark:text-gray-300">자산 유형 *</label>
                <select id="stock-asset-type" className={`mt-1 w-full ${INPUT_SM}`} value={form.asset_type}
                  onChange={(e) => set("asset_type", e.target.value)}>
                  {Object.entries(STOCK_ASSET_TYPE_OPTIONS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
            </>
          )}

          <div>
            <label htmlFor="stock-institution" className="text-sm font-medium text-gray-700 dark:text-gray-300">금융기관명</label>
            <input id="stock-institution" className={`mt-1 w-full ${INPUT_SM}`} value={form.institution ?? ""}
              onChange={(e) => set("institution", e.target.value)} placeholder="예: 한국투자증권, 키움증권" />
          </div>

          {/* MANUAL 예수금 */}
          {form.data_source === "MANUAL" && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">예수금</label>
              <div>
                <label htmlFor="stock-deposit-krw" className="text-xs text-gray-500 dark:text-gray-400">원화 예수금</label>
                <div className="relative mt-0.5">
                  <input id="stock-deposit-krw" type="number" inputMode="decimal" className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={depositKrw ?? ""} onChange={(e) => setDepositKrw(e.target.value === "" ? undefined : Number(e.target.value))} placeholder="0" />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">원</span>
                </div>
              </div>
              <div>
                <label htmlFor="stock-deposit-usd" className="text-xs text-gray-500 dark:text-gray-400">외화 예수금 (USD)</label>
                <div className="relative mt-0.5">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">$</span>
                  <input id="stock-deposit-usd" type="number" inputMode="decimal" className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg pl-6 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={depositUsd ?? ""} onChange={(e) => setDepositUsd(e.target.value === "" ? undefined : Number(e.target.value))} placeholder="0" />
                </div>
                {(depositUsd ?? 0) > 0 && (
                  <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                    {usdRate == null
                      ? "환율 정보를 불러오는 중..."
                      : `≈ ${fmtKrw(usdAsKrw)} (환율 ${usdRate.toLocaleString()}원/USD)`}
                  </p>
                )}
              </div>
              {hasAnyDeposit && (
                <div className="flex justify-between items-center pt-1 border-t border-gray-100 dark:border-gray-700">
                  <span className="text-xs text-gray-500 dark:text-gray-400">합계</span>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-50">{fmtKrw(totalKrw)}</span>
                </div>
              )}
            </div>
          )}

          {/* 편집 모드: KIS/키움 예수금 수동 보정 */}
          {isEdit && form.data_source !== "MANUAL" && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">예수금 (수동 보정)</label>
              <div className="relative">
                <input type="number" inputMode="decimal" className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={depositKrw ?? ""} onChange={(e) => setDepositKrw(e.target.value === "" ? undefined : Number(e.target.value))} placeholder="원화 예수금" />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">원</span>
              </div>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">$</span>
                <input type="number" inputMode="decimal" step="0.01" className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg pl-6 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={depositUsd ?? ""} onChange={(e) => setDepositUsd(e.target.value === "" ? undefined : Number(e.target.value))} placeholder="외화 예수금 (USD)" />
              </div>
              {(depositUsd ?? 0) > 0 && usdRate != null && (
                <p className="text-xs text-gray-400 dark:text-gray-500">≈ {fmtKrw(usdAsKrw)} (환율 {usdRate.toLocaleString()}원/USD)</p>
              )}
            </div>
          )}

          {/* KIS 자격증명 */}
          {form.data_source === "KIS_API" && (
            <>
              {!isEdit && (
                <div>
                  <label htmlFor="stock-kis-account-no" className="text-sm font-medium text-gray-700 dark:text-gray-300">KIS 계좌번호 *</label>
                  <input id="stock-kis-account-no" className={`mt-1 w-full ${INPUT_SM}`} value={form.kis_account_no ?? ""}
                    onChange={(e) => set("kis_account_no", e.target.value)} placeholder="12345678-01" />
                  {isKis && form.kis_account_no && !kisAccountNoValid && (
                    <p className="mt-1 text-xs text-red-500">형식 오류: 12345678-01 형식으로 입력하세요</p>
                  )}
                </div>
              )}
              <div>
                <label htmlFor="stock-kis-app-key" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  KIS App Key{!isEdit && " *"}
                </label>
                {isEdit && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 mb-1">비워두면 기존 키를 유지합니다</p>}
                <input
                  id="stock-kis-app-key"
                  type="password"
                  className={`mt-1 w-full ${INPUT_SM}`}
                  value={form.kis_app_key ?? ""}
                  onChange={(e) => { set("kis_app_key", e.target.value); resetVerify(); }}
                  placeholder={isEdit ? "기존 키 유지" : "KIS 앱 키"}
                />
              </div>
              <div>
                <label htmlFor="stock-kis-app-secret" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  KIS App Secret{!isEdit && " *"}
                </label>
                <input
                  id="stock-kis-app-secret"
                  type="password"
                  className={`mt-1 w-full ${INPUT_SM}`}
                  value={form.kis_app_secret ?? ""}
                  onChange={(e) => { set("kis_app_secret", e.target.value); resetVerify(); }}
                  placeholder={isEdit ? "기존 시크릿 유지" : "KIS 앱 시크릿"}
                />
              </div>
              {(!isEdit || form.kis_app_key || form.kis_app_secret) && (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleVerify}
                    disabled={verifyState === "loading" || !form.kis_app_key || !form.kis_app_secret}
                    className="px-3 py-1.5 text-xs border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
                  >
                    {verifyState === "loading" ? "확인 중..." : "자격증명 확인"}
                  </button>
                  {verifyState === "ok" && (
                    <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                      <CheckCircle size={14} /> 자격증명 확인됨
                    </span>
                  )}
                  {verifyState === "error" && (
                    <span className="flex items-center gap-1 text-xs text-red-500">
                      <XCircle size={14} /> {verifyError}
                    </span>
                  )}
                </div>
              )}
            </>
          )}

          {/* 키움 자격증명 */}
          {form.data_source === "KIWOOM_API" && (
            <>
              {!isEdit && (
                <div>
                  <label htmlFor="stock-kiwoom-account-no" className="text-sm font-medium text-gray-700 dark:text-gray-300">키움 계좌번호 *</label>
                  <input id="stock-kiwoom-account-no" className={`mt-1 w-full ${INPUT_SM}`} value={form.kiwoom_account_no ?? ""}
                    onChange={(e) => set("kiwoom_account_no", e.target.value)} placeholder="12345678-01" />
                </div>
              )}
              <div>
                <label htmlFor="stock-kiwoom-app-key" className="text-sm font-medium text-gray-600 dark:text-gray-400">
                  키움 App Key{!isEdit && " *"}
                </label>
                {isEdit && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 mb-1">비워두면 기존 키를 유지합니다</p>}
                <input
                  id="stock-kiwoom-app-key"
                  type="password"
                  className={`mt-1 w-full ${INPUT_SM}`}
                  value={form.kiwoom_app_key ?? ""}
                  onChange={(e) => set("kiwoom_app_key", e.target.value || undefined)}
                  placeholder={isEdit ? "기존 키 유지" : "키움 앱 키"}
                />
              </div>
              <div>
                <label htmlFor="stock-kiwoom-app-secret" className="text-sm font-medium text-gray-600 dark:text-gray-400">
                  키움 App Secret{!isEdit && " *"}
                </label>
                <input
                  id="stock-kiwoom-app-secret"
                  type="password"
                  className={`mt-1 w-full ${INPUT_SM}`}
                  value={form.kiwoom_app_secret ?? ""}
                  onChange={(e) => set("kiwoom_app_secret", e.target.value || undefined)}
                  placeholder={isEdit ? "기존 시크릿 유지" : "키움 앱 시크릿"}
                />
              </div>
            </>
          )}

          {!isEdit && form.data_source !== "MANUAL" && (
            <div className="flex items-center gap-2">
              <input type="checkbox" id="mock-mode" checked={form.is_mock_mode ?? true}
                onChange={(e) => set("is_mock_mode", e.target.checked)} className="w-4 h-4 text-blue-600" />
              <label htmlFor="mock-mode" className="text-sm text-gray-700 dark:text-gray-300">테스트/모의투자 환경 사용</label>
            </div>
          )}

          <div>
            <label htmlFor="stock-notes" className="text-sm font-medium text-gray-700 dark:text-gray-300">메모</label>
            <textarea id="stock-notes"
              value={form.notes ?? ""}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="선택 입력" rows={2}
              className={`mt-1 w-full ${TEXTAREA_SM}`} />
          </div>

          <div className="flex items-center gap-2">
            <input type="checkbox" id="stock-include-in-total"
              checked={form.include_in_total ?? true}
              onChange={(e) => set("include_in_total", e.target.checked)}
              className="w-4 h-4 text-blue-600" />
            <label htmlFor="stock-include-in-total" className="text-sm text-gray-700 dark:text-gray-300">전체 자산 합계에 포함</label>
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">취소</button>
          <button onClick={handleSubmit}
            disabled={isEdit ? editDisabled : createDisabled}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
            {isLoading ? "저장 중..." : isEdit ? "저장" : "등록"}
          </button>
        </div>
      </div>
    </div>
  );
}
