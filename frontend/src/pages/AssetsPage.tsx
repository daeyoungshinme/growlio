import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart2, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { AssetAccountCreate, createAccount, deleteAccount, fetchAccounts, syncAccount } from "../api/assets";
import StockPositionsModal from "../components/assets/StockPositionsModal";
import { fmtKrwNullable } from "../utils/format";

const ASSET_TYPE_LABELS: Record<string, string> = {
  BANK_ACCOUNT: "통장잔고",
  DEPOSIT: "예금/적금",
  STOCK_KIS: "주식 (KIS)",
  STOCK_LS: "주식 (LS증권)",
  STOCK_OTHER: "주식 (타증권사)",
  CASH_OTHER: "예수금 (기타)",
  OTHER: "기타",
  REAL_ESTATE: "부동산",
};

const DATA_SOURCE_LABELS: Record<string, string> = {
  MANUAL: "수동",
  KIS_API: "KIS 자동",
  LS_SEC: "LS증권 자동",
  OPEN_BANKING: "오픈뱅킹",
};

const DATA_SOURCE_BADGE: Record<string, string> = {
  KIS_API: "bg-blue-50 text-blue-600",
  LS_SEC: "bg-purple-50 text-purple-600",
  OPEN_BANKING: "bg-green-50 text-green-700",
  MANUAL: "bg-gray-100 text-gray-500",
};


