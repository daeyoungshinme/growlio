import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import InfoTip from "@/components/common/InfoTip";
import Modal from "@/components/common/Modal";

describe("InfoTip", () => {
  it("탭하기 전엔 설명이 없고, 탭하면 열린다", () => {
    render(<InfoTip label="MDD 설명" content="고점 대비 최대 하락폭" />);
    expect(screen.queryByRole("tooltip")).toBeNull();

    const btn = screen.getByRole("button", { name: "MDD 설명" });
    fireEvent.click(btn);
    expect(screen.getByRole("tooltip")).toHaveTextContent("고점 대비 최대 하락폭");
    expect(btn).toHaveAttribute("aria-expanded", "true");
  });

  it("다시 탭하면 닫힌다", () => {
    render(<InfoTip label="설명" content="내용" />);
    const btn = screen.getByRole("button", { name: "설명" });
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("바깥을 탭하면 닫힌다", () => {
    render(
      <div>
        <InfoTip label="설명" content="내용" />
        <p>바깥</p>
      </div>,
    );
    fireEvent.click(screen.getByRole("button", { name: "설명" }));
    fireEvent.pointerDown(screen.getByText("바깥"));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("팝오버 안을 탭해도 닫히지 않는다", () => {
    render(<InfoTip label="설명" content="내용" />);
    fireEvent.click(screen.getByRole("button", { name: "설명" }));
    fireEvent.pointerDown(screen.getByRole("tooltip"));
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
  });

  it("텍스트 children을 트리거로 쓸 수 있다", () => {
    render(
      <InfoTip label="CAGR 설명" content="연평균 수익률">
        CAGR
      </InfoTip>,
    );
    fireEvent.click(screen.getByRole("button", { name: "CAGR" }));
    expect(screen.getByRole("tooltip")).toHaveTextContent("연평균 수익률");
  });

  it("모달 안에서 Esc는 팝오버만 닫고 모달은 닫지 않는다", () => {
    const onClose = vi.fn();
    render(
      <Modal onClose={onClose} title="모달">
        <InfoTip label="설명" content="내용" />
      </Modal>,
    );
    fireEvent.click(screen.getByRole("button", { name: "설명" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
    expect(onClose).not.toHaveBeenCalled();

    // 팝오버가 닫힌 뒤의 Esc는 모달로 간다
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
    document.body.style.overflow = "";
  });
});
