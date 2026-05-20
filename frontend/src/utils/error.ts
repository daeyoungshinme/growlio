export function extractErrorMessage(
  error: unknown,
  fallback = "오류가 발생했습니다",
): string {
  if (typeof error === "string") return error;
  if (error instanceof Error) {
    const axiosDetail = (
      error as unknown as { response?: { data?: { detail?: string } } }
    ).response?.data?.detail;
    return axiosDetail ?? error.message ?? fallback;
  }
  const detail = (error as { response?: { data?: { detail?: string } } })
    ?.response?.data?.detail;
  return detail ?? fallback;
}
