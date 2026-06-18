/**
 * 네이티브(Capacitor) vs 웹(PWA/브라우저) 런타임 감지 유틸.
 * Capacitor WebView에서 실행 중이면 true, 일반 브라우저면 false.
 */
export function isNativePlatform(): boolean {
  try {
    // Capacitor v3+: window.Capacitor.isNativePlatform() 함수 존재
    const cap = (window as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor;
    return typeof cap?.isNativePlatform === "function" && cap.isNativePlatform();
  } catch {
    return false;
  }
}

/**
 * 네이티브 앱에서 사용할 API baseURL.
 * 웹에서는 빈 문자열("")을 반환해 상대 경로 유지.
 * 네이티브에서는 VITE_API_DOMAIN 환경변수 기반의 절대 URL 반환.
 */
export function getApiBaseUrl(): string {
  if (!isNativePlatform()) return "";
  const domain =
    (import.meta.env.VITE_API_DOMAIN as string | undefined) ?? "localhost:8000";
  return `https://${domain}`;
}
