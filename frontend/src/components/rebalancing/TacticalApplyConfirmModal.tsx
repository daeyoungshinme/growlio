import type { TacticalStatus } from "@/api/tactical";
import Modal, { ModalFooter } from "@/components/common/Modal";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { formatTacticalWeights, REGIME_LABEL, TACTICAL_ASSET_LIST_TEXT } from "./tacticalLabels";

/** 제안 비중 적용 확인창 — "절반 먼저 적용"(0.5) / "한 번에 적용"(1), 절반 적용 중이면 "나머지 적용" 하나 */
export default function TacticalApplyConfirmModal({
  status,
  partialActive,
  autoExecutionNotice,
  pending,
  onClose,
  onApply,
}: {
  status: TacticalStatus & { proposed_weights: NonNullable<TacticalStatus["proposed_weights"]> };
  partialActive: boolean;
  autoExecutionNotice: string | null;
  pending: boolean;
  onClose: () => void;
  onApply: (fraction: number) => void;
}) {
  return (
    <Modal title={partialActive ? "나머지 적용" : "제안 비중 적용"} size="sm" onClose={onClose}>
      <div className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-2 text-sm text-gray-700 dark:text-gray-200">
        <p>
          &ldquo;{status.portfolio_name}&rdquo; 목표 비중을{" "}
          {REGIME_LABEL[status.confirmed_regime ?? "NEUTRAL"]} 국면 비중(
          {formatTacticalWeights(status.proposed_weights)})으로 {partialActive ? "마저 " : ""}
          바꿀까요?
        </p>
        <p className="text-gray-500 dark:text-gray-400">
          {autoExecutionNotice ??
            "주문은 나가지 않으며, 다음 화면에서 매매 내역을 확인한 뒤 직접 실행해요."}
          {" 지수 그룹의 대표·합산 종목 구성은 그대로 두고 비중만 바꿔요."}
          {!status.portfolio_compatible &&
            ` ${TACTICAL_ASSET_LIST_TEXT} 외 종목은 목표에서 빠집니다.`}
        </p>
        {status.portfolio_compatible && !partialActive && (
          <p className="text-gray-500 dark:text-gray-400">
            국면이 막 바뀐 직후라면 절반만 먼저 적용하고 다음 거래일에 나머지를 적용해 매수·매도
            타이밍을 나눌 수 있어요.
          </p>
        )}
      </div>
      <ModalFooter>
        {status.portfolio_compatible && !partialActive && (
          <button
            type="button"
            className={`${TOUCH_TARGET_MIN} flex-1 px-4 rounded-lg text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 disabled:opacity-50`}
            disabled={pending}
            onClick={() => onApply(0.5)}
          >
            절반 먼저 적용
          </button>
        )}
        <button
          type="button"
          className={`${TOUCH_TARGET_MIN} flex-1 bg-blue-600 text-white px-4 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
          disabled={pending}
          onClick={() => onApply(1)}
        >
          {partialActive ? "나머지 적용" : "한 번에 적용"}
        </button>
      </ModalFooter>
    </Modal>
  );
}
