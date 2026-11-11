import { describe, expect, it } from "vitest";
import { AxiosError, AxiosHeaders } from "axios";
import { isRetryableError, retryDelayMs, shouldRetryQuery } from "@/api/retryPolicy";

function axiosError(status?: number): AxiosError {
  const err = new AxiosError("fail", status == null ? "ERR_NETWORK" : "ERR_BAD_RESPONSE");
  if (status != null) {
    err.response = {
      status,
      statusText: "",
      data: null,
      headers: {},
      config: { headers: new AxiosHeaders() },
    };
  }
  return err;
}

describe("retryPolicy (plans/125 C7)", () => {
  it("네트워크 오류·5xx·429만 재시도 대상이다", () => {
    expect(isRetryableError(axiosError())).toBe(true);
    expect(isRetryableError(axiosError(503))).toBe(true);
    expect(isRetryableError(axiosError(429))).toBe(true);
    expect(isRetryableError(axiosError(404))).toBe(false);
    expect(isRetryableError(axiosError(422))).toBe(false);
    expect(isRetryableError(new Error("boom"))).toBe(false);
  });

  it("최대 1회만 재시도한다", () => {
    expect(shouldRetryQuery(0, axiosError(500))).toBe(true);
    expect(shouldRetryQuery(1, axiosError(500))).toBe(false);
    expect(shouldRetryQuery(0, axiosError(400))).toBe(false);
  });

  it("지수 백오프에 지터를 더하고 상한을 둔다", () => {
    expect(retryDelayMs(0, undefined, () => 0)).toBe(500);
    expect(retryDelayMs(0, undefined, () => 1)).toBe(1000);
    expect(retryDelayMs(1, undefined, () => 1)).toBe(2000);
    expect(retryDelayMs(10, undefined, () => 1)).toBe(8000);
  });
});
