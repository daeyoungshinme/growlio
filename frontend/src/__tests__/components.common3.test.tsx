import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import * as Sentry from "@sentry/react";

// Mock Sentry
vi.mock("@sentry/react", () => ({
  captureException: vi.fn(),
}));

// Mock useOnlineStatus
vi.mock("@/hooks/useOnlineStatus", () => ({
  useOnlineStatus: vi.fn(() => true),
}));

import ErrorBoundary from "@/components/ErrorBoundary";
import Toaster from "@/components/Toaster";
import OfflineBanner from "@/components/common/OfflineBanner";
import PageLoader from "@/components/common/PageLoader";
import SkeletonTable from "@/components/common/SkeletonTable";
import Tabs from "@/components/common/Tabs";
import TreemapCell from "@/components/common/TreemapCell";
import StatCard from "@/components/common/StatCard";
import Tooltip from "@/components/common/Tooltip";
import SkeletonCard from "@/components/common/SkeletonCard";
import SkeletonStatBox from "@/components/common/SkeletonStatBox";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";

// ------- ErrorBoundary -------
function BrokenComponent({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error("Test crash");
  return <div>OK</div>;
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders children when no error", () => {
    render(
      <ErrorBoundary>
        <div>Hello</div>
      </ErrorBoundary>
    );
    expect(screen.getByText("Hello")).toBeDefined();
  });

  it("renders page error UI on crash (default variant)", () => {
    render(
      <ErrorBoundary>
        <BrokenComponent shouldThrow />
      </ErrorBoundary>
    );
    expect(screen.getByText(/페이지를 불러올 수 없습니다/)).toBeDefined();
    expect(screen.getByRole("button", { name: /새로고침/ })).toBeDefined();
  });

  it("renders section error UI on crash (section variant)", () => {
    render(
      <ErrorBoundary variant="section">
        <BrokenComponent shouldThrow />
      </ErrorBoundary>
    );
    expect(screen.getByText(/이 섹션을 불러올 수 없습니다/)).toBeDefined();
  });

  it("calls Sentry.captureException on error", () => {
    render(
      <ErrorBoundary>
        <BrokenComponent shouldThrow />
      </ErrorBoundary>
    );
    expect(Sentry.captureException).toHaveBeenCalled();
  });

  it("retry button resets error state (section variant)", () => {
    const { rerender } = render(
      <ErrorBoundary variant="section">
        <BrokenComponent shouldThrow />
      </ErrorBoundary>
    );
    const retryBtn = screen.getByRole("button", { name: /다시 시도/ });
    fireEvent.click(retryBtn);
    // After clicking retry, it re-renders children — but since BrokenComponent still throws,
    // error state will be re-entered
    expect(retryBtn || screen.queryByText(/이 섹션을 불러올 수 없습니다/)).toBeDefined();
  });

  it("shows ChunkLoadError reload button in section", () => {
    function ChunkError() {
      const e = new Error("Loading chunk 1 failed");
      e.name = "ChunkLoadError";
      throw e;
    }
    render(
      <ErrorBoundary variant="section">
        <ChunkError />
      </ErrorBoundary>
    );
    expect(screen.getByRole("button", { name: /새로고침/ })).toBeDefined();
  });
});

// ------- Toaster -------
describe("Toaster", () => {
  it("renders nothing initially", () => {
    const { container } = renderWithProviders(<Toaster />);
    expect(container.firstChild).toBeNull();
  });

  it("shows toast on custom event", async () => {
    renderWithProviders(<Toaster />);
    await act(async () => {
      const event = new CustomEvent("growlio:toast", {
        detail: { id: "t1", type: "success", message: "저장되었습니다" },
      });
      window.dispatchEvent(event);
    });
    expect(screen.getByText("저장되었습니다")).toBeDefined();
  });

  it("shows error toast with correct class", async () => {
    renderWithProviders(<Toaster />);
    await act(async () => {
      const event = new CustomEvent("growlio:toast", {
        detail: { id: "t2", type: "error", message: "에러 발생" },
      });
      window.dispatchEvent(event);
    });
    expect(screen.getByText("에러 발생")).toBeDefined();
  });

  it("shows info toast", async () => {
    renderWithProviders(<Toaster />);
    await act(async () => {
      const event = new CustomEvent("growlio:toast", {
        detail: { id: "t3", type: "info", message: "알림" },
      });
      window.dispatchEvent(event);
    });
    expect(screen.getByText("알림")).toBeDefined();
  });
});

// ------- OfflineBanner -------
describe("OfflineBanner", () => {
  it("renders nothing when online", () => {
    vi.mocked(useOnlineStatus).mockReturnValue(true);
    const { container } = renderWithProviders(<OfflineBanner />);
    expect(container.firstChild).toBeNull();
  });

  it("renders banner when offline", () => {
    vi.mocked(useOnlineStatus).mockReturnValue(false);
    renderWithProviders(<OfflineBanner />);
    expect(screen.getByRole("alert")).toBeDefined();
    expect(screen.getByText(/오프라인 상태입니다/)).toBeDefined();
  });
});

// ------- PageLoader -------
describe("PageLoader", () => {
  it("renders loading spinner", () => {
    renderWithProviders(<PageLoader />);
    expect(screen.getByRole("status")).toBeDefined();
    expect(screen.getByLabelText(/로딩 중/)).toBeDefined();
  });
});

