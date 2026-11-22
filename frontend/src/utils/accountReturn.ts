/** 계좌 평가액을 기록된 순입금(입금 − 출금)과 비교한 수익(plans/144 C2).
 *
 * 배당은 예수금으로 들어와 평가액에 이미 들어 있으므로 다시 더하지 않는다. 기간 수익률(XIRR)이 아니라
 * "넣은 돈 대비 지금 얼마"라서 입금 시점은 반영하지 않는다. 기록 이전 자금이 있는 계좌는 순입금이 작아
 * 수익이 부풀려 보이므로, 순입금이 0 이하면 계산하지 않는다(화면에서 숨김).
 */
export interface DepositReturn {
  netDeposit: number;
  gain: number;
  pct: number;
}

export interface DepositReturnInput {
  amountKrw: number;
  depositTotal: number;
  withdrawalTotal: number;
}

export function depositReturn({
  amountKrw,
  depositTotal,
  withdrawalTotal,
}: DepositReturnInput): DepositReturn | null {
  const netDeposit = depositTotal - withdrawalTotal;
  if (!(netDeposit > 0) || !Number.isFinite(amountKrw)) return null;
  const gain = amountKrw - netDeposit;
  return { netDeposit, gain, pct: (gain / netDeposit) * 100 };
}

/** 계산 가능한 계좌(순입금 > 0)만 모아 합계를 낸다 — 기록 없는 계좌의 평가액을 섞으면 수익이 부풀려진다. */
export function sumDepositReturn(
  items: DepositReturnInput[],
): (DepositReturn & { accountCount: number }) | null {
  let amount = 0;
  let netDeposit = 0;
  let accountCount = 0;
  for (const item of items) {
    const r = depositReturn(item);
    if (!r) continue;
    amount += item.amountKrw;
    netDeposit += r.netDeposit;
    accountCount += 1;
  }
  if (accountCount === 0) return null;
  const gain = amount - netDeposit;
  return { netDeposit, gain, pct: (gain / netDeposit) * 100, accountCount };
}
