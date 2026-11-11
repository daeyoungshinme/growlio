import { useId, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Modal, { ModalBody, ModalFooter } from "@/components/common/Modal";
import { createFxExtraNeed, updateFxExtraNeed, type FxExtraNeed } from "@/api/invest";
import { fxExtraNeedSchema } from "@/schemas/fxExtraNeed";
import { FORM_LABEL, INPUT_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { invalidateFxExtraNeedData } from "@/utils/queryInvalidation";
import { localToday } from "@/utils/format";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

interface Props {
  /** null = 새 항목 */
  need: FxExtraNeed | null;
  onClose: () => void;
}

const toNumber = (v: string) => (v.trim() === "" ? undefined : Number(v.replace(/,/g, "")));

/** 추가 환전 항목(여행 등) 추가·수정 — plans/123 */
export default function FxExtraNeedModal({ need, onClose }: Props) {
  const formId = useId();
  const qc = useQueryClient();
  const [name, setName] = useState(need?.name ?? "");
  const [amount, setAmount] = useState(need ? String(need.amount_usd) : "");
  const [exchanged, setExchanged] = useState(
    need && need.exchanged_usd > 0 ? String(need.exchanged_usd) : "",
  );
  const [dueDate, setDueDate] = useState(need?.due_date ?? "");
  const [error, setError] = useState<string | null>(null);
  const today = localToday();

  const mutation = useMutation({
    mutationFn: (data: {
      name: string;
      amount_usd: number;
      exchanged_usd: number;
      due_date: string;
    }) => (need ? updateFxExtraNeed(need.id, data) : createFxExtraNeed(data)),
    onSuccess: () => {
      void invalidateFxExtraNeedData(qc);
      toast(need ? "추가 환전 항목을 고쳤습니다" : "추가 환전 항목을 만들었습니다", "success");
      onClose();
    },
    onError: (e) => setError(extractErrorMessage(e, "저장에 실패했습니다")),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const parsed = fxExtraNeedSchema.safeParse({
      name,
      amount_usd: toNumber(amount),
      exchanged_usd: toNumber(exchanged) ?? 0,
      due_date: dueDate,
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "입력값을 확인해주세요");
      return;
    }
    // 이미 지난 항목은 필요일을 그대로 두면 서버가 받아 준다 — 새로 고른 날짜만 오늘 이후여야 한다
    if (parsed.data.due_date < today && parsed.data.due_date !== need?.due_date) {
      setError("필요일은 오늘 이후여야 합니다");
      return;
    }
    mutation.mutate(parsed.data);
  };

  return (
    <Modal title={need ? "추가 환전 수정" : "추가 환전 등록"} onClose={onClose} size="sm">
      <ModalBody>
        <form id={formId} onSubmit={handleSubmit} className="space-y-4">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            여행·해외 결제처럼 날짜가 정해진 달러를 적립 계획과 따로 나눠 바꾸도록 구간을
            제안합니다. 증권 계좌 달러로는 빼지 않습니다.
          </p>
          <div>
            <label htmlFor="fx-need-name" className={FORM_LABEL}>
              이름
            </label>
            <input
              id="fx-need-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={40}
              placeholder="예: 도쿄 여행"
              className={`${INPUT_SM} w-full`}
            />
          </div>
          <div>
            <label htmlFor="fx-need-amount" className={FORM_LABEL}>
              필요한 금액 (USD)
            </label>
            <input
              id="fx-need-amount"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              inputMode="decimal"
              placeholder="1000"
              className={`${INPUT_SM} w-full`}
            />
          </div>
          <div>
            <label htmlFor="fx-need-due" className={FORM_LABEL}>
              필요일
            </label>
            <input
              id="fx-need-due"
              type="date"
              value={dueDate}
              min={need && need.due_date < today ? need.due_date : today}
              onChange={(e) => setDueDate(e.target.value)}
              className={`${INPUT_SM} w-full`}
            />
          </div>
          <div>
            <label htmlFor="fx-need-exchanged" className={FORM_LABEL}>
              이미 환전한 금액 (USD, 선택)
            </label>
            <input
              id="fx-need-exchanged"
              value={exchanged}
              onChange={(e) => setExchanged(e.target.value)}
              inputMode="decimal"
              placeholder="0"
              className={`${INPUT_SM} w-full`}
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {error}
            </p>
          )}
        </form>
      </ModalBody>
      <ModalFooter>
        <button
          type="button"
          onClick={onClose}
          className={`${TOUCH_TARGET_MIN} flex-1 px-5 py-2 rounded-lg text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300`}
        >
          취소
        </button>
        <button
          type="submit"
          form={formId}
          disabled={mutation.isPending}
          className={`${TOUCH_TARGET_MIN} flex-1 bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
        >
          {mutation.isPending ? "저장 중..." : "저장"}
        </button>
      </ModalFooter>
    </Modal>
  );
}