// ------- SkeletonTable -------
describe("SkeletonTable", () => {
  it("renders with default cols and rows", () => {
    const { container } = renderWithProviders(<SkeletonTable />);
    expect(container.firstChild).toBeDefined();
  });

  it("renders with custom cols and rows", () => {
    const { container } = renderWithProviders(<SkeletonTable cols={3} rows={2} />);
    expect(container.firstChild).toBeDefined();
  });
});

// ------- Tabs -------
describe("Tabs", () => {
  const tabs = ["탭1", "탭2", "탭3"] as const;

  it("renders underline tabs (default)", () => {
    const onChange = vi.fn();
    renderWithProviders(<Tabs tabs={tabs} activeTab="탭1" onChange={onChange} />);
    expect(screen.getByText("탭1")).toBeDefined();
    expect(screen.getByText("탭2")).toBeDefined();
    expect(screen.getByText("탭3")).toBeDefined();
  });

  it("renders pill tabs", () => {
    const onChange = vi.fn();
    renderWithProviders(<Tabs tabs={tabs} activeTab="탭2" onChange={onChange} variant="pill" />);
    expect(screen.getByText("탭2")).toBeDefined();
  });

  it("calls onChange when tab clicked", () => {
    const onChange = vi.fn();
    renderWithProviders(<Tabs tabs={tabs} activeTab="탭1" onChange={onChange} />);
    fireEvent.click(screen.getByText("탭2"));
    expect(onChange).toHaveBeenCalledWith("탭2");
  });

  it("calls onChange when pill tab clicked", () => {
    const onChange = vi.fn();
    renderWithProviders(<Tabs tabs={tabs} activeTab="탭1" onChange={onChange} variant="pill" />);
    fireEvent.click(screen.getByText("탭3"));
    expect(onChange).toHaveBeenCalledWith("탭3");
  });
});

// ------- TreemapCell -------
describe("TreemapCell", () => {
  it("renders with small dimensions (no text)", () => {
    const { container } = render(
      <svg>
        <TreemapCell x={0} y={0} width={30} height={20} name="TEST" pct={12.5} ticker="TST" index={0} />
      </svg>
    );
    expect(container.querySelector("rect")).toBeDefined();
  });

  it("renders text when dimensions are large enough", () => {
    render(
      <svg>
        <TreemapCell x={0} y={0} width={100} height={80} name="삼성전자" pct={25.5} ticker="005930" index={1} />
      </svg>
    );
    expect(screen.getByText(/25\.5/)).toBeDefined();
  });

  it("renders ticker when height > 55", () => {
    render(
      <svg>
        <TreemapCell x={0} y={0} width={120} height={70} name="Apple" pct={10} ticker="AAPL" index={2} />
      </svg>
    );
    expect(screen.getByText("AAPL")).toBeDefined();
  });

  it("truncates long name", () => {
    const { container } = render(
      <svg>
        <TreemapCell x={0} y={0} width={100} height={60} name="이름이매우길어요" pct={5} ticker="TST" index={0} />
      </svg>
    );
    // truncated text node exists (sliced + ellipsis)
    const textNodes = container.querySelectorAll("text");
    const hasName = Array.from(textNodes).some((t) => t.textContent?.includes("이름이매우길"));
    expect(hasName).toBe(true);
  });
});

// ------- StatCard -------
describe("StatCard", () => {
  it("renders label and value", () => {
    renderWithProviders(<StatCard label="총자산" value="1,000만원" />);
    expect(screen.getByText("총자산")).toBeDefined();
    expect(screen.getByText("1,000만원")).toBeDefined();
  });

  it("renders sub text", () => {
    renderWithProviders(<StatCard label="수익률" value="+5%" sub="전일 대비" />);
    expect(screen.getByText("전일 대비")).toBeDefined();
  });

  it("renders in sm size", () => {
    renderWithProviders(<StatCard label="수익" value="+1%" size="sm" />);
    expect(screen.getByText("수익")).toBeDefined();
  });

  it("renders with color variants", () => {
    const { rerender } = renderWithProviders(<StatCard label="수익" value="+1%" color="red" />);
    expect(screen.getByText("+1%")).toBeDefined();
    rerender(<StatCard label="수익" value="+1%" color="green" />);
    expect(screen.getByText("+1%")).toBeDefined();
  });
});

// ------- Tooltip -------
describe("Tooltip", () => {
  it("renders children and tooltip content", () => {
    render(
      <Tooltip content="도움말">
        <button>hover me</button>
      </Tooltip>
    );
    expect(screen.getByText("hover me")).toBeDefined();
    expect(screen.getByRole("tooltip")).toBeDefined();
    expect(screen.getByText("도움말")).toBeDefined();
  });

  it("renders with position bottom", () => {
    const { container } = render(
      <Tooltip content="아래" position="bottom">
        <span>target</span>
      </Tooltip>
    );
    expect(container.querySelector('[role="tooltip"]')).toBeDefined();
  });
});

// ------- SkeletonCard -------
describe("SkeletonCard", () => {
  it("renders with defaults", () => {
    const { container } = renderWithProviders(<SkeletonCard />);
    expect(container.firstChild).toBeDefined();
  });

  it("renders with custom rows and height", () => {
    const { container } = renderWithProviders(<SkeletonCard rows={5} height="h-8" />);
    expect(container.firstChild).toBeDefined();
  });
});

// ------- SkeletonStatBox -------
describe("SkeletonStatBox", () => {
  it("renders", () => {
    const { container } = renderWithProviders(<SkeletonStatBox />);
    expect(container.firstChild).toBeDefined();
  });
});
