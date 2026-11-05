import { TOUCH_HEIGHT_MIN } from "@/constants/uiSizes";

interface Props {
  message: string;
  onRetry: () => void;
}

/** 페이지 전체 조회 실패 — 메시지와 다시 시도 버튼 */
export default function PageLoadError({ message, onRetry }: Props) {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <p className="text-sm text-red-500">{message}</p>
      <button
        onClick={onRetry}
        className={`px-4 ${TOUCH_HEIGHT_MIN} text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors`}
      >
        다시 시도
      </button>
    </div>
  );
}
