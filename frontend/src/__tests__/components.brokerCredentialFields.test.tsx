import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import BrokerCredentialFields from "@/components/assets/BrokerCredentialFields";
import type { AssetAccountCreate } from "@/api/assets";
import type { BrokerDataSource } from "@/constants/brokerCredentials";

const EMPTY_FORM = { name: "", asset_type: "STOCK_OTHER" } as AssetAccountCreate;

function renderFields(
  source: BrokerDataSource,
  opts: { isEdit?: boolean; form?: Partial<AssetAccountCreate>; accountNoError?: string } = {},
) {
  const set = vi.fn();
  const onCredentialChange = vi.fn();
  render(
    <BrokerCredentialFields
      source={source}
      form={{ ...EMPTY_FORM, ...opts.form }}
      set={set}
      isEdit={opts.isEdit ?? false}
      accountNoError={opts.accountNoError}
      verifyState="idle"
      verifyError=""
      onVerify={vi.fn()}
      onCredentialChange={onCredentialChange}
    />,
  );
  return { set, onCredentialChange };
}

describe("BrokerCredentialFields", () => {
  it.each([
    ["KIS_API", "stock-kis-account-no", "stock-kis-app-key", "stock-kis-app-secret"],
    ["KIWOOM_API", "stock-kiwoom-account-no", "stock-kiwoom-app-key", "stock-kiwoom-app-secret"],
    ["TOSS_API", "stock-toss-account-no", "stock-toss-client-id", "stock-toss-client-secret"],
  ] as const)("%s: 생성 모드는 계좌번호·키·시크릿 입력을 렌더한다", (source, ...ids) => {
    renderFields(source);
    for (const id of ids) expect(document.getElementById(id)).not.toBeNull();
  });

  it("키 입력은 빈 문자열을 undefined로 저장하고 검증 상태를 초기화한다", () => {
    const { set, onCredentialChange } = renderFields("KIS_API", { form: { kis_app_key: "k" } });
    fireEvent.change(document.getElementById("stock-kis-app-key")!, { target: { value: "" } });
    expect(set).toHaveBeenCalledWith("kis_app_key", undefined);
    expect(onCredentialChange).toHaveBeenCalled();
  });

  it("수정 모드는 계좌번호를 숨기고 기존 값 유지 안내를 표시한다", () => {
    renderFields("TOSS_API", { isEdit: true });
    expect(document.getElementById("stock-toss-account-no")).toBeNull();
    expect(screen.getByText("비워두면 기존 값을 유지합니다")).toBeInTheDocument();
    expect(screen.getAllByPlaceholderText("기존 값 유지")).toHaveLength(2);
  });

  it("계좌번호 오류 메시지를 표시한다", () => {
    renderFields("KIS_API", { accountNoError: "형식 오류" });
    expect(screen.getByText("형식 오류")).toBeInTheDocument();
  });

  it("토스만 IP 등록 안내를 표시한다", () => {
    renderFields("TOSS_API");
    expect(screen.getByText(/IP 관리/, { selector: "span" })).toBeInTheDocument();
  });

  it("키움은 IP 등록 안내가 없다", () => {
    renderFields("KIWOOM_API");
    expect(screen.queryByText(/IP 관리/)).not.toBeInTheDocument();
  });
});
