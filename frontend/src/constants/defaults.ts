import { localToday } from "@/utils/format";

// 모듈 로드 시점에 고정하지 않는다 — 앱을 켜 둔 채 자정·새해를 넘기면 종료일·연도가 어제 값으로 남는다
export const backtestDefaultEndDate = () => localToday();
export const backtestDefaultStartDate = () => `${new Date().getFullYear() - 5}-01-01`;