export default function AssetsPage() {
  const qc = useQueryClient();
  const { data: accounts = [], isLoading } = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });
  const [showForm, setShowForm] = useState(false);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [positionsAccount, setPositionsAccount] = useState<{ id: string; name: string } | null>(null);

  const createMut = useMutation({
    mutationFn: createAccount,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["accounts"] }); setShowForm(false); },
  });
  const deleteMut = useMutation({
    mutationFn: deleteAccount,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  });

  const handleSync = async (id: string) => {
    setSyncingId(id);
    setSyncError(null);
    try {
      await syncAccount(id);
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["accounts"] });
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "동기화에 실패했습니다";
      setSyncError(msg);
    } finally {
      setSyncingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">자산 계좌 관리</h1>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          <Plus size={16} />
          계좌 추가
        </button>
      </div>

      {syncError && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
          {syncError}
        </div>
      )}

      {isLoading ? (
        <div className="text-gray-400">로딩 중...</div>
      ) : accounts.length === 0 ? (
        <div className="bg-gray-50 rounded-2xl border border-dashed border-gray-300 p-10 text-center text-gray-400 text-sm">
          등록된 계좌가 없습니다. 계좌 추가를 눌러 시작하세요.
        </div>
      ) : (
        <div className="space-y-3">
          {accounts.map((acc) => (
            <div key={acc.id} className="bg-white rounded-2xl border border-gray-200 p-4 flex items-center justify-between">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-gray-900">{acc.name}</span>
                  <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                    {ASSET_TYPE_LABELS[acc.asset_type] ?? acc.asset_type}
                  </span>
                  {acc.data_source !== "MANUAL" && (
                    <span className={`text-xs px-2 py-0.5 rounded-full ${DATA_SOURCE_BADGE[acc.data_source] ?? "bg-gray-100 text-gray-500"}`}>
                      {DATA_SOURCE_LABELS[acc.data_source] ?? acc.data_source}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-400 mt-0.5 truncate">
                  {acc.institution && <span>{acc.institution}</span>}
                  {acc.kis_account_no && <span className="ml-1 text-blue-400">({acc.kis_account_no})</span>}
                  {acc.ls_account_no && <span className="ml-1 text-purple-400">({acc.ls_account_no})</span>}
                </p>
              </div>
              <div className="text-right mr-4 shrink-0">
                <p className="font-semibold text-gray-900">{fmtKrwNullable(acc.manual_amount)}</p>
                {acc.manual_updated_at && (
                  <p className="text-xs text-gray-400">{new Date(acc.manual_updated_at).toLocaleDateString("ko-KR")}</p>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {acc.asset_type.startsWith("STOCK") && (
                  <button
                    onClick={() => setPositionsAccount({ id: acc.id, name: acc.name })}
                    className="p-2 text-gray-400 hover:text-purple-600 hover:bg-purple-50 rounded-lg transition-colors"
                    title="종목 관리"
                  >
                    <BarChart2 size={16} />
                  </button>
                )}
                <button
                  onClick={() => handleSync(acc.id)}
                  disabled={syncingId === acc.id}
                  className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors disabled:opacity-40"
                  title="동기화"
                >
                  <RefreshCw size={16} className={syncingId === acc.id ? "animate-spin" : ""} />
                </button>
                <button
                  onClick={() => deleteMut.mutate(acc.id)}
                  className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  title="삭제"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <AddAccountModal
          onSubmit={(data) => createMut.mutate(data)}
          onClose={() => setShowForm(false)}
          loading={createMut.isPending}
        />
      )}

      {positionsAccount && (
        <StockPositionsModal
          accountId={positionsAccount.id}
          accountName={positionsAccount.name}
          onClose={() => { setPositionsAccount(null); qc.invalidateQueries({ queryKey: ["accounts"] }); }}
        />
      )}
    </div>
  );
}

function AddAccountModal({ onSubmit, onClose, loading }: {
  onSubmit: (d: AssetAccountCreate) => void;
  onClose: () => void;
  loading: boolean;
}) {
  const [form, setForm] = useState<AssetAccountCreate>({
    name: "",
    asset_type: "BANK_ACCOUNT",
    data_source: "MANUAL",
    institution: "",
    manual_amount: 0,
  });

  const set = (k: keyof AssetAccountCreate, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const isAutoSource = form.data_source !== "MANUAL";

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-lg p-6 w-full max-w-md max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-bold mb-4">계좌 추가</h2>
        <div className="space-y-3">
          <div>
            <label className="text-sm font-medium text-gray-700">계좌명 *</label>
            <input
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="예: 국민은행 주계좌"
            />
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700">데이터 소스</label>
            <select
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              value={form.data_source}
              onChange={(e) => set("data_source", e.target.value)}
            >
              <option value="MANUAL">수동 입력</option>
              <option value="KIS_API">KIS 한국투자증권 (자동)</option>
              <option value="LS_SEC">LS증권 (자동)</option>
              <option value="OPEN_BANKING">오픈뱅킹 은행 (자동)</option>
            </select>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700">자산 유형 *</label>
            <select
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              value={form.asset_type}
              onChange={(e) => set("asset_type", e.target.value)}
            >
              {Object.entries(ASSET_TYPE_LABELS).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700">금융기관명</label>
            <input
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              value={form.institution ?? ""}
              onChange={(e) => set("institution", e.target.value)}
              placeholder="예: 국민은행, LS증권"
            />
          </div>

          {/* 수동 입력 금액 */}
          {form.data_source === "MANUAL" && (
            <div>
              <label className="text-sm font-medium text-gray-700">현재 금액 (원)</label>
              <input
                type="number"
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                value={form.manual_amount ?? 0}
                onChange={(e) => set("manual_amount", Number(e.target.value))}
              />
            </div>
          )}

          {/* KIS 계좌번호 */}
          {form.data_source === "KIS_API" && (
            <div>
              <label className="text-sm font-medium text-gray-700">KIS 계좌번호</label>
              <input
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                value={form.kis_account_no ?? ""}
                onChange={(e) => set("kis_account_no", e.target.value)}
                placeholder="12345678-01"
              />
              <p className="text-xs text-gray-400 mt-1">설정 페이지에서 KIS App Key/Secret을 먼저 등록해야 합니다.</p>
            </div>
          )}

          {/* LS증권 계좌번호 */}
          {form.data_source === "LS_SEC" && (
            <div>
              <label className="text-sm font-medium text-gray-700">LS증권 계좌번호</label>
              <input
                className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
                value={form.ls_account_no ?? ""}
                onChange={(e) => set("ls_account_no", e.target.value)}
                placeholder="12345678-10"
              />
              <p className="text-xs text-gray-400 mt-1">설정 페이지에서 LS증권 App Key/Secret을 먼저 등록해야 합니다.</p>
            </div>
          )}

          {/* 오픈뱅킹 안내 */}
          {form.data_source === "OPEN_BANKING" && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-700">
              설정 페이지에서 오픈뱅킹을 먼저 연결한 후, 연결된 계좌의 핀테크이용번호를 입력하세요.
            </div>
          )}

          {isAutoSource && (
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="mock-mode"
                checked={form.is_mock_mode ?? true}
                onChange={(e) => set("is_mock_mode", e.target.checked)}
                className="w-4 h-4 text-blue-600"
              />
              <label htmlFor="mock-mode" className="text-sm text-gray-700">테스트/모의투자 환경 사용</label>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg hover:bg-gray-50">취소</button>
          <button
            onClick={() => onSubmit(form)}
            disabled={loading || !form.name}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
