import { useId, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Modal, { ModalBody, ModalFooter } from "@/components/common/Modal";
import SegmentedControl from "@/components/common/SegmentedControl";
import {
  upsertDipBuySettings,
  type DipBuyNotifyMode,
  type DipBuySettings,
  type DipBuySettingsInput,
} from "@/api/dipBuy";
import { dipBuySettingsSchema } from "@/schemas/dipBuy";
import { FORM_LABEL, INPUT_SM, SELECT_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { invalidateDipBuyData } from "@/utils/queryInvalidation";
import { fmtKrwPreview } from "@/utils/format";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

interface Props {
  /** null = 처음 정하기 */
  settings: DipBuySettings | null;
  onClose: () => void;
}

const NOTIFY_OPTIONS: readonly { value: DipBuyNotifyMode; label: string }[] = [
  { value: "ON_REACH", label: "구간 도달 다음 날" },
  { value: "MONTHLY_DAY", label: "매달 정한 날" },
];

const DAY_OPTIONS = Array.from({ length: 28 }, (_, i) => i + 1);

const toNumber = (v: string) => (v.trim() === "" ? undefined : Number(v.replace(/,/g, "")));

/** 낙폭 추매 여윳돈·알림 방식(사용자당 하나, 포트폴리오와 무관) — plans/148 */
export default function DipBuySettingsModal({ settings, onClose }: Props) {
  const formId = useId();
  const reserveId = useId();
  const dayId = useId();
  const qc = useQueryClient();
  const [reserve, setReserve] = useState(settings ? String(Math.round(settings.reserve_krw)) : "");
  const [mode, setMode] = useState<DipBuyNotifyMode>(settings?.notify_mode ?? "ON_REACH");
  const [day, setDay] = useState(settings?.notify_day ?? 25);
  const [isActive, setIsActive] = useState(settings?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: (data: DipBuySettingsInput) => upsertDipBuySettings(data),
    onSuccess: () => {
      void invalidateDipBuyData(qc);
      toast(settings ? "추매 여윳돈 설정을 고쳤습니다" : "추매 여윳돈을 정했습니다", "success");
      onClose();
    },
    onError: (e) => setError(extractErrorMessage(e, "저장에 실패했습니다")),
  });

  const reserveValue = toNumber(reserve);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const parsed = dipBuySettingsSchema.safeParse({
      reserve_krw: reserveValue,
      notify_mode: mode,
      notify_day: mode === "MONTHLY_DAY" ? day : null,
      is_active: isActive,
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "입력값을 확인해주세요");
      return;
    }
    saveMutation.mutate(parsed.data);
  };

  return (
    <Modal title={settings ? "추매 여윳돈 설정" : "추매 여윳돈 정하기"} onClose={onClose} size="sm">
      <ModalBody>
        <form id={formId} onSubmit={handleSubmit} className="space-y-4">
          <p className="text-xs text-gray-500 dark:text-gray-400 break-keep">
            매달 적립과 별도로 모아 둔 여윳돈이에요. 지수별 규칙이 이 돈을 나눠 쓰고, 추매했어요로
            기록하면 여기서 빠져요.
          </p>
          <div>
            <label htmlFor={reserveId} className={FORM_LABEL}>
              추매용 여윳돈 (원)
            </label>
            <input
              id={reserveId}
              value={reserve}
              onChange={(e) => setReserve(e.target.value)}
              inputMode="numeric"
              placeholder="10000000"
              className={`${INPUT_SM} w-full`}
            />
            {reserveValue != null && reserveValue > 0 && (
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {fmtKrwPreview(reserveValue)}
              </p>
            )}
          </div>
          <div>
            <p className={FORM_LABEL}>알림 시점</p>
            <SegmentedControl
              options={NOTIFY_OPTIONS}
              value={mode}
              onChange={setMode}
              ariaLabel="알림 시점"
              stretch
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 break-keep">
              {mode === "ON_REACH"
                ? "미국장 마감 종가로 새 구간에 들어가면 다음 날 아침에 한 번 알려드려요."
                : "정한 날 1~3일 전과 당일 아침에 알려드려요. 휴장일이면 다음 거래일이에요."}
            </p>
          </div>
          {mode === "MONTHLY_DAY" && (
            <div>
              <label htmlFor={dayId} className={FORM_LABEL}>
                매달 알림일
              </label>
              <select
                id={dayId}
                value={day}
                onChange={(e) => setDay(Number(e.target.value))}
                className={`${SELECT_SM} w-full`}
              >
                {DAY_OPTIONS.map((d) => (
                  <option key={d} value={d}>
                    {d}일
                  </option>
                ))}
              </select>
            </div>
          )}
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
            />
            추매 안내 받기
          </label>
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
          disabled={saveMutation.isPending}
          className={`${TOUCH_TARGET_MIN} flex-1 bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
        >
          {saveMutation.isPending ? "저장 중..." : "저장"}
        </button>
      </ModalFooter>
    </Modal>
  );
}
