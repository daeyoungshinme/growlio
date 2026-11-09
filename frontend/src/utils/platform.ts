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
  const domain = (import.meta.env.VITE_API_DOMAIN as string | undefined) ?? "localhost:8000";
  return `https://${domain}`;
}

/**
 * UUID v4 문자열. `crypto.randomUUID`는 Chrome/WebView 92+ 전용이라, minSdk 24 기기의 갱신 안 된
 * System WebView에서는 없다 — 그때는 `getRandomValues`로 같은 형식을 만든다(plans/119 C5).
 * 주문 멱등 키에 쓰므로 `Math.random`으로 떨어지지 않는다.
 */
export function randomId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
