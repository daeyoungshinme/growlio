import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAssetModals } from "@/hooks/useAssetModals";

describe("useAssetModals", () => {
  it("초기 상태: 모든 모달이 닫혀 있고 선택 항목이 없다", () => {
    const { result } = renderHook(() => useAssetModals());
    expect(result.current.showBankModal).toBe(false);
    expect(result.current.showStockModal).toBe(false);
    expect(result.current.showRealEstateModal).toBe(false);
    expect(result.current.editingRealEstate).toBeNull();
    expect(result.current.editingBankAccount).toBeNull();
    expect(result.current.confirmDeleteId).toBeNull();
    expect(result.current.positionsAccount).toBeNull();
    expect(result.current.txAccount).toBeNull();
  });

  it("setShowBankModal이 showBankModal을 토글한다", () => {
    const { result } = renderHook(() => useAssetModals());
    act(() => { result.current.setShowBankModal(true); });
    expect(result.current.showBankModal).toBe(true);
    act(() => { result.current.setShowBankModal(false); });
    expect(result.current.showBankModal).toBe(false);
  });

  it("setShowStockModal이 showStockModal을 토글한다", () => {
    const { result } = renderHook(() => useAssetModals());
    act(() => { result.current.setShowStockModal(true); });
    expect(result.current.showStockModal).toBe(true);
  });

  it("setShowRealEstateModal이 showRealEstateModal을 토글한다", () => {
    const { result } = renderHook(() => useAssetModals());
    act(() => { result.current.setShowRealEstateModal(true); });
    expect(result.current.showRealEstateModal).toBe(true);
  });

  it("setEditingRealEstate가 부동산 계좌를 설정한다", () => {
    const { result } = renderHook(() => useAssetModals());
    const mockAccount = { id: "acc-1", name: "내 아파트" } as never;
    act(() => { result.current.setEditingRealEstate(mockAccount); });
    expect(result.current.editingRealEstate).toEqual(mockAccount);
    act(() => { result.current.setEditingRealEstate(null); });
    expect(result.current.editingRealEstate).toBeNull();
  });

  it("setEditingBankAccount가 은행 계좌를 설정한다", () => {
    const { result } = renderHook(() => useAssetModals());
    const mockAccount = { id: "acc-2", name: "국민은행" } as never;
    act(() => { result.current.setEditingBankAccount(mockAccount); });
    expect(result.current.editingBankAccount).toEqual(mockAccount);
  });

  it("setConfirmDeleteId가 삭제 확인 ID를 설정한다", () => {
    const { result } = renderHook(() => useAssetModals());
    act(() => { result.current.setConfirmDeleteId("acc-3"); });
    expect(result.current.confirmDeleteId).toBe("acc-3");
    act(() => { result.current.setConfirmDeleteId(null); });
    expect(result.current.confirmDeleteId).toBeNull();
  });

  it("setPositionsAccount가 포지션 계좌를 설정한다", () => {
    const { result } = renderHook(() => useAssetModals());
    const info = { id: "acc-4", name: "KIS계좌", dataSource: "KIS_API" };
    act(() => { result.current.setPositionsAccount(info); });
    expect(result.current.positionsAccount).toEqual(info);
  });

  it("setTxAccount가 거래 계좌를 설정한다", () => {
    const { result } = renderHook(() => useAssetModals());
    const info = { id: "acc-5", name: "내 계좌", depositKrw: 1000000 };
    act(() => { result.current.setTxAccount(info); });
    expect(result.current.txAccount).toEqual(info);
  });
});
