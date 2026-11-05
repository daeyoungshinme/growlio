import { useId, useState } from "react";
import type { RealEstateDetails } from "@/api/assets";
import Modal, { ModalBody, ModalFooter } from "@/components/common/Modal";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { fmtKrw, fmtKrwPreview } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { FORM_LABEL, INPUT_SM } from "@/constants/inputStyles";
import { PROPERTY_TYPE_OPTIONS } from "./constants";

export interface RealEstateFormValues {
  name: string;
  market_value: string;
  property_type: string;
  address: string;
  purchase_price: string;
  purchase_date: string;
  mortgage_balance: string;
  include_in_total: boolean;
}

export interface RealEstateSubmitValues {
  name: string;
  manual_amount: number | undefined;
  real_estate_details: RealEstateDetails;
  include_in_total: boolean;
}

interface Props {
  title: string;
  submitLabel: string;
  /** label·input 연결 id 접두사 — 추가·수정 모달이 같이 떠도 겹치지 않게 */
  idSuffix: "create" | "edit";
  initial: RealEstateFormValues;
  placeholders?: Partial<Record<keyof RealEstateFormValues, string>>;
  onClose: () => void;
  onSubmit: (values: RealEstateSubmitValues) => void;
  isLoading: boolean;
}

const inputCls = `w-full ${INPUT_SM}`;
const PREVIEW_CLS = "text-xs font-medium text-blue-600 dark:text-blue-400 mt-1";

export function RealEstateFormModal({
  title,
  submitLabel,
  idSuffix,
  initial,
  placeholders,
  onClose,
  onSubmit,
  isLoading,
}: Props) {
  const formId = useId();
  const [form, setForm] = useState(initial);
  const id = (field: string) => `re-${idSuffix}-${field}`;
  const includeId = `include-in-total-${idSuffix}`;

  const marketValue = Number(form.market_value) || 0;
  const mortgage = Number(form.mortgage_balance) || 0;
  const equity = marketValue - mortgage;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
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

  return (
    <Modal onClose={onClose} title={title} size="md" closeOnBackdrop>
      <ModalBody>
        <form id={formId} onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor={id("name")} className={FORM_LABEL}>
              부동산 이름 *
            </label>
            <input
              id={id("name")}
              type="text"
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder={placeholders?.name}
              className={inputCls}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor={id("type")} className={FORM_LABEL}>
                종류
              </label>
              <select
                id={id("type")}
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
              <label htmlFor={id("purchase-date")} className={FORM_LABEL}>
                매입일
              </label>
              <input
                id={id("purchase-date")}
                type="date"
                value={form.purchase_date}
                onChange={(e) => setForm({ ...form, purchase_date: e.target.value })}
                className={inputCls}
              />
            </div>
          </div>
          <div>
            <label htmlFor={id("address")} className={FORM_LABEL}>
              주소
            </label>
            <input
              id={id("address")}
              type="text"
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
              placeholder={placeholders?.address}
              className={inputCls}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor={id("market-value")} className={FORM_LABEL}>
                현재 시세 (원) *
              </label>
              <input
                id={id("market-value")}
                type="number"
                inputMode="decimal"
                required
                min={0}
                value={form.market_value}
                onChange={(e) => setForm({ ...form, market_value: e.target.value })}
                placeholder={placeholders?.market_value}
                className={inputCls}
              />
              {marketValue > 0 && <p className={PREVIEW_CLS}>{fmtKrwPreview(marketValue)}</p>}
            </div>
            <div>
              <label htmlFor={id("purchase-price")} className={FORM_LABEL}>
                매입가 (원)
              </label>
              <input
                id={id("purchase-price")}
                type="number"
                inputMode="decimal"
                min={0}
                value={form.purchase_price}
                onChange={(e) => setForm({ ...form, purchase_price: e.target.value })}
                placeholder={placeholders?.purchase_price}
                className={inputCls}
              />
              {form.purchase_price && (
                <p className={PREVIEW_CLS}>{fmtKrwPreview(Number(form.purchase_price))}</p>
              )}
            </div>
          </div>
          <div>
            <label htmlFor={id("mortgage")} className={FORM_LABEL}>
              담보대출 잔액 (원)
            </label>
            <input
              id={id("mortgage")}
              type="number"
              inputMode="decimal"
              min={0}
              value={form.mortgage_balance}
              onChange={(e) => setForm({ ...form, mortgage_balance: e.target.value })}
              placeholder={placeholders?.mortgage_balance}
              className={inputCls}
            />
            {mortgage > 0 && <p className={PREVIEW_CLS}>{fmtKrwPreview(mortgage)}</p>}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id={includeId}
              checked={form.include_in_total}
              onChange={(e) => setForm({ ...form, include_in_total: e.target.checked })}
              className="w-4 h-4 text-blue-600"
            />
            <label htmlFor={includeId} className="text-sm text-gray-700 dark:text-gray-300">
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
        </form>
      </ModalBody>
      <ModalFooter>
        <button
          type="button"
          onClick={onClose}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
        >
          취소
        </button>
        <button
          type="submit"
          form={formId}
          disabled={isLoading}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors`}
        >
          {isLoading ? "저장 중..." : submitLabel}
        </button>
      </ModalFooter>
    </Modal>
  );
}
