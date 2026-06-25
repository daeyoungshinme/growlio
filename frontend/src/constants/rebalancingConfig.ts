import type { MarketConditionMode, ScheduleType, TriggerCondition } from "@/api/alerts";

export const SCHEDULE_OPTIONS: { value: ScheduleType; label: string }[] = [
  { value: "DAILY", label: "매일" },
  { value: "WEEKLY", label: "매주" },
  { value: "MONTHLY", label: "매월" },
  { value: "QUARTERLY", label: "3개월" },
  { value: "SEMIANNUAL", label: "6개월" },
  { value: "ANNUAL", label: "1년" },
];

export const DAYS_KO = ["월", "화", "수", "목", "금", "토", "일"] as const;

export const SCHEDULE_LABEL: Record<ScheduleType, string> = {
  DAILY: "매일",
  WEEKLY: "매주",
  MONTHLY: "매월",
  QUARTERLY: "매 3개월",
  SEMIANNUAL: "매 6개월",
  ANNUAL: "매년",
};

export const NEEDS_DAY_OF_MONTH: ScheduleType[] = ["MONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL"];

export const TRIGGER_CONDITION_SHORT_LABEL: Record<TriggerCondition, string> = {
  DRIFT_ONLY: "이탈 감지",
  SCHEDULE_ONLY: "정기 리포트",
  BOTH: "이탈+정기",
};

export const TRIGGER_CONDITION_OPTIONS: { value: TriggerCondition; label: string; desc: string }[] =
  [
    { value: "DRIFT_ONLY", label: "비중 이탈 시에만", desc: "이탈 종목이 있을 때만 동작합니다" },
    {
      value: "SCHEDULE_ONLY",
      label: "주기마다 항상",
      desc: "주기마다 무조건 리포트를 받습니다",
    },
    {
      value: "BOTH",
      label: "주기마다 + 비중 이탈 시",
      desc: "정기 리포트 + 이탈 즉시 알림",
    },
  ];

export const MODE_OPTIONS: { value: "NOTIFY" | "AUTO"; label: string; desc: string }[] = [
  { value: "NOTIFY", label: "알림만 (권장)", desc: "이메일로 알림 수신" },
  { value: "AUTO", label: "자동 실행", desc: "조건 충족 시 주문 자동 실행" },
];

export const STRATEGY_OPTIONS: { value: "BUY_ONLY" | "FULL"; label: string; desc: string }[] = [
  { value: "BUY_ONLY", label: "매수만 (권장)", desc: "세금 절감" },
  { value: "FULL", label: "매도+매수", desc: "완전 리밸런싱" },
];

export const MARKET_CONDITION_OPTIONS: {
  value: MarketConditionMode;
  label: string;
  desc: string;
}[] = [
  { value: "DISABLED", label: "신호 무시", desc: "시장 상황과 무관하게 자동 실행" },
  { value: "CAUTIOUS", label: "신중", desc: "고위험(RED) 신호 시 자동 실행 중단" },
  { value: "STRICT", label: "엄격", desc: "중위험(YELLOW) 이상에서 자동 실행 중단" },
];
