import { Link } from "react-router-dom";
import { TOUCH_TARGET_ROW } from "@/constants/uiSizes";

/** 자동 실행 가능한(KIS·키움) 계좌가 없을 때 — 안내문만 두면 막다른 길이라 계좌 연결 화면 링크를 함께 준다. */
export default function NoTradableAccountNotice() {
  return (
    <div className="text-xs text-amber-600 dark:text-amber-400">
      <p>자동 실행할 수 있는 KIS·키움 연동 계좌가 없습니다. 토스 계좌는 조회 전용이에요.</p>
      <Link
        to="/assets?tab=계좌관리&atab=증권계좌"
        className={`${TOUCH_TARGET_ROW} font-medium text-blue-600 dark:text-blue-400 hover:underline`}
      >
        증권계좌 연결하기 →
      </Link>
    </div>
  );
}
