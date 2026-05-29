import { useState } from "react";
import { X, CheckCircle, XCircle } from "lucide-react";
import type { AssetAccountCreate } from "../../api/assets";
import { verifyKisCredentials } from "../../api/assets";
import { useExchangeRate } from "../../hooks/useExchangeRate";
import { extractErrorMessage } from "../../utils/error";
import { fmtKrw } from "../../utils/format";

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

interface Props {
  onClose: () => void;
  onSubmit: (data: AssetAccountCreate) => void;
  isLoading: boolean;
}

export default function StockAccountModal({ onClose, onSubmit, isLoading }: Props) {
  const usdRate = useExchangeRate();
  const [form, setForm] = useState<AssetAccountCreate>({
    name: "",
    asset_type: "STOCK_KIS",
    data_source: "KIS_API",
    institution: "",
    is_mock_mode: true,
  });
  const set = (k: keyof AssetAccountCreate, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const [depositKrw, setDepositKrw] = useState<number | undefined>(undefined);
  const [depositUsd, setDepositUsd] = useState<number | undefined>(undefined);

  const usdAsKrw = depositUsd != null && usdRate != null ? Math.round(depositUsd * usdRate) : 0;
  const totalKrw = (depositKrw ?? 0) + usdAsKrw;
  const hasAnyDeposit = (depositKrw ?? 0) > 0 || (depositUsd ?? 0) > 0;

  const isKis = form.data_source === "KIS_API";
  const KIS_ACCOUNT_NO_REGEX = /^\d{8}-\d{2}$|^\d{10}$/;
  const kisAccountNoValid = !isKis || (!!form.kis_account_no && KIS_ACCOUNT_NO_REGEX.test(form.kis_account_no));
  const kisValid = !isKis || (kisAccountNoValid && !!form.kis_app_key && !!form.kis_app_secret);

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
    if (source !== "MANUAL") {
      set("manual_amount", undefined);
      setDepositKrw(undefined);
      setDepositUsd(undefined);
    }
  };

  const handleSubmit = () => {
    let submitForm = form;
    if (form.data_source === "MANUAL") {
      const usdConverted = depositUsd != null && usdRate != null ? Math.round(depositUsd * usdRate) : 0;
      const total = (depositKrw ?? 0) + usdConverted;
      submitForm = { ...form, manual_amount: total > 0 ? total : undefined };
    }
    onSubmit(submitForm);
  };

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-bold text-gray-900 dark:text-gray-50">증권사 계좌 등록</h2>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
            <X size={18} />
          </button>
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">주식 계좌를 등록하면 포트폴리오에서 조회할 수 있습니다</p>
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">계좌명 *</label>
            <input className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.name}
              onChange={(e) => set("name", e.target.value)} placeholder="예: KIS 주식계좌" />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">데이터 소스</label>
            <select className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.data_source}
              onChange={(e) => handleSourceChange(e.target.value)}>
              <option value="MANUAL">수동 입력</option>
              <option value="KIS_API">KIS 한국투자증권 (자동)</option>
              <option value="KIWOOM_API">키움증권 (자동)</option>
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">자산 유형 *</label>
            <select className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.asset_type}
              onChange={(e) => set("asset_type", e.target.value)}>
              {Object.entries(STOCK_ASSET_TYPE_OPTIONS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">금융기관명</label>
            <input className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.institution ?? ""}
              onChange={(e) => set("institution", e.target.value)} placeholder="예: 한국투자증권, LS증권" />
          </div>
          {form.data_source === "MANUAL" && (
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">예수금</label>
              <div>
                <label className="text-xs text-gray-500 dark:text-gray-400">원화 예수금</label>
                <div className="relative mt-0.5">
                  <input type="number" className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={depositKrw ?? ""} onChange={(e) => setDepositKrw(e.target.value === "" ? undefined : Number(e.target.value))} placeholder="0" />
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">원</span>
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-500 dark:text-gray-400">외화 예수금 (USD)</label>
                <div className="relative mt-0.5">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">$</span>
                  <input type="number" className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg pl-6 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
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
          {form.data_source === "KIS_API" && (
            <>
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">KIS 계좌번호 *</label>
                <input className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.kis_account_no ?? ""}
                  onChange={(e) => set("kis_account_no", e.target.value)} placeholder="12345678-01" />
                {isKis && form.kis_account_no && !kisAccountNoValid && (
                  <p className="mt-1 text-xs text-red-500">형식 오류: 12345678-01 형식으로 입력하세요</p>
                )}
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">KIS App Key *</label>
                <input
                  type="password"
                  className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={form.kis_app_key ?? ""}
                  onChange={(e) => { set("kis_app_key", e.target.value); resetVerify(); }}
                  placeholder="KIS 앱 키"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">KIS App Secret *</label>
                <input
                  type="password"
                  className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={form.kis_app_secret ?? ""}
                  onChange={(e) => { set("kis_app_secret", e.target.value); resetVerify(); }}
                  placeholder="KIS 앱 시크릿"
                />
              </div>
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
            </>
          )}
          {form.data_source === "KIWOOM_API" && (
            <>
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">키움 계좌번호 *</label>
                <input className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.kiwoom_account_no ?? ""}
                  onChange={(e) => set("kiwoom_account_no", e.target.value)} placeholder="12345678-01" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400">키움 App Key *</label>
                <input
                  type="password"
                  className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={form.kiwoom_app_key ?? ""}
                  onChange={(e) => set("kiwoom_app_key", e.target.value || undefined)}
                  placeholder="키움 앱 키"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400">키움 App Secret *</label>
                <input
                  type="password"
                  className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={form.kiwoom_app_secret ?? ""}
                  onChange={(e) => set("kiwoom_app_secret", e.target.value || undefined)}
                  placeholder="키움 앱 시크릿"
                />
              </div>
            </>
          )}
          {form.data_source !== "MANUAL" && (
            <div className="flex items-center gap-2">
              <input type="checkbox" id="mock-mode" checked={form.is_mock_mode ?? true}
                onChange={(e) => set("is_mock_mode", e.target.checked)} className="w-4 h-4 text-blue-600" />
              <label htmlFor="mock-mode" className="text-sm text-gray-700 dark:text-gray-300">테스트/모의투자 환경 사용</label>
            </div>
          )}
        </div>
        <div className="flex justify-end gap-3 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">취소</button>
          <button onClick={handleSubmit}
            disabled={isLoading || !form.name || !kisValid || (isKis && verifyState !== "ok") || (form.data_source === "MANUAL" && (depositUsd ?? 0) > 0 && usdRate == null)}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
            {isLoading ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
