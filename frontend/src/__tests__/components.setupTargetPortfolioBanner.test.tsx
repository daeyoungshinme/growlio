import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import SetupTargetPortfolioBanner from "@/components/dashboard/SetupTargetPortfolioBanner";
import { renderWithProviders } from "@/test/renderWithProviders";
import { useAuthStore } from "@/stores/authStore";
import { targetPortfolioBannerDismissedKey } from "@/constants/storageKeys";

const fetchPortfolios = vi.fn();

vi.mock("@/api/portfolios", () => ({
  fetchPortfolios: (...args: unknown[]) => fetchPortfolios(...args),
}));

const STORAGE_KEY = targetPortfolioBannerDismissedKey("user-1");

function renderBanner() {
  return renderWithProviders(
    <MemoryRouter>
      <SetupTargetPortfolioBanner />
    </MemoryRouter>,
  );
}

describe("SetupTargetPortfolioBanner", () => {
  beforeEach(() => {
    fetchPortfolios.mockReset();
    localStorage.clear();
    useAuthStore.setState({ userId: "user-1" });
  });

  it("포트폴리오가 없으면 배너를 표시한다", async () => {
    fetchPortfolios.mockResolvedValue([]);
    renderBanner();
    await waitFor(() => {
      expect(screen.getByText("기준 포트폴리오를 만들어보세요")).toBeInTheDocument();
    });
  });

  it("포트폴리오가 있으면 배너를 표시하지 않는다", async () => {
    fetchPortfolios.mockResolvedValue([{ id: "p-1" }]);
    renderBanner();
    await waitFor(() => expect(fetchPortfolios).toHaveBeenCalled());
    expect(screen.queryByText("기준 포트폴리오를 만들어보세요")).not.toBeInTheDocument();
  });

  it("닫기 버튼을 누르면 localStorage에 저장되어 재마운트해도 다시 표시되지 않는다", async () => {
    fetchPortfolios.mockResolvedValue([]);
    const { unmount } = renderBanner();
    await waitFor(() => {
      expect(screen.getByLabelText("배너 닫기")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByLabelText("배너 닫기"));
    expect(screen.queryByText("기준 포트폴리오를 만들어보세요")).not.toBeInTheDocument();
    expect(localStorage.getItem(STORAGE_KEY)).toBe("true");

    unmount();
    renderBanner();
    await waitFor(() => expect(fetchPortfolios).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("기준 포트폴리오를 만들어보세요")).not.toBeInTheDocument();
  });

  it("한 계정이 닫은 배너는 같은 기기의 다른 계정에선 다시 뜬다(plans/118 C7)", async () => {
    fetchPortfolios.mockResolvedValue([]);
    localStorage.setItem(STORAGE_KEY, "true");
    useAuthStore.setState({ userId: "user-2" });
    renderBanner();
    await waitFor(() => {
      expect(screen.getByText("기준 포트폴리오를 만들어보세요")).toBeInTheDocument();
    });
  });
});
