import { useEffect, useState } from "react";
import type { ToastEvent } from "@/utils/toast";

const COLORS: Record<string, string> = {
  error: "bg-red-600",
  success: "bg-green-600",
  info: "bg-blue-600",
};

export default function Toaster() {
  const [toasts, setToasts] = useState<ToastEvent[]>([]);

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<ToastEvent>).detail;
      setToasts((prev) => [...prev, detail]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== detail.id));
      }, 3500);
    };
    window.addEventListener("growlio:toast", handler);
    return () => window.removeEventListener("growlio:toast", handler);
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-[calc(3.75rem+env(safe-area-inset-bottom)+0.5rem)] right-3 lg:bottom-5 lg:right-5 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`${COLORS[t.type]} text-white text-sm px-4 py-2.5 rounded-xl shadow-lg animate-fade-in`}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
