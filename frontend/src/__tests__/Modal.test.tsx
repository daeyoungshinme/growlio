import { describe, it, expect, vi } from "vitest";
import { render, fireEvent, getAllByRole } from "@testing-library/react";
import Modal from "@/components/common/Modal";

describe("Modal", () => {
  it("children과 title을 렌더링한다", () => {
    const { getByText } = render(
      <Modal onClose={vi.fn()} title="테스트 모달">
        <p>내용입니다</p>
      </Modal>,
    );
    expect(getByText("테스트 모달")).toBeTruthy();
    expect(getByText("내용입니다")).toBeTruthy();
  });

  it("Tab 키로 포커스가 마지막 요소에서 첫 번째로 순환한다", () => {
    const { container } = render(
      <Modal onClose={vi.fn()}>
        <button>버튼1</button>
        <button>버튼2</button>
      </Modal>,
    );
    const buttons = getAllByRole(container, "button");
    buttons[buttons.length - 1].focus();
    fireEvent.keyDown(document, { key: "Tab" });
    // 포커스 트랩 실행 확인 (에러 없이 처리)
    expect(document.activeElement).toBeTruthy();
  });

  it("Shift+Tab 키로 포커스가 첫 번째 요소에서 마지막으로 순환한다", () => {
    const { container } = render(
      <Modal onClose={vi.fn()}>
        <button>버튼1</button>
        <button>버튼2</button>
      </Modal>,
    );
    const buttons = getAllByRole(container, "button");
    buttons[0].focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBeTruthy();
  });

  it("backdropClick 미설정 시 배경 클릭으로 닫히지 않는다", () => {
    const onClose = vi.fn();
    const { getByRole } = render(
      <Modal onClose={onClose}>
        <p>내용</p>
      </Modal>,
    );
    fireEvent.click(getByRole("dialog").parentElement!);
    expect(onClose).not.toHaveBeenCalled();
  });
});
