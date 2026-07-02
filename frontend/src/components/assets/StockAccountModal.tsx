import { Lock } from "lucide-react";
import ErrorBoundary from "@/components/ErrorBoundary";
import Modal from "@/components/common/Modal";
import type { AssetAccount, AssetAccountCreate } from "@/api/assets";
import { INPUT_SM, TEXTAREA_SM } from "@/constants/inputStyles";
import { useCurrencyInput } from "@/hooks/useCurrencyInput";
import { useForm } from "@/hooks/useForm";
import { useKisCredentialVerify } from "@/hooks/useKisCredentialVerify";
import { convertUsdToKrw } from "@/utils/format";
import { STOCK_TYPE_LABELS } from "@/constants";
import StockDepositFields from "./StockDepositFields";
import KisCredentialFields from "./KisCredentialFields";
import KiwoomCredentialFields from "./KiwoomCredentialFields";

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
    depositKrw,
    depositUsd,
    usdRate,
    usdAsKrw,
    totalKrw,
    hasAnyDeposit,
    usdPending,
    setDepositKrw,
    setDepositUsd,
  } = useCurrencyInput(
    isEdit ? (initialAccount?.deposit_krw ?? undefined) : undefined,
    isEdit ? (initialAccount?.deposit_usd ?? undefined) : undefined,
  );

  const isKis = form.data_source === "KIS_API";
  const KIS_ACCOUNT_NO_REGEX = /^\d{8}-\d{2}$|^\d{10}$/;
  const kisAccountNoValid =
    !isKis || isEdit || (!!form.kis_account_no && KIS_ACCOUNT_NO_REGEX.test(form.kis_account_no));
  const kisValid =
    !isKis || isEdit || (kisAccountNoValid && !!form.kis_app_key && !!form.kis_app_secret);

  const { verifyState, verifyError, verify, reset: resetVerify } = useKisCredentialVerify();

  const handleVerify = async () => {
    if (!form.kis_app_key || !form.kis_app_secret) return;
    await verify(form.kis_app_key, form.kis_app_secret, form.is_mock_mode ?? true);
  };

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

  const createDisabled =
    isLoading ||
    !form.name ||
    !kisValid ||
    (isKis && !isEdit && verifyState !== "ok") ||
    (form.data_source === "MANUAL" && usdPending);
  const editDisabled = isLoading || !form.name || usdPending;

  const accountNo = initialAccount?.kis_account_no ?? initialAccount?.kiwoom_account_no;
  const typeLabel =
    STOCK_TYPE_LABELS[initialAccount?.asset_type ?? ""] ?? initialAccount?.asset_type;

  return (
    <ErrorBoundary variant="section">
      <Modal
        onClose={onClose}
        title={isEdit ? "증권계좌 수정" : "증권사 계좌 등록"}
        size="md"
        closeOnBackdrop
      >
        <div className="overflow-y-auto flex-1 px-6 py-4">
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">
            {isEdit
              ? "계좌 정보를 수정합니다. 계좌번호·유형·데이터 소스는 변경할 수 없습니다."
              : "주식 계좌를 등록하면 포트폴리오에서 조회할 수 있습니다"}
          </p>

          {isEdit && (
            <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 flex items-center gap-2 flex-wrap">
              <span className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500">
                <Lock size={11} /> 변경 불가
              </span>
              <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-xs rounded-full">
                {typeLabel}
              </span>
              {accountNo && (
                <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                  {accountNo}
                </span>
              )}
              <span
                className={`px-2 py-0.5 text-xs rounded-full ${initialAccount?.is_mock_mode ? "bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400" : "bg-green-50 dark:bg-green-950 text-green-600 dark:text-green-400"}`}
              >
                {initialAccount?.is_mock_mode ? "모의투자" : "실투자"}
              </span>
            </div>
          )}

          <div className="space-y-3">
            <div>
              <label
                htmlFor="stock-name"
                className="text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                계좌명 *
              </label>
              <input
                id="stock-name"
                className={`mt-1 w-full ${INPUT_SM}`}
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="예: KIS 주식계좌"
              />
            </div>

            {!isEdit && (
              <>
                <div>
                  <label
                    htmlFor="stock-data-source"
                    className="text-sm font-medium text-gray-700 dark:text-gray-300"
                  >
                    데이터 소스
                  </label>
                  <select
                    id="stock-data-source"
                    className={`mt-1 w-full ${INPUT_SM}`}
                    value={form.data_source}
                    onChange={(e) => handleSourceChange(e.target.value)}
                  >
                    <option value="MANUAL">수동 입력</option>
                    <option value="KIS_API">KIS 한국투자증권 (자동)</option>
                    <option value="KIWOOM_API">키움증권 (자동)</option>
                  </select>
                </div>
                <div>
                  <label
                    htmlFor="stock-asset-type"
                    className="text-sm font-medium text-gray-700 dark:text-gray-300"
                  >
                    자산 유형 *
                  </label>
                  <select
                    id="stock-asset-type"
                    className={`mt-1 w-full ${INPUT_SM}`}
                    value={form.asset_type}
                    onChange={(e) => set("asset_type", e.target.value)}
                  >
                    {Object.entries(STOCK_ASSET_TYPE_OPTIONS).map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </div>
              </>
            )}

            <div>
              <label
                htmlFor="stock-institution"
                className="text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                금융기관명
              </label>
              <input
                id="stock-institution"
                className={`mt-1 w-full ${INPUT_SM}`}
                value={form.institution ?? ""}
                onChange={(e) => set("institution", e.target.value)}
                placeholder="예: 한국투자증권, 키움증권"
              />
            </div>

            {/* MANUAL 예수금 */}
            {form.data_source === "MANUAL" && (
              <StockDepositFields
                mode="create"
                depositKrw={depositKrw}
                depositUsd={depositUsd}
                setDepositKrw={setDepositKrw}
                setDepositUsd={setDepositUsd}
                usdRate={usdRate}
                usdAsKrw={usdAsKrw}
                totalKrw={totalKrw}
                hasAnyDeposit={hasAnyDeposit}
              />
            )}

            {/* 편집 모드: KIS/키움 예수금 수동 보정 */}
            {isEdit && form.data_source !== "MANUAL" && (
              <StockDepositFields
                mode="edit"
                depositKrw={depositKrw}
                depositUsd={depositUsd}
                setDepositKrw={setDepositKrw}
                setDepositUsd={setDepositUsd}
                usdRate={usdRate}
                usdAsKrw={usdAsKrw}
                totalKrw={totalKrw}
                hasAnyDeposit={hasAnyDeposit}
              />
            )}

            {/* KIS 자격증명 */}
            {form.data_source === "KIS_API" && (
              <KisCredentialFields
                form={form}
                set={set}
                isEdit={isEdit}
                kisAccountNoValid={kisAccountNoValid}
                verifyState={verifyState}
                verifyError={verifyError}
                onVerify={handleVerify}
                onCredentialChange={resetVerify}
              />
            )}

            {/* 키움 자격증명 */}
            {form.data_source === "KIWOOM_API" && (
              <KiwoomCredentialFields form={form} set={set} isEdit={isEdit} />
            )}

            {!isEdit && form.data_source !== "MANUAL" && (
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="mock-mode"
                  checked={form.is_mock_mode ?? true}
                  onChange={(e) => set("is_mock_mode", e.target.checked)}
                  className="w-4 h-4 text-blue-600"
                />
                <label htmlFor="mock-mode" className="text-sm text-gray-700 dark:text-gray-300">
                  테스트/모의투자 환경 사용
                </label>
              </div>
            )}

            <div>
              <label
                htmlFor="stock-notes"
                className="text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                메모
              </label>
              <textarea
                id="stock-notes"
                value={form.notes ?? ""}
                onChange={(e) => set("notes", e.target.value)}
                placeholder="선택 입력"
                rows={2}
                className={`mt-1 w-full ${TEXTAREA_SM}`}
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="stock-include-in-total"
                checked={form.include_in_total ?? true}
                onChange={(e) => set("include_in_total", e.target.checked)}
                className="w-4 h-4 text-blue-600"
              />
              <label
                htmlFor="stock-include-in-total"
                className="text-sm text-gray-700 dark:text-gray-300"
              >
                전체 자산 합계에 포함
              </label>
            </div>
          </div>

        </div>
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 dark:border-gray-700 shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            disabled={isEdit ? editDisabled : createDisabled}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {isLoading ? "저장 중..." : isEdit ? "저장" : "등록"}
          </button>
        </div>
      </Modal>
    </ErrorBoundary>
  );
}
