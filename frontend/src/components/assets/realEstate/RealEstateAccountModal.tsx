import { useState } from "react";
import type { AssetAccountCreate, RealEstateDetails } from "@/api/assets";
import Modal from "@/components/common/Modal";
import { fmtKrw, fmtKrwPreview } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { FORM_LABEL, INPUT_SM } from "@/constants/inputStyles";
import { REAL_ESTATE_ASSET_TYPE } from "@/constants/assets";
import { PROPERTY_TYPE_OPTIONS } from "./constants";

interface CreateModalProps {
  onClose: () => void;
  onSubmit: (data: AssetAccountCreate) => void;
  isLoading: boolean;
}

export function RealEstateAccountModal({ onClose, onSubmit, isLoading }: CreateModalProps) {
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
      asset_type: REAL_ESTATE_ASSET_TYPE,
      data_source: "MANUAL",
      manual_amount: marketValue || undefined,
      real_estate_details: details,
      include_in_total: form.include_in_total,
    });
  };

  const inputCls = `w-full ${INPUT_SM}`;

  return (
    <Modal onClose={onClose} title="부동산 추가" size="md" closeOnBackdrop>
      <div className="overflow-y-auto flex-1 px-6 py-5">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="re-create-name" className={FORM_LABEL}>
              부동산 이름 *
            </label>
            <input
              id="re-create-name"
              type="text"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="예: 강남 아파트"
              className={inputCls}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="re-create-type" className={FORM_LABEL}>
                종류
              </label>
              <select
                id="re-create-type"
                value={form.property_type}
                onChange={(e) => setForm({ ...form, property_type: e.target.value })}
                className={inputCls}
              >
                {PROPERTY_TYPE_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="re-create-purchase-date" className={FORM_LABEL}>
                매입일
              </label>
              <input
                id="re-create-purchase-date"
                type="date"
                value={form.purchase_date}
                onChange={(e) => setForm({ ...form, purchase_date: e.target.value })}
                className={inputCls}
              />
            </div>
          </div>
          <div>
            <label htmlFor="re-create-address" className={FORM_LABEL}>
              주소
            </label>
            <input
              id="re-create-address"
              type="text"
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
              placeholder="예: 서울시 강남구 ..."
              className={inputCls}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="re-create-market-value" className={FORM_LABEL}>
                현재 시세 (원) *
              </label>
              <input
                id="re-create-market-value"
                type="number"
                inputMode="decimal"
                required
                min={0}
                value={form.market_value}
                onChange={(e) => setForm({ ...form, market_value: e.target.value })}
                placeholder="예: 800000000"
                className={inputCls}
              />
              {marketValue > 0 && (
                <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mt-1">
                  {fmtKrwPreview(marketValue)}
                </p>
              )}
            </div>
            <div>
              <label htmlFor="re-create-purchase-price" className={FORM_LABEL}>
                매입가 (원)
              </label>
              <input
                id="re-create-purchase-price"
                type="number"
                inputMode="decimal"
                min={0}
                value={form.purchase_price}
                onChange={(e) => setForm({ ...form, purchase_price: e.target.value })}
                placeholder="예: 600000000"
                className={inputCls}
              />
              {form.purchase_price && (
                <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mt-1">
                  {fmtKrwPreview(Number(form.purchase_price))}
                </p>
              )}
            </div>
          </div>
          <div>
            <label htmlFor="re-create-mortgage" className={FORM_LABEL}>
              담보대출 잔액 (원)
            </label>
            <input
              id="re-create-mortgage"
              type="number"
              inputMode="decimal"
              min={0}
              value={form.mortgage_balance}
              onChange={(e) => setForm({ ...form, mortgage_balance: e.target.value })}
              placeholder="0"
              className={inputCls}
            />
            {mortgage > 0 && (
              <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mt-1">
                {fmtKrwPreview(mortgage)}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="include-in-total-create"
              checked={form.include_in_total}
              onChange={(e) => setForm({ ...form, include_in_total: e.target.checked })}
              className="w-4 h-4 text-blue-600"
            />
            <label
              htmlFor="include-in-total-create"
              className="text-sm text-gray-700 dark:text-gray-300"
            >
              전체 자산에 포함
            </label>
          </div>
          {marketValue > 0 && (
            <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 text-sm space-y-1">
              <div className="flex justify-between text-gray-500 dark:text-gray-400">
                <span>시세</span>
                <span>{fmtKrw(marketValue)}</span>
              </div>
              {mortgage > 0 && (
                <div className="flex justify-between text-gray-500 dark:text-gray-400">
                  <span>담보대출</span>
                  <span className="text-blue-500">−{fmtKrw(mortgage)}</span>
                </div>
              )}
              <div className="flex justify-between font-semibold text-gray-900 dark:text-gray-50 border-t border-gray-200 dark:border-gray-700 pt-1">
                <span>순자산</span>
                <span className={pnlColor(equity)}>{fmtKrw(equity)}</span>
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {isLoading ? "저장 중..." : "추가"}
            </button>
          </div>
        </form>
      </div>
    </Modal>
  );
}
