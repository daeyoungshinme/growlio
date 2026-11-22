import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import DividendSettingsModal from "@/components/invest/DividendSettingsModal";

describe("DividendSettingsModal", () => {
  it("Enter(폼 제출)로 저장한다", () => {
    const onSave = vi.fn();
    render(
      <DividendSettingsModal
        form={{ annual_dividend_goal: "12000000" }}
        setForm={vi.fn()}
        saving={false}
        onSave={onSave}
        onClose={vi.fn()}
      />,
    );
    fireEvent.submit(screen.getByLabelText(/목표 연간 배당금/).closest("form")!);
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("저장 중이면 다시 제출하지 않는다", () => {
    const onSave = vi.fn();
    render(
      <DividendSettingsModal
        form={{ annual_dividend_goal: "1" }}
        setForm={vi.fn()}
        saving
        onSave={onSave}
        onClose={vi.fn()}
      />,
    );
    fireEvent.submit(screen.getByLabelText(/목표 연간 배당금/).closest("form")!);
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "저장 중..." })).toBeDisabled();
  });
});
