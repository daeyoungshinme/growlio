import { useEffect, useState } from "react";
import type { ToastEvent } from "@/utils/toast";

const COLORS: Record<string, string> = {
  error: "bg-red-600",
  success: "bg-green-600",
  info: "bg-blue-600",
};

const MAX_TOASTS = 3;

export default function Toaster() {
  const [toasts, setToasts] = useState<ToastEvent[]>([]);

  const dismiss = (id: ToastEvent["id"]) => setToasts((prev) => prev.filter((t) => t.id !== id));

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<ToastEvent>).detail;
      setToasts((prev) => [...prev, detail].slice(-MAX_TOASTS));
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== detail.id));
      }, 3500);
    };
    window.addEventListener("growlio:toast", handler);
    return () => window.removeEventListener("growlio:toast", handler);
  }, []);

  if (toasts.length === 0) return null;

  return (
    // 모달(z-60) 위에 떠야 모달 안 오류가 보이고, 좌우 여백을 줘 긴 문구가 화면 끝까지 붙지 않게 한다.
    // 탭하면 닫힌다(가린 버튼을 누를 수 있게) — docs/plans/67 P2-5
    <div className="fixed bottom-[calc(var(--bottom-nav-h)+env(safe-area-inset-bottom)+0.5rem)] left-3 right-3 lg:left-auto lg:bottom-5 lg:right-5 lg:max-w-sm z-[80] flex flex-col items-end gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          role={t.type === "error" ? "alert" : "status"}
          aria-live={t.type === "error" ? "assertive" : "polite"}
          onClick={() => dismiss(t.id)}
          className={`${COLORS[t.type]} pointer-events-auto cursor-pointer text-white text-sm px-4 py-2.5 rounded-xl shadow-lg animate-fade-in`}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
