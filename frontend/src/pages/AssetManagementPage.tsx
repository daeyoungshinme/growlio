import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Plus, Trash2, X, Building2, TrendingUp, Receipt, ChevronUp, BarChart2, Pencil, RefreshCw, Home, Loader2 } from "lucide-react";
import {
  fetchAccounts,
  createAccount,
  updateAccount,
  deleteAccount,
  syncAccount,
  fetchExchangeRate,
  searchStocks,
  StockSuggestion,
  AssetAccount,
  AssetAccountCreate,
  RealEstateDetails,
} from "../api/assets";
import {
  fetchTransactions,
  createTransaction,
  updateTransaction,
  deleteTransaction,
  Transaction,
  TransactionCreate,
} from "../api/transactions";
import StockPositionsModal from "../components/assets/StockPositionsModal";
import TransactionModal from "../components/transactions/TransactionModal";
import { fmtKrw } from "../utils/format";
import { toast } from "../utils/toast";

const TABS = ["은행계좌", "증권계좌", "부동산", "입출금·배당"] as const;
type Tab = typeof TABS[number];

const BANK_TYPES = ["BANK_ACCOUNT", "DEPOSIT", "CASH_OTHER"];
const STOCK_TYPES = ["STOCK_KIS", "STOCK_LS", "STOCK_OTHER"];
const REAL_ESTATE_TYPES = ["REAL_ESTATE"];

const PROPERTY_TYPE_OPTIONS = ["아파트", "오피스텔", "상가", "토지", "단독주택", "기타"];


interface StockOverview {
  total_stock_krw: number;
  total_invested_krw: number;
  unrealized_pnl_krw: number;
  stock_return_pct: number;
  accounts: { id: string; amount_krw: number; invested_krw: number; unrealized_pnl: number }[];
}

interface AccountStats {
  amount_krw: number;
  invested_krw: number;
  unrealized_pnl: number;
  deposit_total: number;
  dividend_total: number;
}

const fetchStockOverview = () =>
  api.get<StockOverview>("/portfolio/overview").then((r) => r.data);

const BANK_TYPE_LABELS: Record<string, string> = {
  BANK_ACCOUNT: "입출금",
  DEPOSIT: "예·적금",
  CASH_OTHER: "현금/기타",
};

const STOCK_TYPE_LABELS: Record<string, string> = {
  STOCK_KIS: "주식 (KIS)",
  STOCK_LS: "주식 (LS증권)",
  STOCK_OTHER: "주식 (타증권사)",
  CASH_OTHER: "예수금 (기타)",
};

const STOCK_ASSET_TYPE_OPTIONS: Record<string, string> = {
  STOCK_KIS: "주식 (KIS 한국투자증권)",
  STOCK_LS: "주식 (LS증권)",
  STOCK_OTHER: "주식 (타증권사 / 수동)",
  CASH_OTHER: "예수금 (기타)",
};

const TX_LABELS: Record<string, string> = {
  DEPOSIT: "입금",
  WITHDRAWAL: "출금",
  DIVIDEND: "배당",
};

const TX_COLORS: Record<string, string> = {
  DEPOSIT: "text-blue-600",
  WITHDRAWAL: "text-red-500",
  DIVIDEND: "text-green-600",
};

function defaultAssetTypeForSource(source: string): string {
  if (source === "KIS_API") return "STOCK_KIS";
  if (source === "LS_SEC") return "STOCK_LS";
  return "STOCK_OTHER";
}

// ─── Bank Account Modal ──────────────────────────────────────────────────────

interface BankModalProps {
  onClose: () => void;
  onSubmit: (data: AssetAccountCreate) => void;
  isLoading: boolean;
}

