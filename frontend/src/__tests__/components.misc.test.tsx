import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import ConfirmModal from "@/components/common/ConfirmModal";
import FormInput from "@/components/common/FormInput";
import Modal from "@/components/common/Modal";
import SkeletonCard from "@/components/common/SkeletonCard";
import SkeletonStatBox from "@/components/common/SkeletonStatBox";
import Button from "@/components/common/Button";

vi.mock("@/hooks/useHaptic", () => ({
  triggerHaptic: vi.fn().mockResolvedValue(undefined),
}));

describe("ConfirmModal", () => {
  it("메시지와 버튼을 렌더링한다", () => {
    renderWithProviders(
      <ConfirmModal
        message="정말 삭제하시겠습니까?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByText("정말 삭제하시겠습니까?")).toBeInTheDocument();
    expect(screen.getByText("확인")).toBeInTheDocument();
    expect(screen.getByText("취소")).toBeInTheDocument();
  });

  it("confirmLabel/cancelLabel을 커스터마이즈할 수 있다", () => {
    renderWithProviders(
      <ConfirmModal
        message="메시지"
        confirmLabel="삭제"
        cancelLabel="아니오"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByText("삭제")).toBeInTheDocument();
    expect(screen.getByText("아니오")).toBeInTheDocument();
  });

  it("확인 버튼 클릭 시 onConfirm을 호출한다", () => {
    const onConfirm = vi.fn();
    renderWithProviders(
      <ConfirmModal message="메시지" onConfirm={onConfirm} onCancel={vi.fn()} />
    );
    fireEvent.click(screen.getByText("확인"));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("취소 버튼 클릭 시 onCancel을 호출한다", () => {
    const onCancel = vi.fn();
    renderWithProviders(
      <ConfirmModal message="메시지" onConfirm={vi.fn()} onCancel={onCancel} />
    );
    fireEvent.click(screen.getByText("취소"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("배경 클릭 시 onCancel을 호출한다", () => {
    const onCancel = vi.fn();
    const { container } = renderWithProviders(
      <ConfirmModal message="메시지" onConfirm={vi.fn()} onCancel={onCancel} />
    );
    fireEvent.click(container.firstChild as Element);
    expect(onCancel).toHaveBeenCalled();
  });
});

describe("FormInput", () => {
  it("레이블과 입력 필드를 렌더링한다", () => {
    renderWithProviders(<FormInput label="이메일" />);
    expect(screen.getByLabelText("이메일")).toBeInTheDocument();
  });

  it("required이면 레이블에 * 표시가 붙는다", () => {
    renderWithProviders(<FormInput label="이메일" required />);
    expect(screen.getByText("*")).toBeInTheDocument();
  });

  it("error가 있으면 에러 메시지를 표시한다", () => {
    renderWithProviders(<FormInput label="이메일" error="올바른 이메일을 입력하세요" />);
    expect(screen.getByText("올바른 이메일을 입력하세요")).toBeInTheDocument();
  });

  it("hint가 있으면 힌트 텍스트를 표시한다", () => {
    renderWithProviders(<FormInput label="비밀번호" hint="8자 이상 입력하세요" />);
    expect(screen.getByText("8자 이상 입력하세요")).toBeInTheDocument();
  });

  it("error가 있으면 hint를 숨긴다", () => {
    renderWithProviders(
      <FormInput label="비밀번호" hint="힌트" error="에러" />
    );
    expect(screen.queryByText("힌트")).toBeNull();
    expect(screen.getByText("에러")).toBeInTheDocument();
  });
});

describe("Modal", () => {
  it("title이 있으면 헤더를 렌더링한다", () => {
    renderWithProviders(
      <Modal title="모달 제목" onClose={vi.fn()}>
        <div>콘텐츠</div>
      </Modal>
    );
    expect(screen.getByText("모달 제목")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("닫기 버튼 클릭 시 onClose를 호출한다", () => {
    const onClose = vi.fn();
    renderWithProviders(
      <Modal title="제목" onClose={onClose}>
        <div>내용</div>
      </Modal>
    );
    fireEvent.click(screen.getByLabelText("닫기"));
    expect(onClose).toHaveBeenCalled();
  });

  it("closeOnBackdrop=true이면 배경 클릭 시 onClose를 호출한다", () => {
    const onClose = vi.fn();
    const { container } = renderWithProviders(
      <Modal title="제목" onClose={onClose} closeOnBackdrop>
        <div>내용</div>
      </Modal>
    );
    fireEvent.click(container.firstChild as Element);
    expect(onClose).toHaveBeenCalled();
  });

  it("title 없이도 콘텐츠를 렌더링한다", () => {
    renderWithProviders(
      <Modal onClose={vi.fn()}>
        <div>콘텐츠만</div>
      </Modal>
    );
    expect(screen.getByText("콘텐츠만")).toBeInTheDocument();
    expect(screen.queryByLabelText("닫기")).toBeNull();
  });

  it("Escape 키 입력 시 onClose를 호출한다", () => {
    const onClose = vi.fn();
    renderWithProviders(
      <Modal title="제목" onClose={onClose}>
        <button>포커스 대상</button>
      </Modal>
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

describe("SkeletonCard", () => {
  it("기본 3개의 스켈레톤 행을 렌더링한다", () => {
    const { container } = renderWithProviders(<SkeletonCard />);
    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons).toHaveLength(3);
  });

  it("rows 수에 맞게 렌더링한다", () => {
    const { container } = renderWithProviders(<SkeletonCard rows={5} />);
    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons).toHaveLength(5);
  });
});

describe("SkeletonStatBox", () => {
  it("두 개의 스켈레톤 블록을 렌더링한다", () => {
    const { container } = renderWithProviders(<SkeletonStatBox />);
    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons).toHaveLength(2);
  });
});

describe("Button", () => {
  it("children을 렌더링한다", () => {
    renderWithProviders(<Button>클릭</Button>);
    expect(screen.getByText("클릭")).toBeInTheDocument();
  });

  it("loading=true이면 버튼이 비활성화된다", () => {
    renderWithProviders(<Button loading>로딩 중</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("danger variant이면 적절한 클래스가 적용된다", () => {
    renderWithProviders(<Button variant="danger">삭제</Button>);
    expect(screen.getByRole("button").className).toContain("text-red-600");
  });

  it("클릭 핸들러를 호출한다", () => {
    const onClick = vi.fn();
    renderWithProviders(<Button onClick={onClick}>버튼</Button>);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalled();
  });
});
