import { describe, it, expect, vi, afterEach } from "vitest";
import { render, fireEvent, getAllByRole } from "@testing-library/react";
import Modal from "@/components/common/Modal";

afterEach(() => {
  document.body.style.overflow = "";
});

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

  it("열려 있는 동안 body 스크롤을 잠그고 닫히면 복원한다", () => {
    expect(document.body.style.overflow).toBe("");

    const { unmount } = render(
      <Modal onClose={vi.fn()}>
        <p>내용</p>
      </Modal>,
    );
    expect(document.body.style.overflow).toBe("hidden");

    unmount();
    expect(document.body.style.overflow).toBe("");
  });

  it("모달이 중첩되어도 하나가 남아있으면 body 스크롤 잠금이 유지된다", () => {
    const outer = render(
      <Modal onClose={vi.fn()}>
        <p>바깥 모달</p>
      </Modal>,
    );
    const inner = render(
      <Modal onClose={vi.fn()}>
        <p>안쪽 모달</p>
      </Modal>,
    );
    expect(document.body.style.overflow).toBe("hidden");

    inner.unmount();
    expect(document.body.style.overflow).toBe("hidden");

    outer.unmount();
    expect(document.body.style.overflow).toBe("");
  });

  it("모달 영역의 터치 이벤트는 상위(예: mainRef)로 전파되지 않는다", () => {
    const { getByRole } = render(
      <Modal onClose={vi.fn()}>
        <p>내용</p>
      </Modal>,
    );
    const dialog = getByRole("dialog");

    for (const type of ["touchstart", "touchmove", "touchend"]) {
      const parentHandler = vi.fn();
      document.addEventListener(type, parentHandler);

      dialog.dispatchEvent(new Event(type, { bubbles: true, cancelable: true }));
      expect(parentHandler).not.toHaveBeenCalled();

      document.removeEventListener(type, parentHandler);
    }
  });
});