function BankAccountModal({ onClose, onSubmit, isLoading }: BankModalProps) {
  const [form, setForm] = useState({
    name: "",
    institution: "",
    asset_type: "BANK_ACCOUNT",
    manual_amount: "",
    notes: "",
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      name: form.name,
      institution: form.institution,
      asset_type: form.asset_type,
      data_source: "MANUAL",
      manual_amount: form.manual_amount ? Number(form.manual_amount) : undefined,
      notes: form.notes || undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 w-full max-w-md p-6 mx-4">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">은행계좌 추가</h2>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">계좌 별칭 *</label>
            <input type="text" required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="예: 국민은행 주계좌"
              className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">은행명 *</label>
            <input type="text" required value={form.institution}
              onChange={(e) => setForm({ ...form, institution: e.target.value })}
              placeholder="예: 국민은행"
              className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">계좌 종류</label>
            <select value={form.asset_type} onChange={(e) => setForm({ ...form, asset_type: e.target.value })}
              className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
              <option value="BANK_ACCOUNT">입출금</option>
              <option value="DEPOSIT">예·적금</option>
              <option value="CASH_OTHER">현금/기타</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">잔액 (원)</label>
            <input type="number" value={form.manual_amount}
              onChange={(e) => setForm({ ...form, manual_amount: e.target.value })}
              placeholder="0" min="0"
              className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">메모</label>
            <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="선택 입력" rows={2}
              className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none" />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">취소</button>
            <button type="submit" disabled={isLoading}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {isLoading ? "저장 중..." : "추가"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Stock Account Modal (풀 기능) ────────────────────────────────────────────

interface StockModalProps {
  onClose: () => void;
  onSubmit: (data: AssetAccountCreate) => void;
  isLoading: boolean;
}

function StockAccountModal({ onClose, onSubmit, isLoading }: StockModalProps) {
  const [form, setForm] = useState<AssetAccountCreate>({
    name: "",
    asset_type: "STOCK_KIS",
    data_source: "KIS_API",
    institution: "",
  });
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
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">KIS 계좌번호</label>
              <input className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" value={form.kis_account_no ?? ""}
                onChange={(e) => set("kis_account_no", e.target.value)} placeholder="12345678-01" />
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">설정 페이지에서 KIS App Key/Secret을 먼저 등록하세요.</p>
            </div>
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

// ─── Real Estate Account Modal ───────────────────────────────────────────────

interface RealEstateModalProps {
  onClose: () => void;
  onSubmit: (data: AssetAccountCreate) => void;
  isLoading: boolean;
}

function RealEstateAccountModal({ onClose, onSubmit, isLoading }: RealEstateModalProps) {
  const [form, setForm] = useState({
    name: "",
    market_value: "",
    property_type: "아파트",
    address: "",
    purchase_price: "",
    purchase_date: "",
    mortgage_balance: "",
    include_in_total: true,
  });

  const marketValue = Number(form.market_value) || 0;
  const mortgage = Number(form.mortgage_balance) || 0;
  const equity = marketValue - mortgage;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const details: RealEstateDetails = {
      property_type: form.property_type || undefined,
      address: form.address || undefined,
      purchase_price_krw: form.purchase_price ? Number(form.purchase_price) : undefined,
      purchase_date: form.purchase_date || undefined,
      mortgage_balance_krw: form.mortgage_balance ? Number(form.mortgage_balance) : undefined,
    };
    onSubmit({
      name: form.name,
      asset_type: "REAL_ESTATE",
      data_source: "MANUAL",
      manual_amount: marketValue || undefined,
      real_estate_details: details,
      include_in_total: form.include_in_total,
    });
  };

  const inputCls = "w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 w-full max-w-md p-6 mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">부동산 추가</h2>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">부동산 이름 *</label>
            <input type="text" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="예: 강남 아파트" className={inputCls} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">종류</label>
              <select value={form.property_type} onChange={(e) => setForm({ ...form, property_type: e.target.value })}
                className={inputCls}>
                {PROPERTY_TYPE_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">매입일</label>
              <input type="date" value={form.purchase_date} onChange={(e) => setForm({ ...form, purchase_date: e.target.value })}
                className={inputCls} />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">주소</label>
            <input type="text" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })}
              placeholder="예: 서울시 강남구 ..." className={inputCls} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">현재 시세 (원) *</label>
              <input type="number" required min={0} value={form.market_value} onChange={(e) => setForm({ ...form, market_value: e.target.value })}
                placeholder="예: 800000000" className={inputCls} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">매입가 (원)</label>
              <input type="number" min={0} value={form.purchase_price} onChange={(e) => setForm({ ...form, purchase_price: e.target.value })}
                placeholder="예: 600000000" className={inputCls} />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">담보대출 잔액 (원)</label>
            <input type="number" min={0} value={form.mortgage_balance} onChange={(e) => setForm({ ...form, mortgage_balance: e.target.value })}
              placeholder="0" className={inputCls} />
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="include-in-total-create" checked={form.include_in_total}
              onChange={(e) => setForm({ ...form, include_in_total: e.target.checked })} className="w-4 h-4 text-blue-600" />
            <label htmlFor="include-in-total-create" className="text-sm text-gray-700 dark:text-gray-300">전체 자산에 포함</label>
          </div>
          {marketValue > 0 && (
            <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 text-sm space-y-1">
              <div className="flex justify-between text-gray-500 dark:text-gray-400">
                <span>시세</span><span>{fmtKrw(marketValue)}</span>
              </div>
              {mortgage > 0 && (
                <div className="flex justify-between text-gray-500 dark:text-gray-400">
                  <span>담보대출</span><span className="text-blue-500">−{fmtKrw(mortgage)}</span>
                </div>
              )}
              <div className="flex justify-between font-semibold text-gray-900 dark:text-gray-50 border-t border-gray-200 dark:border-gray-700 pt-1">
                <span>순자산</span><span className={equity >= 0 ? "text-red-500" : "text-blue-500"}>{fmtKrw(equity)}</span>
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">취소</button>
            <button type="submit" disabled={isLoading}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {isLoading ? "저장 중..." : "추가"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Real Estate Account Card ─────────────────────────────────────────────────

interface RealEstateCardProps {
  account: AssetAccount;
  onDelete: (id: string) => void;
  onEdit: (account: AssetAccount) => void;
  isDeleting: boolean;
}

function RealEstateAccountCard({ account, onDelete, onEdit, isDeleting }: RealEstateCardProps) {
  const re = account.real_estate_details;
  const marketValue = account.manual_amount ?? 0;
  const mortgage = re?.mortgage_balance_krw ?? 0;
  const equity = marketValue - mortgage;
  const purchasePrice = re?.purchase_price_krw ?? 0;
  const appreciation = purchasePrice > 0 ? marketValue - purchasePrice : null;

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-50 truncate">{account.name}</span>
            {re?.property_type && (
              <span className="px-2 py-0.5 bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-300 text-xs rounded-full shrink-0">{re.property_type}</span>
            )}
            {!account.include_in_total && (
              <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-xs rounded-full shrink-0">자산 제외</span>
            )}
          </div>
          {re?.address && <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">{re.address}</p>}
          {re?.purchase_date && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">매입일: {re.purchase_date}</p>}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={() => onEdit(account)} title="수정"
            className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors">
            <Pencil size={15} />
          </button>
          <button onClick={() => onDelete(account.id)} disabled={isDeleting} title="삭제"
            className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors disabled:opacity-50">
            <Trash2 size={15} />
          </button>
        </div>
      </div>
      <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">현재 시세</p>
          <p className="text-xs font-semibold text-gray-900 dark:text-gray-50 mt-0.5">{fmtKrw(marketValue)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">담보대출</p>
          <p className="text-xs font-semibold text-blue-500 mt-0.5">{mortgage > 0 ? `−${fmtKrw(mortgage)}` : "—"}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">순자산</p>
          <p className={`text-xs font-semibold mt-0.5 ${equity >= 0 ? "text-red-500" : "text-blue-500"}`}>{fmtKrw(equity)}</p>
        </div>
        {appreciation !== null && (
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">매입차익</p>
            <p className={`text-xs font-semibold mt-0.5 ${appreciation >= 0 ? "text-red-500" : "text-blue-500"}`}>
              {appreciation >= 0 ? "+" : ""}{fmtKrw(appreciation)}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Real Estate Edit Modal ───────────────────────────────────────────────────

interface RealEstateEditModalProps {
  account: AssetAccount;
  onClose: () => void;
  onSubmit: (id: string, data: Partial<AssetAccountCreate & { real_estate_details: RealEstateDetails }>) => void;
  isLoading: boolean;
}

function RealEstateEditModal({ account, onClose, onSubmit, isLoading }: RealEstateEditModalProps) {
  const re = account.real_estate_details;
  const [form, setForm] = useState({
    name: account.name,
    market_value: String(account.manual_amount ?? ""),
    property_type: re?.property_type ?? "아파트",
    address: re?.address ?? "",
    purchase_price: String(re?.purchase_price_krw ?? ""),
    purchase_date: re?.purchase_date ?? "",
    mortgage_balance: String(re?.mortgage_balance_krw ?? ""),
    include_in_total: account.include_in_total ?? true,
  });

  const marketValue = Number(form.market_value) || 0;
  const mortgage = Number(form.mortgage_balance) || 0;
  const equity = marketValue - mortgage;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(account.id, {
      name: form.name,
      manual_amount: marketValue || undefined,
      real_estate_details: {
        property_type: form.property_type || undefined,
        address: form.address || undefined,
        purchase_price_krw: form.purchase_price ? Number(form.purchase_price) : undefined,
        purchase_date: form.purchase_date || undefined,
        mortgage_balance_krw: form.mortgage_balance ? Number(form.mortgage_balance) : undefined,
      },
      include_in_total: form.include_in_total,
    });
  };

  const inputCls = "w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 w-full max-w-md p-6 mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">부동산 수정</h2>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">부동산 이름 *</label>
            <input type="text" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              className={inputCls} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">종류</label>
              <select value={form.property_type} onChange={(e) => setForm({ ...form, property_type: e.target.value })}
                className={inputCls}>
                {PROPERTY_TYPE_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">매입일</label>
              <input type="date" value={form.purchase_date} onChange={(e) => setForm({ ...form, purchase_date: e.target.value })}
                className={inputCls} />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">주소</label>
            <input type="text" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })}
              className={inputCls} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">현재 시세 (원) *</label>
              <input type="number" required min={0} value={form.market_value} onChange={(e) => setForm({ ...form, market_value: e.target.value })}
                className={inputCls} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">매입가 (원)</label>
              <input type="number" min={0} value={form.purchase_price} onChange={(e) => setForm({ ...form, purchase_price: e.target.value })}
                className={inputCls} />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">담보대출 잔액 (원)</label>
            <input type="number" min={0} value={form.mortgage_balance} onChange={(e) => setForm({ ...form, mortgage_balance: e.target.value })}
              className={inputCls} />
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="include-in-total-edit" checked={form.include_in_total}
              onChange={(e) => setForm({ ...form, include_in_total: e.target.checked })} className="w-4 h-4 text-blue-600" />
            <label htmlFor="include-in-total-edit" className="text-sm text-gray-700 dark:text-gray-300">전체 자산에 포함</label>
          </div>
          {marketValue > 0 && (
            <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 text-sm space-y-1">
              <div className="flex justify-between text-gray-500 dark:text-gray-400">
                <span>시세</span><span>{fmtKrw(marketValue)}</span>
              </div>
              {mortgage > 0 && (
                <div className="flex justify-between text-gray-500 dark:text-gray-400">
                  <span>담보대출</span><span className="text-blue-500">−{fmtKrw(mortgage)}</span>
                </div>
              )}
              <div className="flex justify-between font-semibold text-gray-900 dark:text-gray-50 border-t border-gray-200 dark:border-gray-700 pt-1">
                <span>순자산</span><span className={equity >= 0 ? "text-red-500" : "text-blue-500"}>{fmtKrw(equity)}</span>
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">취소</button>
            <button type="submit" disabled={isLoading}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {isLoading ? "저장 중..." : "수정"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Bank Account Card ────────────────────────────────────────────────────────

interface BankCardProps {
  account: AssetAccount;
  onDelete: (id: string) => void;
  onEditAmount: (id: string, amount: number) => void;
  onEditName: (id: string, name: string) => void;
  onSync: (id: string) => void;
  isDeleting: boolean;
  isSyncing: boolean;
}

function BankAccountCard({ account, onDelete, onEditAmount, onEditName, onSync, isDeleting, isSyncing }: BankCardProps) {
  const typeLabel = BANK_TYPE_LABELS[account.asset_type] ?? account.asset_type;
  const [editMode, setEditMode] = useState(false);
  const [editValue, setEditValue] = useState(String(account.manual_amount ?? 0));
  const [editNameMode, setEditNameMode] = useState(false);
  const [editNameValue, setEditNameValue] = useState(account.name);

  const handleSaveName = () => {
    const trimmed = editNameValue.trim();
    if (trimmed) {
      onEditName(account.id, trimmed);
      setEditNameMode(false);
    }
  };

  const handleSave = () => {
    const amount = Number(editValue);
    if (!isNaN(amount) && amount >= 0) {
      onEditAmount(account.id, amount);
      setEditMode(false);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 flex items-start justify-between gap-4">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          {editNameMode ? (
            <>
              <input
                type="text"
                value={editNameValue}
                autoFocus
                onChange={(e) => setEditNameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSaveName();
                  if (e.key === "Escape") { setEditNameMode(false); setEditNameValue(account.name); }
                }}
                className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2 py-0.5 text-sm w-40 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button onClick={handleSaveName} className="text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium">저장</button>
              <button onClick={() => { setEditNameMode(false); setEditNameValue(account.name); }} className="text-xs text-gray-400 dark:text-gray-500 hover:underline">취소</button>
            </>
          ) : (
            <>
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-50 truncate">{account.name}</span>
              <button
                onClick={() => { setEditNameValue(account.name); setEditNameMode(true); }}
                title="계좌명 수정"
                className="p-0.5 text-gray-300 dark:text-gray-600 hover:text-blue-400 transition-colors shrink-0">
                <Pencil size={10} />
              </button>
            </>
          )}
          <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-xs rounded-full shrink-0">{typeLabel}</span>
        </div>
        {account.institution && <p className="text-sm text-gray-500 dark:text-gray-400">{account.institution}</p>}
        {editMode ? (
          <div className="flex items-center gap-2 mt-2">
            <input
              type="number"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2 py-1 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-blue-500"
              autoFocus
              onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") setEditMode(false); }}
            />
            <button onClick={handleSave} className="text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium">저장</button>
            <button onClick={() => setEditMode(false)} className="text-xs text-gray-400 dark:text-gray-500 hover:underline">취소</button>
          </div>
        ) : (
          account.manual_amount != null && (
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mt-1">{fmtKrw(account.manual_amount)}</p>
          )
        )}
        {account.notes && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 truncate">{account.notes}</p>}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {account.data_source === "MANUAL" && (
          <button
            onClick={() => { setEditValue(String(account.manual_amount ?? 0)); setEditMode(true); }}
            title="금액 수정"
            className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors">
            <Pencil size={15} />
          </button>
        )}
        {account.data_source === "OPEN_BANKING" && (
          <button
            onClick={() => onSync(account.id)}
            disabled={isSyncing}
            title="잔액 새로고침"
            className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors disabled:opacity-40">
            <RefreshCw size={15} className={isSyncing ? "animate-spin" : ""} />
          </button>
        )}
        <button onClick={() => onDelete(account.id)} disabled={isDeleting}
          className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors disabled:opacity-50"
          title="계좌 삭제">
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  );
}

// ─── Stock Account Card (관리 버튼 포함) ──────────────────────────────────────

interface StockCardProps {
  account: AssetAccount;
  stats?: AccountStats;
  onDelete: (id: string) => void;
  onManagePositions: (account: { id: string; name: string; dataSource: string }) => void;
  onTransactions: (account: { id: string; name: string }) => void;
  onEditDeposit: (id: string, amount: number) => void;
  onEditName: (id: string, name: string) => void;
  onSync: (id: string) => void;
  isSyncing: boolean;
  isDeleting: boolean;
}

function StockAccountCard({ account, stats, onDelete, onManagePositions, onTransactions, onEditDeposit, onEditName, onSync, isSyncing, isDeleting }: StockCardProps) {
  const typeLabel = STOCK_TYPE_LABELS[account.asset_type] ?? account.asset_type;
  const accountNo = account.kis_account_no ?? account.ls_account_no ?? null;
  const hasStats = stats && (stats.amount_krw > 0 || stats.deposit_total > 0 || stats.dividend_total > 0);
  const pnl = stats?.unrealized_pnl ?? 0;
  const ret = stats?.invested_krw ? (pnl / stats.invested_krw) * 100 : 0;
  const [editNameMode, setEditNameMode] = useState(false);
  const [editNameValue, setEditNameValue] = useState(account.name);
  const [editDepositMode, setEditDepositMode] = useState(false);

  const handleSaveName = () => {
    const trimmed = editNameValue.trim();
    if (trimmed) {
      onEditName(account.id, trimmed);
      setEditNameMode(false);
    }
  };
  const [editDepositValue, setEditDepositValue] = useState("");
  const [depositCurrency, setDepositCurrency] = useState<"KRW" | "USD">("KRW");
  const [depositUsdValue, setDepositUsdValue] = useState<number>(0);
  const [usdRate, setUsdRate] = useState<number | null>(null);

  useEffect(() => {
    fetchExchangeRate().then((r) => setUsdRate(r.usd_krw)).catch(() => {});
  }, []);

  const handleSave = () => {
    const krwAmount = depositCurrency === "USD"
      ? Math.round(depositUsdValue * (usdRate ?? 1))
      : Number(editDepositValue);
    onEditDeposit(account.id, krwAmount);
    setEditDepositMode(false);
  };

  const handleCancel = () => {
    setEditDepositMode(false);
    setDepositCurrency("KRW");
    setDepositUsdValue(0);
  };

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {editNameMode ? (
              <>
                <input
                  type="text"
                  value={editNameValue}
                  autoFocus
                  onChange={(e) => setEditNameValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveName();
                    if (e.key === "Escape") { setEditNameMode(false); setEditNameValue(account.name); }
                  }}
                  className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2 py-0.5 text-sm w-40 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button onClick={handleSaveName} className="text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium">저장</button>
                <button onClick={() => { setEditNameMode(false); setEditNameValue(account.name); }} className="text-xs text-gray-400 dark:text-gray-500 hover:underline">취소</button>
              </>
            ) : (
              <>
                <span className="text-sm font-semibold text-gray-900 dark:text-gray-50 truncate">{account.name}</span>
                <button
                  onClick={() => { setEditNameValue(account.name); setEditNameMode(true); }}
                  title="계좌명 수정"
                  className="p-0.5 text-gray-300 dark:text-gray-600 hover:text-blue-400 transition-colors shrink-0">
                  <Pencil size={10} />
                </button>
              </>
            )}
            <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-xs rounded-full shrink-0">{typeLabel}</span>
          </div>
          {account.institution && <p className="text-sm text-gray-500 dark:text-gray-400">{account.institution}</p>}
          {accountNo && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{accountNo}</p>}
          {account.notes && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 truncate">{account.notes}</p>}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {(account.data_source === "KIS_API" || account.data_source === "LS_SEC") && (
            <button onClick={() => onSync(account.id)} disabled={isSyncing}
              title="KIS 데이터 동기화"
              className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors disabled:opacity-50">
              {isSyncing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            </button>
          )}
          <button onClick={() => onManagePositions({ id: account.id, name: account.name, dataSource: account.data_source })}
            title="종목 관리"
            className="p-1.5 text-gray-400 hover:text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-950 rounded-lg transition-colors">
            <BarChart2 size={15} />
          </button>
          <button onClick={() => onTransactions({ id: account.id, name: account.name })}
            title="입출금 내역"
            className="p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 dark:hover:bg-green-950 rounded-lg transition-colors">
            <Receipt size={15} />
          </button>
          <button onClick={() => onDelete(account.id)} disabled={isDeleting}
            title="계좌 삭제"
            className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors disabled:opacity-50">
            <Trash2 size={15} />
          </button>
        </div>
      </div>
      {hasStats && (
        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 grid grid-cols-3 gap-x-4 gap-y-2 sm:grid-cols-6">
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">평가금액</p>
            <p className="text-xs font-semibold text-gray-900 dark:text-gray-50 mt-0.5">{fmtKrw(stats!.amount_krw)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">평가손익</p>
            <p className={`text-xs font-semibold mt-0.5 ${pnl >= 0 ? "text-red-500" : "text-blue-500"}`}>
              {pnl >= 0 ? "+" : ""}{fmtKrw(pnl)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">수익률</p>
            <p className={`text-xs font-semibold mt-0.5 ${ret >= 0 ? "text-red-500" : "text-blue-500"}`}>
              {ret >= 0 ? "+" : ""}{ret.toFixed(2)}%
            </p>
          </div>
          <div>
            <div className="flex items-center justify-between">
              <p className="text-xs text-gray-400 dark:text-gray-500">예수금</p>
              {editDepositMode && (
                <div className="flex gap-0.5 text-xs">
                  {(["KRW", "USD"] as const).map((c) => (
                    <button key={c} type="button"
                      onClick={() => { setDepositCurrency(c); setDepositUsdValue(0); }}
                      className={`px-1.5 py-0.5 rounded transition-colors ${
                        depositCurrency === c ? "bg-blue-600 text-white" : "text-gray-400 hover:text-gray-600"
                      }`}>
                      {c}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {editDepositMode ? (
              depositCurrency === "USD" ? (
                <div>
                  <div className="flex items-center gap-1 mt-0.5">
                    <span className="text-xs text-gray-400 shrink-0">$</span>
                    <input
                      type="number" autoFocus step="0.01" min={0}
                      value={depositUsdValue || ""}
                      onChange={(e) => setDepositUsdValue(parseFloat(e.target.value) || 0)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleSave();
                        if (e.key === "Escape") handleCancel();
                      }}
                      className="w-20 border rounded px-1.5 py-0.5 text-xs"
                    />
                    <button onClick={handleSave} className="text-xs text-blue-500 hover:text-blue-700">저장</button>
                    <button onClick={handleCancel} className="text-xs text-gray-400">취소</button>
                  </div>
                  {usdRate && depositUsdValue > 0 && (
                    <p className="text-xs text-gray-400 mt-0.5">
                      ≈ {fmtKrw(Math.round(depositUsdValue * usdRate))}
                    </p>
                  )}
                </div>
              ) : (
                <div className="flex items-center gap-1 mt-0.5">
                  <input
                    type="number" autoFocus
                    value={editDepositValue}
                    onChange={(e) => setEditDepositValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSave();
                      if (e.key === "Escape") handleCancel();
                    }}
                    className="w-20 border rounded px-1.5 py-0.5 text-xs"
                  />
                  <button onClick={handleSave} className="text-xs text-blue-500 hover:text-blue-700">저장</button>
                  <button onClick={handleCancel} className="text-xs text-gray-400">취소</button>
                </div>
              )
            ) : (
              <div className="flex items-center gap-1 mt-0.5">
                <p className="text-xs font-semibold text-gray-700 dark:text-gray-300">{fmtKrw(account.deposit_krw ?? 0)}</p>
                <button
                  onClick={() => { setEditDepositValue(String(account.deposit_krw ?? 0)); setDepositCurrency("KRW"); setDepositUsdValue(0); setEditDepositMode(true); }}
                  className="p-0.5 text-gray-300 hover:text-blue-400 transition-colors">
                  <Pencil size={10} />
                </button>
              </div>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">누적 입금</p>
            <p className="text-xs font-semibold text-blue-600 dark:text-blue-400 mt-0.5">{fmtKrw(stats!.deposit_total)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">누적 배당</p>
            <p className="text-xs font-semibold text-green-600 dark:text-green-400 mt-0.5">{fmtKrw(stats!.dividend_total)}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Transaction Tab ──────────────────────────────────────────────────────────

const today = new Date().toISOString().slice(0, 10);
const currentYear = new Date().getFullYear();
const YEAR_OPTIONS = Array.from({ length: 5 }, (_, i) => currentYear - i);

interface TransactionTabProps {
  accounts: AssetAccount[];
}

function TransactionTab({ accounts }: TransactionTabProps) {
  const qc = useQueryClient();
  const [selectedYear, setSelectedYear] = useState(currentYear);
  const [filterAccountId, setFilterAccountId] = useState("");
  const [filterType, setFilterType] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);
  const [depositPrompt, setDepositPrompt] = useState<{
    accountId: string;
    amount: number;
    txType: "DEPOSIT" | "WITHDRAWAL" | "DIVIDEND";
    currentDeposit: number;
  } | null>(null);
  const [form, setForm] = useState<TransactionCreate>({
    account_id: "",
    transaction_type: "DEPOSIT",
    amount: 0,
    transaction_date: today,
    ticker: "",
    notes: "",
  });

  const [currency, setCurrency] = useState<"KRW" | "USD">("KRW");
  const [amountUsd, setAmountUsd] = useState<number>(0);
  const [usdRate, setUsdRate] = useState<number | null>(null);
  const [tickerDirect, setTickerDirect] = useState(false);
  const [tickerQuery, setTickerQuery] = useState("");
  const [tickerSuggestions, setTickerSuggestions] = useState<StockSuggestion[]>([]);
  const [tickerSearchLoading, setTickerSearchLoading] = useState(false);
  const [showTickerSuggestions, setShowTickerSuggestions] = useState(false);
  const tickerSearchTimer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    fetchExchangeRate().then((r) => setUsdRate(r.usd_krw)).catch(() => {});
  }, []);

  const { data: txList = [], isLoading } = useQuery({
    queryKey: ["transactions", "all", selectedYear],
    queryFn: () => fetchTransactions({ year: selectedYear }),
  });

  const { data: positionsData } = useQuery({
    queryKey: ["account-positions", form.account_id],
    queryFn: () =>
      api
        .get<{ positions: Array<{ ticker: string; name: string; qty: number }> }>(
          `/assets/${form.account_id}/positions`
        )
        .then((r) => r.data),
    enabled: !!form.account_id && form.transaction_type === "DIVIDEND",
    staleTime: 60_000,
  });
  const accountPositions = positionsData?.positions ?? [];

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["transactions"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const triggerDepositPrompt = (accId: string, amt: number, txType: string) => {
    if (!accId || amt <= 0) return;
    const acc = accounts.find((a) => a.id === accId);
    if (!acc || !STOCK_TYPES.includes(acc.asset_type)) return;
    setDepositPrompt({
      accountId: accId,
      amount: amt,
      txType: txType as "DEPOSIT" | "WITHDRAWAL" | "DIVIDEND",
      currentDeposit: acc.deposit_krw ?? 0,
    });
  };

  const createMut = useMutation({
    mutationFn: createTransaction,
    onSuccess: (_, vars) => {
      invalidate();
      const accId = vars.account_id as string ?? "";
      const amt = vars.amount ?? 0;
      const txType = vars.transaction_type;
      setForm({ account_id: "", transaction_type: "DEPOSIT", amount: 0, transaction_date: today, ticker: "", notes: "" });
      setCurrency("KRW");
      setAmountUsd(0);
      setTickerDirect(false);
      setTickerQuery("");
      setTickerSuggestions([]);
      setShowTickerSuggestions(false);
      setShowForm(false);
      triggerDepositPrompt(accId, amt, txType);
    },
    onError: () => toast("내역 저장에 실패했습니다"),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<TransactionCreate> }) =>
      updateTransaction(id, data),
    onSuccess: (_, vars) => {
      invalidate();
      const accId = vars.data?.account_id as string ?? "";
      const amt = vars.data?.amount ?? 0;
      const txType = vars.data?.transaction_type ?? "";
      setEditingTx(null);
      setForm({ account_id: "", transaction_type: "DEPOSIT", amount: 0, transaction_date: today, ticker: "", notes: "" });
      setCurrency("KRW");
      setAmountUsd(0);
      setTickerDirect(false);
      setTickerQuery("");
      setTickerSuggestions([]);
      setShowTickerSuggestions(false);
      setShowForm(false);
      triggerDepositPrompt(accId, amt, txType);
    },
    onError: () => toast("내역 수정에 실패했습니다"),
  });

  const deleteMut = useMutation({
    mutationFn: deleteTransaction,
    onSuccess: invalidate,
    onError: () => toast("내역 삭제에 실패했습니다"),
  });

  const startEdit = (tx: Transaction) => {
    setEditingTx(tx);
    setForm({
      account_id: tx.account_id ?? "",
      transaction_type: tx.transaction_type,
      amount: tx.amount,
      transaction_date: tx.transaction_date,
      ticker: tx.ticker ?? "",
      notes: tx.notes ?? "",
    });
    setTickerDirect(!!tx.ticker);
    setTickerQuery(tx.ticker ?? "");
    setCurrency("KRW");
    setAmountUsd(0);
    setTickerSuggestions([]);
    setShowTickerSuggestions(false);
    setShowForm(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.amount || form.amount <= 0) return;
    const payload = {
      ...form,
      account_id: form.account_id || undefined,
      ticker: form.transaction_type === "DIVIDEND" && form.ticker ? form.ticker : undefined,
      notes: form.notes || undefined,
    };
    if (editingTx) {
      updateMut.mutate({ id: editingTx.id, data: payload });
    } else {
      createMut.mutate(payload);
    }
  };

  const yearDeposit = txList.filter((t) => t.transaction_type === "DEPOSIT").reduce((s, t) => s + t.amount, 0);
  const yearDividend = txList.filter((t) => t.transaction_type === "DIVIDEND").reduce((s, t) => s + t.amount, 0);

  const filtered = txList.filter((t) => {
    if (filterAccountId && t.account_id !== filterAccountId) return false;
    if (filterType && t.transaction_type !== filterType) return false;
    return true;
  });

  const accountMap = Object.fromEntries(accounts.map((a) => [a.id, a.name]));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{selectedYear}년 입금 합계</p>
          <p className="text-xl font-bold text-blue-600 dark:text-blue-400">{fmtKrw(yearDeposit)}</p>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{selectedYear}년 배당 합계</p>
          <p className="text-xl font-bold text-green-600 dark:text-green-400">{fmtKrw(yearDividend)}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select value={filterAccountId} onChange={(e) => setFilterAccountId(e.target.value)}
          className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option value="">전체 계좌</option>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={filterType} onChange={(e) => setFilterType(e.target.value)}
          className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option value="">전체 유형</option>
          <option value="DEPOSIT">입금</option>
          <option value="WITHDRAWAL">출금</option>
          <option value="DIVIDEND">배당</option>
        </select>
        <select value={selectedYear} onChange={(e) => setSelectedYear(Number(e.target.value))}
          className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          {YEAR_OPTIONS.map((y) => <option key={y} value={y}>{y}년</option>)}
        </select>
        <button onClick={() => setShowForm((v) => !v)}
          className="ml-auto flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
          {showForm ? <ChevronUp size={16} /> : <Plus size={16} />}
          내역 추가
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className={`bg-white dark:bg-gray-900 rounded-2xl border p-5 space-y-4 ${editingTx ? "border-amber-200 dark:border-amber-800" : "border-blue-200 dark:border-blue-800"}`}>
          <div className="flex gap-2">
            {(["DEPOSIT", "WITHDRAWAL", "DIVIDEND"] as const).map((t) => (
              <button key={t} type="button"
                onClick={() => { setForm((f) => ({ ...f, transaction_type: t })); setCurrency("KRW"); setAmountUsd(0); setTickerDirect(false); setTickerQuery(""); setTickerSuggestions([]); setShowTickerSuggestions(false); }}
                className={`flex-1 py-2 text-sm font-medium rounded-lg border transition-colors ${
                  form.transaction_type === t
                    ? "bg-blue-600 text-white border-blue-600"
                    : "border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-blue-300 dark:hover:border-blue-600"
                }`}>
                {TX_LABELS[t]}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">계좌 선택</label>
              <select value={form.account_id}
                onChange={(e) => { setForm((f) => ({ ...f, account_id: e.target.value, ticker: "" })); setTickerDirect(false); setTickerQuery(""); setTickerSuggestions([]); setShowTickerSuggestions(false); }}
                className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="">계좌 미지정</option>
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">날짜 *</label>
              <input type="date" required value={form.transaction_date}
                onChange={(e) => setForm((f) => ({ ...f, transaction_date: e.target.value }))}
                className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">금액 *</label>
                {form.transaction_type === "DIVIDEND" && (
                  <div className="flex gap-0.5 text-xs">
                    {(["KRW", "USD"] as const).map((c) => (
                      <button key={c} type="button"
                        onClick={() => { setCurrency(c); setAmountUsd(0); }}
                        className={`px-1.5 py-0.5 rounded transition-colors ${
                          currency === c ? "bg-blue-600 text-white" : "text-gray-400 hover:text-gray-600"
                        }`}>
                        {c}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {currency === "USD" && form.transaction_type === "DIVIDEND" ? (
                <div>
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className="text-sm text-gray-400 shrink-0">$</span>
                    <input type="number"
                      value={amountUsd || ""}
                      onChange={(e) => {
                        const usd = parseFloat(e.target.value) || 0;
                        setAmountUsd(usd);
                        setForm((f) => ({ ...f, amount: usdRate ? Math.round(usd * usdRate) : f.amount }));
                      }}
                      placeholder="0.00" step="0.01" min={0}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                  {usdRate && amountUsd > 0 && (
                    <p className="text-xs text-gray-400 text-right mt-0.5">
                      ≈ ₩{Math.round(amountUsd * usdRate).toLocaleString()}
                    </p>
                  )}
                  {!usdRate && currency === "USD" && (
                    <p className="text-xs text-amber-500 mt-0.5">환율 정보를 불러오는 중입니다</p>
                  )}
                </div>
              ) : (
                <input type="number" required min={1} value={form.amount || ""}
                  onChange={(e) => setForm((f) => ({ ...f, amount: Number(e.target.value) }))}
                  placeholder="예: 500000"
                  className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              )}
            </div>
            {form.transaction_type === "DIVIDEND" ? (
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">종목 (선택)</label>
                {accountPositions.length > 0 && !tickerDirect ? (
                  <select
                    value={form.ticker || ""}
                    onChange={(e) => {
                      if (e.target.value === "__direct__") {
                        setTickerDirect(true);
                        setForm((f) => ({ ...f, ticker: "" }));
                      } else {
                        setForm((f) => ({ ...f, ticker: e.target.value }));
                      }
                    }}
                    className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">종목 선택</option>
                    {accountPositions.map((p) => (
                      <option key={p.ticker} value={p.ticker}>{p.name}</option>
                    ))}
                    <option value="__direct__">기타 종목 직접 입력...</option>
                  </select>
                ) : (
                  <div className="flex gap-1 mt-1">
                    <div className="relative w-full">
                      <input
                        value={tickerQuery}
                        onChange={(e) => {
                          const v = e.target.value;
                          setTickerQuery(v);
                          setForm((f) => ({ ...f, ticker: v }));
                          setShowTickerSuggestions(true);
                          if (tickerSearchTimer.current) clearTimeout(tickerSearchTimer.current);
                          if (!v.trim()) { setTickerSuggestions([]); return; }
                          tickerSearchTimer.current = setTimeout(async () => {
                            setTickerSearchLoading(true);
                            try { setTickerSuggestions(await searchStocks(v.trim())); }
                            catch { setTickerSuggestions([]); }
                            finally { setTickerSearchLoading(false); }
                          }, 300);
                        }}
                        onFocus={() => tickerSuggestions.length > 0 && setShowTickerSuggestions(true)}
                        onBlur={() => setTimeout(() => setShowTickerSuggestions(false), 150)}
                        placeholder="종목명 또는 코드 검색"
                        className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                      {tickerSearchLoading && (
                        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400 dark:text-gray-500">검색 중...</span>
                      )}
                      {showTickerSuggestions && tickerSuggestions.length > 0 && (
                        <ul className="absolute z-20 left-0 right-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg mt-0.5 max-h-48 overflow-y-auto">
                          {tickerSuggestions.map((s) => (
                            <li key={s.ticker}
                              className="px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-950 cursor-pointer text-sm flex items-center gap-2"
                              onMouseDown={() => {
                                setTickerQuery(s.name);
                                setForm((f) => ({ ...f, ticker: s.ticker }));
                                setTickerSuggestions([]);
                                setShowTickerSuggestions(false);
                              }}>
                              <span className="font-medium text-blue-700 dark:text-blue-400">{s.ticker}</span>
                              <span className="text-gray-700 dark:text-gray-300">{s.name}</span>
                              <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">{s.market}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                    {accountPositions.length > 0 && (
                      <button type="button"
                        onClick={() => { setTickerDirect(false); setForm((f) => ({ ...f, ticker: "" })); setTickerQuery(""); setTickerSuggestions([]); setShowTickerSuggestions(false); }}
                        className="shrink-0 px-2 text-xs text-blue-500 hover:text-blue-700 whitespace-nowrap">
                        ← 목록
                      </button>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">메모 (선택)</label>
                <input value={form.notes || ""}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                  placeholder="메모 입력"
                  className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
            )}
          </div>
          {form.transaction_type === "DIVIDEND" && (
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">메모 (선택)</label>
              <input value={form.notes || ""}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                placeholder="메모 입력"
                className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => { setShowForm(false); setEditingTx(null); }}
              className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">취소</button>
            <button type="submit" disabled={(editingTx ? updateMut.isPending : createMut.isPending) || !form.amount}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {(editingTx ? updateMut.isPending : createMut.isPending) ? "저장 중..." : editingTx ? "수정" : "추가"}
            </button>
          </div>
        </form>
      )}

      {showForm && form.transaction_type === "DIVIDEND" && accountPositions.length > 0 && (
        <div className="bg-gray-50 dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-4">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">보유 종목 참고</p>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-400 dark:text-gray-500">
                <th className="text-left pb-1">종목코드</th>
                <th className="text-left pb-1">종목명</th>
                <th className="text-right pb-1">수량</th>
              </tr>
            </thead>
            <tbody>
              {accountPositions.map((p) => (
                <tr
                  key={p.ticker}
                  className="border-t border-gray-100 dark:border-gray-700 cursor-pointer hover:bg-white dark:hover:bg-gray-700 transition-colors"
                  onClick={() => setForm((f) => ({ ...f, ticker: p.ticker }))}
                >
                  <td className="py-1.5 text-blue-600 dark:text-blue-400 font-medium">{p.ticker}</td>
                  <td className="py-1.5 text-gray-700 dark:text-gray-300">{p.name}</td>
                  <td className="py-1.5 text-right text-gray-500 dark:text-gray-400">{p.qty.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 예수금 반영 확인 팝업 */}
      {depositPrompt && (
        <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-2xl p-4">
          <p className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-1">예수금에 반영할까요?</p>
          <p className="text-xs text-blue-600 dark:text-blue-400 mb-3">
            {fmtKrw(depositPrompt.currentDeposit)}
            {" → "}
            {fmtKrw(Math.max(0, depositPrompt.currentDeposit + (depositPrompt.txType === "WITHDRAWAL" ? -depositPrompt.amount : depositPrompt.amount)))}
            {" ("}
            {depositPrompt.txType === "WITHDRAWAL" ? "-" : "+"}
            {fmtKrw(depositPrompt.amount)}{")"}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => {
                const next = Math.max(0, depositPrompt.currentDeposit + (depositPrompt.txType === "WITHDRAWAL" ? -depositPrompt.amount : depositPrompt.amount));
                updateAccount(depositPrompt.accountId, { deposit_krw: next }).then(() => {
                  qc.invalidateQueries({ queryKey: ["accounts"] });
                  qc.invalidateQueries({ queryKey: ["portfolio-overview"] });
                  qc.invalidateQueries({ queryKey: ["dashboard"] });
                });
                setDepositPrompt(null);
              }}
              className="px-4 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 transition-colors"
            >
              반영
            </button>
            <button
              onClick={() => setDepositPrompt(null)}
              className="px-4 py-1.5 text-gray-500 dark:text-gray-400 text-xs rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              건너뜀
            </button>
          </div>
        </div>
      )}

      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        {isLoading ? (
          <div className="py-12 text-center text-gray-400 dark:text-gray-500 text-sm">불러오는 중...</div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center text-gray-400 dark:text-gray-500 text-sm">등록된 내역이 없습니다.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
                <th className="text-left px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">날짜</th>
                <th className="text-left px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">구분</th>
                <th className="text-right px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">금액</th>
                <th className="text-left px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">계좌</th>
                <th className="text-left px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">메모</th>
                <th className="px-3 py-3" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((tx: Transaction) => (
                <tr key={tx.id} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                  <td className="px-3 py-3 text-gray-500 dark:text-gray-400 whitespace-nowrap text-xs">{tx.transaction_date}</td>
                  <td className={`px-3 py-3 font-medium whitespace-nowrap ${TX_COLORS[tx.transaction_type]}`}>
                    <span>{TX_LABELS[tx.transaction_type]}</span>
                    {tx.ticker && <span className="block text-xs text-gray-400 dark:text-gray-500 font-normal mt-0.5">{tx.ticker}</span>}
                  </td>
                  <td className="px-3 py-3 text-right font-semibold text-gray-900 dark:text-gray-50 whitespace-nowrap">{fmtKrw(tx.amount)}</td>
                  <td className="px-3 py-3 text-gray-500 dark:text-gray-400 text-xs whitespace-nowrap">
                    {tx.account_id ? (accountMap[tx.account_id] ?? "—") : "—"}
                  </td>
                  <td className="px-3 py-3 text-gray-400 dark:text-gray-500 text-sm">
                    <div className="max-w-[160px] truncate">{tx.notes || "—"}</div>
                  </td>
                  <td className="px-3 py-3 text-right">
                    <div className="flex justify-end gap-1">
                      <button onClick={() => startEdit(tx)}
                        className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors">
                        <Pencil size={15} />
                      </button>
                      <button onClick={() => deleteMut.mutate(tx.id)} disabled={deleteMut.isPending}
                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function AssetManagementPage() {
  const [tab, setTab] = useState<Tab>("은행계좌");
  const [showBankModal, setShowBankModal] = useState(false);
  const [showStockModal, setShowStockModal] = useState(false);
  const [showRealEstateModal, setShowRealEstateModal] = useState(false);
  const [editingRealEstate, setEditingRealEstate] = useState<AssetAccount | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [syncingBankId, setSyncingBankId] = useState<string | null>(null);
  const [syncingStockIds, setSyncingStockIds] = useState<Set<string>>(new Set());
  const [positionsAccount, setPositionsAccount] = useState<{ id: string; name: string; dataSource: string } | null>(null);
  const [txAccount, setTxAccount] = useState<{ id: string; name: string; depositKrw: number } | null>(null);

  const queryClient = useQueryClient();

  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ["accounts"],
    queryFn: fetchAccounts,
  });

  const { data: overview } = useQuery({
    queryKey: ["portfolio-overview"],
    queryFn: fetchStockOverview,
    enabled: tab === "증권계좌",
  });

  const { data: allTx = [] } = useQuery({
    queryKey: ["transactions", "all-time"],
    queryFn: () => fetchTransactions(),
    enabled: tab === "증권계좌",
  });

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["accounts"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio-overview"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const createMutation = useMutation({
    mutationFn: createAccount,
    onSuccess: async (data) => {
      invalidateAll();
      setShowBankModal(false);
      setShowStockModal(false);
      if (data.data_source === "KIS_API" || data.data_source === "LS_SEC") {
        setSyncingStockIds((prev) => new Set(prev).add(data.id));
        try {
          await syncAccount(data.id);
          invalidateAll();
        } catch {
          toast("초기 동기화 실패. 계좌 카드의 동기화 버튼으로 재시도하세요.");
        } finally {
          setSyncingStockIds((prev) => {
            const next = new Set(prev);
            next.delete(data.id);
            return next;
          });
        }
      }
    },
    onError: () => toast("계좌 추가에 실패했습니다"),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAccount,
    onSuccess: () => {
      invalidateAll();
      setDeletingId(null);
    },
    onError: () => toast("계좌 삭제에 실패했습니다"),
  });

  const handleDelete = (id: string) => {
    if (!confirm("계좌를 삭제하시겠습니까?")) return;
    setDeletingId(id);
    deleteMutation.mutate(id);
  };

  const updateAmountMutation = useMutation({
    mutationFn: ({ id, amount }: { id: string; amount: number }) =>
      updateAccount(id, { manual_amount: amount }),
    onSuccess: () => invalidateAll(),
    onError: () => toast("금액 수정에 실패했습니다"),
  });

  const handleEditAmount = (id: string, amount: number) => {
    updateAmountMutation.mutate({ id, amount });
  };

  const updateDepositMutation = useMutation({
    mutationFn: ({ id, deposit_krw }: { id: string; deposit_krw: number }) =>
      updateAccount(id, { deposit_krw }),
    onSuccess: () => invalidateAll(),
    onError: () => toast("예수금 수정에 실패했습니다"),
  });

  const handleEditDeposit = (id: string, amount: number) => {
    updateDepositMutation.mutate({ id, deposit_krw: amount });
  };

  const updateNameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      updateAccount(id, { name }),
    onSuccess: () => invalidateAll(),
    onError: () => toast("계좌명 수정에 실패했습니다"),
  });

  const handleEditName = (id: string, name: string) => {
    updateNameMutation.mutate({ id, name });
  };

  const updateRealEstateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateAccount>[1] }) =>
      updateAccount(id, data),
    onSuccess: () => {
      invalidateAll();
      setEditingRealEstate(null);
    },
    onError: () => toast("부동산 정보 수정에 실패했습니다"),
  });

  const handleSyncBank = async (id: string) => {
    setSyncingBankId(id);
    try {
      await syncAccount(id);
      invalidateAll();
    } finally {
      setSyncingBankId(null);
    }
  };

  const handleSyncKisAccount = async (id: string) => {
    setSyncingStockIds((prev) => new Set(prev).add(id));
    try {
      await syncAccount(id);
      invalidateAll();
      toast("동기화 완료");
    } catch {
      toast("동기화 실패. KIS API 자격증명을 확인하세요.");
    } finally {
      setSyncingStockIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const bankAccounts = accounts.filter((a) => BANK_TYPES.includes(a.asset_type));
  const stockAccounts = accounts.filter((a) => STOCK_TYPES.includes(a.asset_type));
  const realEstateAccounts = accounts.filter((a) => REAL_ESTATE_TYPES.includes(a.asset_type));
  const currentBankOrStock = tab === "은행계좌" ? bankAccounts : stockAccounts;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-50">자산관리</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">계좌를 등록하고 입출금·배당 내역을 관리합니다.</p>
      </div>

      {/* Tab */}
      <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-xl p-1 w-fit mb-6">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t ? "bg-white dark:bg-gray-700 shadow text-gray-900 dark:text-gray-50" : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            }`}>
            {t}
          </button>
        ))}
      </div>

      {/* 입출금·배당 탭 */}
      {tab === "입출금·배당" && <TransactionTab accounts={accounts} />}

      {/* 부동산 탭 */}
      {tab === "부동산" && (
        <>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
              <Home size={18} />
              <span className="text-sm font-medium">
                부동산 {isLoading ? "" : `(${realEstateAccounts.length}개)`}
              </span>
            </div>
            <button onClick={() => setShowRealEstateModal(true)}
              className="flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
              <Plus size={16} />
              부동산 추가
            </button>
          </div>
          {isLoading ? (
            <div className="text-center py-12 text-gray-400 text-sm">불러오는 중...</div>
          ) : realEstateAccounts.length === 0 ? (
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-12 text-center">
              <p className="text-gray-400 dark:text-gray-500 text-sm">등록된 부동산이 없습니다.</p>
              <button onClick={() => setShowRealEstateModal(true)}
                className="mt-3 text-blue-600 dark:text-blue-400 text-sm hover:underline">
                + 부동산 추가하기
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {realEstateAccounts.map((account) => (
                <RealEstateAccountCard key={account.id} account={account}
                  onDelete={handleDelete}
                  onEdit={(acc) => setEditingRealEstate(acc)}
                  isDeleting={deletingId === account.id && deleteMutation.isPending} />
              ))}
            </div>
          )}
        </>
      )}

      {/* 계좌 탭 */}
      {tab !== "입출금·배당" && tab !== "부동산" && (
        <>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
              {tab === "은행계좌" ? <Building2 size={18} /> : <TrendingUp size={18} />}
              <span className="text-sm font-medium">
                {tab} {isLoading ? "" : `(${currentBankOrStock.length}개)`}
              </span>
            </div>
            <button
              onClick={() => tab === "은행계좌" ? setShowBankModal(true) : setShowStockModal(true)}
              className="flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
              <Plus size={16} />
              계좌 추가
            </button>
          </div>

          {isLoading ? (
            <div className="text-center py-12 text-gray-400 text-sm">불러오는 중...</div>
          ) : currentBankOrStock.length === 0 ? (
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-12 text-center">
              <p className="text-gray-400 dark:text-gray-500 text-sm">등록된 {tab}이 없습니다.</p>
              <button
                onClick={() => tab === "은행계좌" ? setShowBankModal(true) : setShowStockModal(true)}
                className="mt-3 text-blue-600 dark:text-blue-400 text-sm hover:underline">
                + 계좌 추가하기
              </button>
            </div>
          ) : tab === "은행계좌" ? (
            <div className="space-y-3">
              {bankAccounts.map((account) => (
                <BankAccountCard key={account.id} account={account}
                  onDelete={handleDelete}
                  onEditAmount={handleEditAmount}
                  onEditName={handleEditName}
                  onSync={handleSyncBank}
                  isDeleting={deletingId === account.id && deleteMutation.isPending}
                  isSyncing={syncingBankId === account.id} />
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              {/* 증권계좌 요약 */}
              {(() => {
                const totalDeposit = allTx.filter((t) => t.transaction_type === "DEPOSIT").reduce((s, t) => s + t.amount, 0);
                const totalDividend = allTx.filter((t) => t.transaction_type === "DIVIDEND").reduce((s, t) => s + t.amount, 0);
                const pnl = overview?.unrealized_pnl_krw ?? 0;
                const ret = overview?.stock_return_pct ?? 0;
                const pnlColor = pnl >= 0 ? "text-red-500" : "text-blue-500";
                const retColor = ret >= 0 ? "text-red-500" : "text-blue-500";
                return (
                  <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
                    <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-3">증권계좌 전체 요약</p>
                    <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
                      <div>
                        <p className="text-xs text-gray-400 dark:text-gray-500">평가금액</p>
                        <p className="text-sm font-semibold text-gray-900 dark:text-gray-50 mt-0.5">{fmtKrw(overview?.total_stock_krw ?? 0)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400 dark:text-gray-500">평가손익</p>
                        <p className={`text-sm font-semibold mt-0.5 ${pnlColor}`}>
                          {pnl >= 0 ? "+" : ""}{fmtKrw(pnl)}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400 dark:text-gray-500">수익률</p>
                        <p className={`text-sm font-semibold mt-0.5 ${retColor}`}>
                          {ret >= 0 ? "+" : ""}{ret.toFixed(2)}%
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400 dark:text-gray-500">누적 입금</p>
                        <p className="text-sm font-semibold text-blue-600 dark:text-blue-400 mt-0.5">{fmtKrw(totalDeposit)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400 dark:text-gray-500">누적 배당</p>
                        <p className="text-sm font-semibold text-green-600 dark:text-green-400 mt-0.5">{fmtKrw(totalDividend)}</p>
                      </div>
                    </div>
                  </div>
                );
              })()}
              {(() => {
                const portfolioAccMap = Object.fromEntries(
                  (overview?.accounts ?? []).map((a) => [a.id, a])
                );
                const txByAcc: Record<string, { deposit: number; dividend: number }> = {};
                for (const t of allTx) {
                  if (!t.account_id) continue;
                  if (!txByAcc[t.account_id]) txByAcc[t.account_id] = { deposit: 0, dividend: 0 };
                  if (t.transaction_type === "DEPOSIT") txByAcc[t.account_id].deposit += t.amount;
                  if (t.transaction_type === "DIVIDEND") txByAcc[t.account_id].dividend += t.amount;
                }
                return stockAccounts.map((account) => {
                  const pa = portfolioAccMap[account.id];
                  const tx = txByAcc[account.id] ?? { deposit: 0, dividend: 0 };
                  const stats: AccountStats = {
                    amount_krw: pa?.amount_krw ?? 0,
                    invested_krw: pa?.invested_krw ?? 0,
                    unrealized_pnl: pa?.unrealized_pnl ?? 0,
                    deposit_total: tx.deposit,
                    dividend_total: tx.dividend,
                  };
                  return (
                    <StockAccountCard key={account.id} account={account} stats={stats}
                      onDelete={handleDelete}
                      onManagePositions={setPositionsAccount}
                      onTransactions={(a) => setTxAccount({ ...a, depositKrw: account.deposit_krw ?? 0 })}
                      onEditDeposit={handleEditDeposit}
                      onEditName={handleEditName}
                      onSync={handleSyncKisAccount}
                      isSyncing={syncingStockIds.has(account.id)}
                      isDeleting={deletingId === account.id && deleteMutation.isPending} />
                  );
                });
              })()}
            </div>
          )}
        </>
      )}

      {/* Modals */}
      {showBankModal && (
        <BankAccountModal onClose={() => setShowBankModal(false)}
          onSubmit={(data) => createMutation.mutate(data)}
          isLoading={createMutation.isPending} />
      )}
      {showStockModal && (
        <StockAccountModal onClose={() => setShowStockModal(false)}
          onSubmit={(data) => createMutation.mutate(data)}
          isLoading={createMutation.isPending} />
      )}
      {showRealEstateModal && (
        <RealEstateAccountModal onClose={() => setShowRealEstateModal(false)}
          onSubmit={(data) => createMutation.mutate(data)}
          isLoading={createMutation.isPending} />
      )}
      {editingRealEstate && (
        <RealEstateEditModal
          account={editingRealEstate}
          onClose={() => setEditingRealEstate(null)}
          onSubmit={(id, data) => updateRealEstateMutation.mutate({ id, data })}
          isLoading={updateRealEstateMutation.isPending} />
      )}
      {positionsAccount && (
        <StockPositionsModal
          accountId={positionsAccount.id}
          accountName={positionsAccount.name}
          readonly={["KIS_API", "LS_SEC"].includes(positionsAccount.dataSource)}
          onClose={() => {
            setPositionsAccount(null);
            queryClient.invalidateQueries({ queryKey: ["portfolio-overview"] });
          }}
        />
      )}
      {txAccount && (
        <TransactionModal accountId={txAccount.id} accountName={txAccount.name}
          depositKrw={txAccount.depositKrw}
          onDepositUpdate={(newDeposit) => updateDepositMutation.mutate({ id: txAccount.id, deposit_krw: newDeposit })}
          onClose={() => {
            setTxAccount(null);
            queryClient.invalidateQueries({ queryKey: ["portfolio-overview"] });
            queryClient.invalidateQueries({ queryKey: ["dashboard"] });
          }} />
      )}
    </div>
  );
}
