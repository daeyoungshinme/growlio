import { useEffect, useRef, useState } from "react";

export interface OnlineStatus {
  online: boolean;
  lastOnlineAt: Date | null;
}

export function useOnlineStatus(): OnlineStatus {
  const [online, setOnline] = useState(() => navigator.onLine);
  const [lastOnlineAt, setLastOnlineAt] = useState<Date | null>(
    navigator.onLine ? new Date() : null,
  );

  // 이전 상태 추적 — online → offline 전환 시각 기록
  const prevOnline = useRef(navigator.onLine);

  useEffect(() => {
    const goOnline = () => {
      setOnline(true);
      setLastOnlineAt(new Date());
      prevOnline.current = true;
    };
    const goOffline = () => {
      if (prevOnline.current) {
        setLastOnlineAt(new Date());
      }
      setOnline(false);
      prevOnline.current = false;
    };
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  return { online, lastOnlineAt };
}
