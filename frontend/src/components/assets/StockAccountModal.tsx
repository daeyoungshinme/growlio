import { useState } from "react";
import { ChevronDown, ChevronUp, X } from "lucide-react";
import type { AssetAccountCreate } from "../../api/assets";

const STOCK_ASSET_TYPE_OPTIONS: Record<string, string> = {
  STOCK_KIS: "주식 (KIS 한국투자증권)",
  STOCK_LS: "주식 (LS증권)",
  STOCK_OTHER: "주식 (타증권사 / 수동)",
  CASH_OTHER: "예수금 (기타)",
};

function defaultAssetTypeForSource(source: string): string {
  if (source === "KIS_API") return "STOCK_KIS";
  if (source === "LS_SEC") return "STOCK_LS";
  return "STOCK_OTHER";
}

interface Props {
  onClose: () => void;
  onSubmit: (data: AssetAccountCreate) => void;
  isLoading: boolean;
}

export default function StockAccountModal({ onClose, onSubmit, isLoading }: Props) {
  const [form, setForm] = useState<AssetAccountCreate>({
    name: "",
    asset_type: "STOCK_KIS",
    data_source: "KIS_API",
    institution: "",
  });
  const [showOwnCredentials, setShowOwnCredentials] = useState(false);
  const set = (k: keyof AssetAccountCreate, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const handleSourceChange = (source: string) => {
    set("data_source", source);
    set("asset_type", defaultAssetTypeForSource(source));
    if (source !== "MANUAL") {
      set("manual_amount", undefined);
    }
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
              <option value="LS_SEC">LS증권 (자동)</option>
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
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">현재 금액 (원)</label>
              <input type="number" className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.manual_amount ?? 0} onChange={(e) => set("manual_amount", Number(e.target.value))} />
            </div>
          )}
          {form.data_source === "KIS_API" && (
            <>
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">KIS 계좌번호</label>
                <input className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.kis_account_no ?? ""}
                  onChange={(e) => set("kis_account_no", e.target.value)} placeholder="12345678-01" />
              </div>
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                <button
                  type="button"
                  onClick={() => setShowOwnCredentials((v) => !v)}
                  className="w-full flex items-center justify-between px-3 py-2.5 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                >
                  <span className="font-medium">계좌별 API 키 설정 <span className="text-gray-400 dark:text-gray-500 font-normal">(선택사항)</span></span>
                  {showOwnCredentials ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                </button>
                {showOwnCredentials && (
                  <div className="px-3 pb-3 space-y-2 border-t border-gray-200 dark:border-gray-700">
                    <p className="text-xs text-gray-400 dark:text-gray-500 pt-2">미입력 시 설정 페이지의 전역 KIS 자격증명을 사용합니다.</p>
                    <div>
                      <label className="text-xs font-medium text-gray-600 dark:text-gray-400">KIS App Key</label>
                      <input
                        className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        value={form.kis_app_key ?? ""}
                        onChange={(e) => set("kis_app_key", e.target.value || undefined)}
                        placeholder="KIS 앱 키"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-gray-600 dark:text-gray-400">KIS App Secret</label>
                      <input
                        type="password"
                        className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        value={form.kis_app_secret ?? ""}
                        onChange={(e) => set("kis_app_secret", e.target.value || undefined)}
                        placeholder="KIS 앱 시크릿"
                      />
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
          {form.data_source === "LS_SEC" && (
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">LS증권 계좌번호</label>
              <input className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.ls_account_no ?? ""}
                onChange={(e) => set("ls_account_no", e.target.value)} placeholder="12345678-10" />
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">설정 페이지에서 LS증권 App Key/Secret을 먼저 등록하세요.</p>
            </div>
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
          <button onClick={() => onSubmit(form)} disabled={isLoading || !form.name}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
            {isLoading ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
