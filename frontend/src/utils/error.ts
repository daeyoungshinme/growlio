type FastApiDetail = string | { msg: string; loc?: unknown[]; type?: string }[];

function parseDetail(detail: FastApiDetail): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => (typeof e === "string" ? e : e.msg)).join(", ");
  }
  return "오류가 발생했습니다";
}

export function extractErrorMessage(
  error: unknown,
  fallback = "오류가 발생했습니다",
): string {
  if (typeof error === "string") return error;
  const data = (error as { response?: { data?: { detail?: FastApiDetail } } })
    ?.response?.data;
  if (data?.detail !== undefined) return parseDetail(data.detail);
  if (error instanceof Error) return error.message || fallback;
  return fallback;
}
