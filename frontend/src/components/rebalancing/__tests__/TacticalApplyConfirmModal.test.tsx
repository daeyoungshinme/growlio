import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import TacticalApplyConfirmModal from "../TacticalApplyConfirmModal";

type Props = Parameters<typeof TacticalApplyConfirmModal>[0];

function makeStatus(overrides: Partial<Props["status"]> = {}): Props["status"] {
  return {
    portfolio_name: "전술 포트폴리오",
    confirmed_regime: "RISK_ON",
    proposed_weights: { QQQ: 60, SPY: 40 },
    portfolio_compatible: true,
    ...overrides,
  } as Props["status"];
}

function renderModal(overrides: Partial<Props> = {}) {
  const props: Props = {
    status: makeStatus(),
    partialActive: false,
    autoExecutionNotice: null,
    pending: false,
    onClose: vi.fn(),
    onApply: vi.fn(),
    ...overrides,
  };
  render(<TacticalApplyConfirmModal {...props} />);
  return props;
}

describe("TacticalApplyConfirmModal", () => {
  it("호환 포트폴리오면 절반·전체 적용 버튼을 모두 보여주고 비율을 넘긴다", () => {
    const props = renderModal();
    fireEvent.click(screen.getByRole("button", { name: "절반 먼저 적용" }));
    fireEvent.click(screen.getByRole("button", { name: "한 번에 적용" }));
    expect(props.onApply).toHaveBeenNthCalledWith(1, 0.5);
    expect(props.onApply).toHaveBeenNthCalledWith(2, 1);
  });

  it("절반 적용 중이면 '나머지 적용' 하나만 보여준다", () => {
    const props = renderModal({ partialActive: true });
    expect(screen.queryByRole("button", { name: "절반 먼저 적용" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "나머지 적용" }));
    expect(props.onApply).toHaveBeenCalledWith(1);
  });

  it("호환되지 않는 포트폴리오면 절반 적용이 없고 빠지는 종목을 안내한다", () => {
    renderModal({ status: makeStatus({ portfolio_compatible: false }) });
    expect(screen.queryByRole("button", { name: "절반 먼저 적용" })).toBeNull();
    expect(screen.getByText(/외 종목은 목표에서 빠집니다/)).toBeTruthy();
  });

  it("자동 실행 안내가 있으면 기본 안내 대신 보여준다", () => {
    renderModal({ autoExecutionNotice: "AUTO 모드라 바로 주문이 나가요." });
    expect(screen.getByText(/AUTO 모드라 바로 주문이 나가요/)).toBeTruthy();
    expect(screen.queryByText(/주문은 나가지 않으며/)).toBeNull();
  });

  it("처리 중이면 버튼을 비활성화한다", () => {
    renderModal({ pending: true });
    const button = screen.getByRole("button", { name: "한 번에 적용" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });
});
